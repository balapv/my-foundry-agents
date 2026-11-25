"""Reservation API: upcoming reservations for the authenticated customer."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from common.data_store import get_store
from common.dates import demo_today, offset_days, shift
from common.errors import tool_error

router = APIRouter(tags=["reservations"])


def _public_customer(customer: dict[str, Any]) -> dict[str, Any]:
    keys = ("customerId", "firstName", "lastName", "loyaltyNumber", "loyaltyTier", "homeAirport")
    return {k: customer[k] for k in keys}


def _is_upcoming(reservation: dict[str, Any], stored_today: str) -> bool:
    return reservation["status"] == "Confirmed" and any(s["date"] >= stored_today for s in reservation["segments"])


@router.get("/customers/{customerId}/reservations", operation_id="get_customer_reservations")
def get_customer_reservations(
    customerId: str,
    confirmationCode: str | None = Query(default=None, min_length=6, max_length=6),
):
    store = get_store()
    customer = store.customers.get(customerId.strip().upper())
    if customer is None:
        return tool_error(404, "CUSTOMER_NOT_FOUND", f"No customer profile exists for {customerId}.")

    owned = [r for r in store.reservations if r["primaryCustomerId"] == customer["customerId"]]
    if confirmationCode:
        code = confirmationCode.strip().upper()
        matches = [r for r in owned if r["confirmationCode"] == code]
        if not matches:
            return tool_error(
                404, "RESERVATION_NOT_FOUND",
                f"No reservation with confirmation code {code} was found for this customer.",
            )
        reservations = matches
    else:
        stored_today = store.anchor_date.isoformat()
        reservations = sorted((r for r in owned if _is_upcoming(r, stored_today)),
                              key=lambda r: min(s["date"] for s in r["segments"]))

    body: dict[str, Any] = {
        "customer": _public_customer(customer),
        "reservations": reservations,
        "reservationCount": len(reservations),
    }
    if not reservations:
        body["message"] = "The customer has no upcoming confirmed reservations."
    shifted = shift(body, offset_days(store.anchor_date))
    return {"currentDate": demo_today().isoformat(), **shifted}
