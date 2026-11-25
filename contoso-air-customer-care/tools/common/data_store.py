"""Read-only, in-memory access to the synthetic Contoso Air dataset."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from common.dates import demo_now, demo_timezone, offset_days


def _resolve_data_dir() -> Path:
    configured = os.environ.get("CONTOSO_DATA_DIR")
    if configured:
        return Path(configured)
    here = Path(__file__).resolve()
    for candidate in (here.parents[2] / "data", here.parents[1] / "data"):
        if (candidate / "flights.json").exists():
            return candidate
    raise FileNotFoundError("Synthetic data not found. Set CONTOSO_DATA_DIR or run data/generate_data.py.")


class DataStore:
    def __init__(self, data_dir: Path):
        def load(name: str) -> dict[str, Any]:
            with open(data_dir / name, encoding="utf-8") as fh:
                return json.load(fh)

        customers = load("customers.json")
        self.anchor_date = date.fromisoformat(customers["metadata"]["anchorDate"])
        self.customers = {c["customerId"]: c for c in customers["customers"]}
        self.reservations: list[dict[str, Any]] = load("reservations.json")["reservations"]
        flights = load("flights.json")
        self.airports: dict[str, dict[str, Any]] = flights["metadata"]["airports"]
        self.flights: list[dict[str, Any]] = flights["flights"]
        self.flight_index = {(f["flightNumber"], f["date"]): f for f in self.flights}
        self.statuses = {(s["flightNumber"], s["date"]): s for s in load("flight-status.json")["flightStatus"]}
        self.faults: list[dict[str, Any]] = load("fault-injection.json")["faults"]
        if os.environ.get("DISABLE_FAULT_INJECTION", "").lower() in {"1", "true", "yes"}:
            self.faults = []

    def fault_for(self, endpoint: str, flight_number: str, stored_date: str) -> dict[str, Any] | None:
        for fault in self.faults:
            if (fault["endpoint"] == endpoint and fault["flightNumber"] == flight_number
                    and fault["date"] == stored_date):
                return fault
        return None

    def to_utc(self, local: str | datetime, airport: str) -> datetime:
        """Convert a stored local time at ``airport`` to naive UTC using the dataset's UTC offsets."""
        value = datetime.fromisoformat(local) if isinstance(local, str) else local
        return value - timedelta(hours=self.airports[airport]["utc"])

    def from_utc(self, utc: datetime, airport: str) -> datetime:
        return utc + timedelta(hours=self.airports[airport]["utc"])

    def now_utc(self) -> datetime:
        """The simulated current time, mapped into the stored dataset's frame, as naive UTC."""
        tz = demo_timezone()
        stored_local = demo_now() - timedelta(days=offset_days(self.anchor_date))
        hours = next((a["utc"] for a in self.airports.values() if a["tz"] == tz), None)
        if hours is None:
            offset = ZoneInfo(tz).utcoffset(stored_local) or timedelta(0)
            return stored_local - offset
        return stored_local - timedelta(hours=hours)


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    return DataStore(_resolve_data_dir())
