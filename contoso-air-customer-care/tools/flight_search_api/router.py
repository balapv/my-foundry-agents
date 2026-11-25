"""Flight Search API: factual alternative-flight inventory between two airports on a date.

Returns every flight or one-stop itinerary that is not cancelled, has not yet departed and
has at least one seat for sale, with per-cabin seat availability, in chronological order
of departure. It deliberately does NOT rank, recommend, apply rebooking policy, or remove
options because they lack seats for the whole party or in the preferred cabin: the
Foundry agent reasons over these facts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from common.data_store import DataStore, get_store
from common.dates import demo_today, offset_days, shift, to_stored_date
from common.errors import tool_error

router = APIRouter(tags=["flight-search"])

CABINS = ("First", "Economy Plus", "Main Cabin")
MIN_CONNECTION_MINUTES = 45
MAX_CONNECTION_MINUTES = 300


def _leg(store: DataStore, flight: dict[str, Any]) -> dict[str, Any]:
    status = store.statuses[(flight["flightNumber"], flight["date"])]
    return {
        "flightNumber": flight["flightNumber"],
        "date": flight["date"],
        "origin": flight["origin"],
        "destination": flight["destination"],
        "departureLocal": flight["departureLocal"],
        "departureTimeZone": flight["departureTimeZone"],
        "arrivalLocal": flight["arrivalLocal"],
        "arrivalTimeZone": flight["arrivalTimeZone"],
        "aircraft": flight["aircraft"],
        "status": status["status"],
        "cabinAvailability": flight["cabinAvailability"],
        "totalSeatsAvailable": flight["totalSeatsAvailable"],
    }


def _option(store: DataStore, legs: list[dict[str, Any]]) -> dict[str, Any]:
    first, last = legs[0], legs[-1]
    departure_utc = store.to_utc(first["departureLocal"], first["origin"])
    arrival_utc = store.to_utc(last["arrivalLocal"], last["destination"])
    # A passenger needs a seat in the same cabin on every leg, so itinerary availability
    # per cabin is the minimum across legs; seats in different cabins are never combined.
    cabins = {c: min(leg["cabinAvailability"][c] for leg in legs) for c in CABINS}
    option: dict[str, Any] = {
        "type": "Nonstop" if len(legs) == 1 else "Connection",
        "stops": len(legs) - 1,
        "flightNumbers": [leg["flightNumber"] for leg in legs],
        "origin": first["origin"],
        "destination": last["destination"],
        "departureLocal": first["departureLocal"],
        "departureTimeZone": first["departureTimeZone"],
        "arrivalLocal": last["arrivalLocal"],
        "arrivalTimeZone": last["arrivalTimeZone"],
        "totalTravelMinutes": int((arrival_utc - departure_utc).total_seconds() // 60),
        "cabinAvailability": cabins,
        "totalSeatsAvailable": sum(cabins.values()),
        "segments": [_leg(store, leg) for leg in legs],
    }
    if len(legs) == 2:
        option["connectionAirport"] = first["destination"]
        option["layoverMinutes"] = int(
            (datetime.fromisoformat(last["departureLocal"]) - datetime.fromisoformat(first["arrivalLocal"])).total_seconds() // 60
        )
    option["_sortKey"] = (departure_utc, arrival_utc, option["flightNumbers"])
    return option


def _bookable(store: DataStore, flight: dict[str, Any], now_utc: datetime) -> bool:
    status = store.statuses[(flight["flightNumber"], flight["date"])]
    departure = status.get("estimatedDeparture") or flight["departureLocal"]
    return (not status["isCancelled"] and flight["totalSeatsAvailable"] > 0
            and store.to_utc(departure, flight["origin"]) > now_utc)


@router.get("/flight-search/alternatives", operation_id="search_alternative_flights")
def search_alternative_flights(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    travelDate: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    passengerCount: int = Query(default=1, ge=1, le=9),
    preferredCabin: str | None = Query(default=None),
    preferNonstop: bool | None = Query(default=None),
):
    store = get_store()
    origin, destination = origin.upper(), destination.upper()
    for code in (origin, destination):
        if code not in store.airports:
            return tool_error(400, "UNKNOWN_AIRPORT", f"Contoso Air does not serve airport {code}.")
    if origin == destination:
        return tool_error(400, "INVALID_ROUTE", "Origin and destination must be different.")
    if preferredCabin and preferredCabin not in CABINS:
        return tool_error(400, "INVALID_CABIN", f"preferredCabin must be one of: {', '.join(CABINS)}.")
    try:
        stored_date = to_stored_date(travelDate, store.anchor_date)
    except ValueError:
        return tool_error(400, "INVALID_DATE", f"{travelDate} is not a valid date. Use YYYY-MM-DD.")
    if stored_date < store.anchor_date.isoformat():
        return tool_error(400, "DATE_IN_PAST", "Alternatives can only be searched for today or a future date.")

    now_utc = store.now_utc()
    day_flights = [f for f in store.flights if f["date"] == stored_date and _bookable(store, f, now_utc)]
    options = [_option(store, [f]) for f in day_flights if f["origin"] == origin and f["destination"] == destination]
    for first in (f for f in day_flights if f["origin"] == origin and f["destination"] != destination):
        for second in (f for f in day_flights if f["origin"] == first["destination"] and f["destination"] == destination):
            layover = (datetime.fromisoformat(second["departureLocal"])
                       - datetime.fromisoformat(first["arrivalLocal"])).total_seconds() / 60
            if MIN_CONNECTION_MINUTES <= layover <= MAX_CONNECTION_MINUTES:
                options.append(_option(store, [first, second]))

    # Chronological by departure (then arrival); this is not a ranking.
    options.sort(key=lambda o: o.pop("_sortKey"))

    body = {
        "search": {
            "origin": origin,
            "destination": destination,
            "travelDate": stored_date,
            "passengerCount": passengerCount,
            "preferredCabin": preferredCabin,
            "preferNonstop": preferNonstop,
        },
        "resultCount": len(options),
        "options": [{"optionId": f"OPT-{i}", **o} for i, o in enumerate(options, start=1)],
        "note": ("Options are listed in chronological order of departure. The list is not ranked or filtered "
                 "by party size or cabin, and no seats have been held or booked."),
    }
    if not options:
        body["message"] = ("No flights that are not cancelled, have not departed, and have at least one available "
                           "seat were found for this route and date.")
    return {"currentDate": demo_today().isoformat(), **shift(body, offset_days(store.anchor_date))}
