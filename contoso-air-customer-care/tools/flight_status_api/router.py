"""Flight Status API: authoritative operational status for one flight on one date."""

from __future__ import annotations

from fastapi import APIRouter, Query

from common.data_store import get_store
from common.dates import demo_today, offset_days, shift, to_stored_date
from common.errors import tool_error

router = APIRouter(tags=["flight-status"])


@router.get("/flight-status/{flightNumber}", operation_id="get_flight_status")
def get_flight_status(
    flightNumber: str,
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Departure date, YYYY-MM-DD"),
):
    store = get_store()
    number = flightNumber.strip().upper().replace(" ", "")
    try:
        stored_date = to_stored_date(date, store.anchor_date)
    except ValueError:
        return tool_error(400, "INVALID_DATE", f"{date} is not a valid date. Use YYYY-MM-DD.")

    if not any(f["flightNumber"] == number for f in store.flights):
        return tool_error(404, "FLIGHT_NOT_FOUND", f"Contoso Air does not operate a flight numbered {number}.")

    fault = store.fault_for("flight-status", number, stored_date)
    if fault:
        return tool_error(fault["httpStatus"], "SERVICE_UNAVAILABLE", fault["message"])

    status = store.statuses.get((number, stored_date))
    if status is None:
        return tool_error(404, "FLIGHT_NOT_FOUND", f"Flight {number} is not scheduled to operate on {date}.")

    origin, destination = store.airports[status["origin"]], store.airports[status["destination"]]
    body = {
        **status,
        "originCity": origin["city"],
        "destinationCity": destination["city"],
        "departureTimeZone": origin["tz"],
        "arrivalTimeZone": destination["tz"],
    }
    # A status update cannot be later than the simulated current time.
    now_utc = store.now_utc()
    if store.to_utc(status["lastUpdated"], status["origin"]) > now_utc:
        body["lastUpdated"] = store.from_utc(now_utc, status["origin"]).strftime("%Y-%m-%dT%H:%M")
    return {"currentDate": demo_today().isoformat(), **shift(body, offset_days(store.anchor_date))}
