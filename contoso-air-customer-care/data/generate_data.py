"""Generate the deterministic synthetic dataset for the Contoso Air Customer Care demo.

All data is fictional. The generator is seeded, so running it always produces
byte-identical JSON files. Dates are written relative to a fixed ANCHOR_DATE
("today" in the dataset). The tools API rebases every date at runtime so the
seeded hero scenario (CT218 cancelled "tomorrow") stays true on any demo day.

Usage:
    python data/generate_data.py           # (re)write the JSON files
    python data/generate_data.py --check   # verify files are current and valid
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent
SEED = 20260514
ANCHOR_DATE = date(2026, 5, 14)  # "today" inside the stored dataset
DAY_RANGE = range(-12, 8)  # flight instances from 12 days ago to 7 days ahead
TARGET_FLIGHTS = 150
TARGET_RESERVATIONS = 60
CABINS = ("First", "Economy Plus", "Main Cabin")

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

AIRPORTS: dict[str, dict[str, Any]] = {
    "SEA": {"city": "Seattle", "name": "Seattle-Tacoma International", "tz": "America/Los_Angeles", "utc": -7},
    "PDX": {"city": "Portland", "name": "Portland International", "tz": "America/Los_Angeles", "utc": -7},
    "SFO": {"city": "San Francisco", "name": "San Francisco International", "tz": "America/Los_Angeles", "utc": -7},
    "LAX": {"city": "Los Angeles", "name": "Los Angeles International", "tz": "America/Los_Angeles", "utc": -7},
    "DEN": {"city": "Denver", "name": "Denver International", "tz": "America/Denver", "utc": -6},
    "ORD": {"city": "Chicago", "name": "Chicago O'Hare International", "tz": "America/Chicago", "utc": -5},
    "DFW": {"city": "Dallas/Fort Worth", "name": "Dallas/Fort Worth International", "tz": "America/Chicago", "utc": -5},
    "ATL": {"city": "Atlanta", "name": "Hartsfield-Jackson Atlanta International", "tz": "America/New_York", "utc": -4},
    "BOS": {"city": "Boston", "name": "Boston Logan International", "tz": "America/New_York", "utc": -4},
    "JFK": {"city": "New York", "name": "John F. Kennedy International", "tz": "America/New_York", "utc": -4},
    "MIA": {"city": "Miami", "name": "Miami International", "tz": "America/New_York", "utc": -4},
}

AIRCRAFT = {
    "A321neo": {"type": "Airbus A321neo", "capacity": {"First": 16, "Economy Plus": 36, "Main Cabin": 138}},
    "737-9": {"type": "Boeing 737 MAX 9", "capacity": {"First": 16, "Economy Plus": 30, "Main Cabin": 132}},
    "737-800": {"type": "Boeing 737-800", "capacity": {"First": 12, "Economy Plus": 24, "Main Cabin": 123}},
    "E175": {"type": "Embraer 175", "capacity": {"First": 12, "Economy Plus": 16, "Main Cabin": 48}},
}

# Daily schedule templates: flight number -> (origin, destination, departure HH:MM, block minutes, aircraft)
SCHEDULE: dict[str, tuple[str, str, str, int, str]] = {
    "CT102": ("SEA", "SFO", "06:00", 125, "737-800"),
    "CT105": ("SFO", "SEA", "09:10", 130, "737-800"),
    "CT118": ("SEA", "LAX", "08:15", 165, "737-9"),
    "CT121": ("LAX", "SEA", "12:40", 170, "737-9"),
    "CT126": ("SEA", "LAX", "13:35", 165, "737-800"),
    "CT130": ("PDX", "SFO", "07:20", 110, "E175"),
    "CT144": ("SEA", "DFW", "11:55", 230, "737-9"),
    "CT204": ("SEA", "DEN", "07:45", 160, "737-800"),
    "CT207": ("DEN", "SEA", "11:30", 175, "737-800"),
    "CT218": ("SEA", "JFK", "10:30", 320, "A321neo"),
    "CT219": ("JFK", "SEA", "17:55", 385, "A321neo"),
    "CT226": ("SEA", "JFK", "09:20", 325, "A321neo"),
    "CT232": ("SEA", "JFK", "15:45", 325, "737-9"),
    "CT310": ("SEA", "ORD", "07:10", 245, "737-9"),
    "CT315": ("ORD", "SEA", "16:20", 280, "737-9"),
    "CT352": ("SFO", "ORD", "06:45", 250, "737-9"),
    "CT372": ("PDX", "ORD", "08:15", 235, "737-800"),
    "CT442": ("ORD", "JFK", "15:05", 135, "737-800"),
    "CT460": ("ORD", "BOS", "14:05", 140, "737-800"),
    "CT466": ("ORD", "BOS", "15:20", 140, "E175"),
    "CT472": ("ORD", "MIA", "09:55", 185, "737-800"),
    "CT540": ("SFO", "BOS", "08:05", 335, "A321neo"),
    "CT544": ("SFO", "BOS", "12:30", 335, "737-9"),
    "CT580": ("PDX", "BOS", "07:30", 330, "737-9"),
    "CT584": ("PDX", "BOS", "13:10", 330, "737-800"),
    "CT610": ("LAX", "ORD", "07:00", 245, "737-9"),
    "CT614": ("LAX", "ORD", "10:40", 245, "737-800"),
    "CT655": ("DFW", "ATL", "11:40", 125, "737-800"),
    "CT720": ("LAX", "DEN", "09:00", 140, "E175"),
    "CT760": ("DFW", "LAX", "15:10", 200, "737-800"),
    "CT820": ("DEN", "ORD", "13:30", 150, "737-800"),
    "CT880": ("ATL", "MIA", "10:25", 115, "E175"),
    "CT915": ("BOS", "ORD", "07:05", 165, "737-800"),
    "CT920": ("JFK", "MIA", "08:40", 190, "737-800"),
    "CT990": ("BOS", "SEA", "17:30", 390, "A321neo"),
}

CUSTOMERS_SEED: list[tuple[str, str, str, str]] = [
    # firstName, lastName, loyaltyTier, homeAirport  (index 0 -> CUST-1001)
    ("Maya", "Patel", "Silver", "SFO"),
    ("Daniel", "Okafor", "Basic", "ATL"),
    ("Sofia", "Rossi", "Gold", "BOS"),
    ("Liam", "Nguyen", "Basic", "SEA"),
    ("Hannah", "Kim", "Platinum", "JFK"),
    ("Mateo", "Hernandez", "Silver", "LAX"),
    ("Alex", "Johnson", "Gold", "SEA"),  # CUST-1007 — hero
    ("Grace", "Thompson", "Basic", "DEN"),
    ("Omar", "Haddad", "Silver", "DFW"),
    ("Chloe", "Martin", "Gold", "ORD"),
    ("Ethan", "Brooks", "Basic", "PDX"),
    ("Priya", "Raman", "Silver", "SFO"),  # CUST-1012 — scenario B1
    ("Lucas", "Silva", "Platinum", "MIA"),
    ("Emily", "Carter", "Basic", "SEA"),
    ("Marcus", "Reed", "Basic", "LAX"),  # CUST-1015 — scenario B2
    ("Aisha", "Bello", "Gold", "ATL"),
    ("Noah", "Fischer", "Silver", "DEN"),
    ("Elena", "Petrova", "Silver", "PDX"),  # CUST-1018 — scenario B3
    ("Jordan", "Blake", "Basic", "SEA"),  # CUST-1019 — scenario D1
    ("Isabella", "Moreno", "Silver", "LAX"),
    ("Samuel", "Wright", "Gold", "DFW"),  # CUST-1021 — scenario D3
    ("Mei", "Chen", "Basic", "SFO"),
    ("Ryan", "O'Connell", "Silver", "BOS"),
    ("Fatima", "Rahman", "Platinum", "ORD"),  # CUST-1024 — scenario D4
    ("Benjamin", "Clarke", "Basic", "JFK"),
    ("Zoe", "Anderson", "Gold", "SEA"),
    ("Kenji", "Watanabe", "Silver", "SFO"),
    ("Olivia", "Grant", "Basic", "MIA"),
    ("Tomas", "Novak", "Gold", "DEN"),
    ("Ava", "Sullivan", "Platinum", "SEA"),
]

COMPANION_FIRST = {
    "adult": ["Jamie", "Chris", "Morgan", "Sam", "Riley", "Casey", "Drew", "Jesse", "Robin", "Avery", "Quinn", "Hayden"],
    "child": ["Leo", "Mia", "Ella", "Noor", "Kai", "Lily", "Owen", "Ivy", "Theo", "Ruby", "Finn", "Nora"],
}

SCENARIO_CUSTOMERS = {
    "CUST-1007": "A - hero: family of four, CT218 cancelled tomorrow",
    "CUST-1012": "B1 — family of four, no same-day flight has four seats",
    "CUST-1015": "B2 — couple, nonstop and connection both fit",
    "CUST-1018": "B3 — parent with two children, only the connection fits",
    "CUST-1019": "D1 — no upcoming reservations",
    "CUST-1021": "D3 — flight-status system unavailable for their flight",
    "CUST-1024": "D4 — reservation record conflicts with operational status",
}

UNKNOWN_CONFIRMATION_CODE = "QX7M4R"  # used by evaluation D1; must never exist
UNKNOWN_FLIGHT_NUMBER = "CT999"  # used by evaluation D2; must never exist


# ---------------------------------------------------------------------------
# Scenario flight overrides: (flight, day offset) -> seats / status
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Override:
    seats: dict[str, int] | None = None  # seats available per cabin
    status: str = "On Time"  # On Time | Delayed | Cancelled
    delay_minutes: int = 0
    disruption: dict[str, str] | None = None
    last_updated: tuple[int, str] | None = None  # (day offset, HH:MM)


def _cancel(category: str, responsibility: str, reason: str, code: str, updated: tuple[int, str]) -> Override:
    return Override(
        seats={c: 0 for c in CABINS},
        status="Cancelled",
        disruption={"type": "Cancellation", "category": category, "responsibility": responsibility,
                    "reasonCode": code, "reason": reason},
        last_updated=updated,
    )


def _delay(minutes: int, category: str, responsibility: str, reason: str, code: str,
           updated: tuple[int, str] | None = None) -> Override:
    return Override(
        status="Delayed",
        delay_minutes=minutes,
        disruption={"type": "Delay", "category": category, "responsibility": responsibility,
                    "reasonCode": code, "reason": reason},
        last_updated=updated,
    )


SCENARIO_FLIGHTS: dict[tuple[str, int], Override] = {
    # --- Hero (day +1): SEA -> JFK ------------------------------------------------
    ("CT218", 1): _cancel("Controllable", "Carrier", "Operational disruption", "OPS", (0, "06:12")),
    ("CT226", 1): Override(seats={"First": 1, "Economy Plus": 6, "Main Cabin": 9}),
    ("CT232", 1): Override(seats={"First": 0, "Economy Plus": 1, "Main Cabin": 2}),
    ("CT310", 1): Override(seats={"First": 2, "Economy Plus": 2, "Main Cabin": 8}),
    ("CT442", 1): Override(seats={"First": 0, "Economy Plus": 2, "Main Cabin": 4}),
    # --- B1 (day +1): SFO -> BOS, nobody can seat four together today ----------
    ("CT540", 1): _cancel("Controllable", "Carrier", "Crew availability", "CRW", (0, "05:48")),
    ("CT544", 1): Override(seats={"First": 0, "Economy Plus": 0, "Main Cabin": 2}),
    ("CT352", 1): Override(seats={"First": 1, "Economy Plus": 1, "Main Cabin": 3}),
    ("CT460", 1): Override(seats={"First": 0, "Economy Plus": 0, "Main Cabin": 2}),
    ("CT540", 2): Override(seats={"First": 1, "Economy Plus": 3, "Main Cabin": 7}),
    # --- B2 (day +2): LAX -> ORD, nonstop and connection both fit ---------------
    ("CT610", 2): _cancel("Controllable", "Carrier", "Aircraft maintenance", "MX", (0, "07:30")),
    ("CT614", 2): Override(seats={"First": 0, "Economy Plus": 1, "Main Cabin": 4}),
    ("CT720", 2): Override(seats={"First": 1, "Economy Plus": 2, "Main Cabin": 4}),
    ("CT820", 2): Override(seats={"First": 0, "Economy Plus": 1, "Main Cabin": 3}),
    # --- B3 (day +3): PDX -> BOS, only the connection fits three ----------------
    ("CT580", 3): _cancel("Controllable", "Carrier", "Operational disruption", "OPS", (0, "08:05")),
    ("CT584", 3): Override(seats={"First": 0, "Economy Plus": 0, "Main Cabin": 2}),
    ("CT372", 3): Override(seats={"First": 1, "Economy Plus": 2, "Main Cabin": 6}),
    ("CT466", 3): Override(seats={"First": 0, "Economy Plus": 2, "Main Cabin": 3}),
    # --- D3 (day +1): DFW -> ATL, status service fails (see fault-injection.json)
    ("CT655", 1): Override(seats={"First": 2, "Economy Plus": 5, "Main Cabin": 14}),
    # --- D4 (day +2): ORD -> MIA operates normally, but reservation says cancelled
    ("CT472", 2): Override(seats={"First": 3, "Economy Plus": 4, "Main Cabin": 11}),
}

# Other disrupted flights that make the system look real (never scenario flights).
BACKGROUND_DISRUPTIONS: dict[tuple[str, int], Override] = {
    ("CT207", -8): _cancel("Uncontrollable", "Weather", "Winter weather at Denver", "WX", (-9, "19:40")),
    ("CT915", -5): _cancel("Controllable", "Carrier", "Aircraft maintenance", "MX", (-6, "21:15")),
    ("CT121", -3): _delay(95, "Uncontrollable", "Air traffic control", "Air traffic control flow program", "ATC"),
    ("CT102", 0): _delay(50, "Uncontrollable", "Weather", "Low visibility at San Francisco", "WX", (0, "05:20")),
    ("CT760", 1): _delay(210, "Controllable", "Carrier", "Aircraft maintenance", "MX", (0, "07:55")),
    ("CT920", 4): _cancel("Uncontrollable", "Weather", "Forecast tropical storm at Miami", "WX", (0, "09:10")),
}

# Non-scenario flight instances referenced by scenario reservations (always generated).
REQUIRED_INSTANCES: set[tuple[str, int]] = {("CT204", -11), ("CT207", -7), ("CT102", -10), ("CT105", -6), ("CT118", 5)}

# Ordinary, unrelated Seattle departures on the hero day, so the hero airport has normal
# activity. None of these destinations has an onward flight to JFK, so they never add
# SEA -> JFK itineraries.
HERO_DAY_SEA_DEPARTURES: set[tuple[str, int]] = {("CT102", 1), ("CT118", 1), ("CT204", 1), ("CT126", 1), ("CT144", 1)}

# On scenario days, background flights touching scenario origins/destinations are
# withheld so each scenario search returns exactly the intended alternatives.
SCENARIO_EXCLUSIONS: dict[int, dict[str, set[str]]] = {
    1: {"origins": {"SFO"}, "destinations": {"JFK", "BOS"}},
    2: {"origins": {"LAX", "SFO"}, "destinations": {"ORD", "BOS"}},
    3: {"origins": {"PDX"}, "destinations": {"BOS"}},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def day(offset: int) -> date:
    return ANCHOR_DATE + timedelta(days=offset)


def local_times(origin: str, destination: str, dep_day: date, dep_hhmm: str, block_minutes: int) -> tuple[str, str]:
    dep = datetime.combine(dep_day, datetime.strptime(dep_hhmm, "%H:%M").time())
    tz_shift = AIRPORTS[destination]["utc"] - AIRPORTS[origin]["utc"]
    arr = dep + timedelta(minutes=block_minutes, hours=tz_shift)
    return dep.strftime("%Y-%m-%dT%H:%M"), arr.strftime("%Y-%m-%dT%H:%M")


def shift_minutes(local: str, minutes: int) -> str:
    return (datetime.strptime(local, "%Y-%m-%dT%H:%M") + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")


def make_code(rng: random.Random, used: set[str]) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(rng.choice(alphabet) for _ in range(6))
        if (code not in used and code != UNKNOWN_CONFIRMATION_CODE
                and any(ch.isdigit() for ch in code) and any(ch.isalpha() for ch in code)):
            used.add(code)
            return code


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_customers() -> list[dict[str, Any]]:
    rng = random.Random(SEED + 1)
    customers = []
    for i, (first, last, tier, home) in enumerate(CUSTOMERS_SEED, start=1):
        cid = f"CUST-{1000 + i}"
        loyalty = "CA8475921" if cid == "CUST-1007" else f"CA{rng.randint(1000000, 9999999)}"
        email_local = f"{first}.{last}".lower().replace("'", "")
        customers.append({
            "customerId": cid,
            "firstName": first,
            "lastName": last,
            "email": f"{email_local}@example.com",
            "phone": f"+1-555-01{rng.randint(0, 99):02d}",
            "loyaltyNumber": loyalty,
            "loyaltyTier": tier,
            "homeAirport": home,
            "memberSince": (date(2011, 1, 1) + timedelta(days=rng.randint(0, 5000))).isoformat(),
            "preferredContact": rng.choice(["Email", "App notification", "SMS"]),
        })
    return customers


def build_flights() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(SEED + 2)
    scenario_instances: list[tuple[str, int]] = list(SCENARIO_FLIGHTS)
    candidates: list[tuple[str, int]] = []
    for offset in DAY_RANGE:
        excl = SCENARIO_EXCLUSIONS.get(offset)
        for number, (origin, dest, *_rest) in SCHEDULE.items():
            if (number, offset) in SCENARIO_FLIGHTS:
                continue
            if excl and (origin in excl["origins"] or dest in excl["destinations"]):
                continue
            candidates.append((number, offset))
    # Keep every background disruption and reservation-referenced flight, then sample the rest.
    must_have = set(BACKGROUND_DISRUPTIONS) | REQUIRED_INSTANCES | HERO_DAY_SEA_DEPARTURES
    required = sorted(k for k in must_have if k in candidates)
    pool = [k for k in candidates if k not in must_have]
    needed = TARGET_FLIGHTS - len(scenario_instances) - len(required)
    chosen = scenario_instances + required + rng.sample(pool, needed)
    chosen.sort(key=lambda k: (k[1], SCHEDULE[k[0]][2], k[0]))

    flights, statuses = [], []
    for number, offset in chosen:
        origin, dest, dep_hhmm, block, equipment = SCHEDULE[number]
        dep_day = day(offset)
        dep_local, arr_local = local_times(origin, dest, dep_day, dep_hhmm, block)
        override = SCENARIO_FLIGHTS.get((number, offset)) or BACKGROUND_DISRUPTIONS.get((number, offset)) or Override()
        capacity = AIRCRAFT[equipment]["capacity"]
        if offset < 0 or override.status == "Cancelled":
            seats = {c: 0 for c in CABINS}  # departed or cancelled flights are closed for sale
        elif override.seats is not None:
            seats = dict(override.seats)
        else:
            seats = {c: rng.randint(0, max(2, capacity[c] // 4)) for c in CABINS}
            seats["Main Cabin"] = max(seats["Main Cabin"], rng.randint(4, 20))

        if override.status == "Cancelled":
            op_status = live_status = "Cancelled"
        elif offset < 0:
            op_status, live_status = "Completed", "Landed"
        elif override.status == "Delayed":
            op_status = live_status = "Delayed"
        else:
            op_status, live_status = "Scheduled", "On Time"

        flights.append({
            "flightNumber": number,
            "date": dep_day.isoformat(),
            "origin": origin,
            "destination": dest,
            "departureLocal": dep_local,
            "departureTimeZone": AIRPORTS[origin]["tz"],
            "arrivalLocal": arr_local,
            "arrivalTimeZone": AIRPORTS[dest]["tz"],
            "blockMinutes": block,
            "stops": 0,
            "aircraft": AIRCRAFT[equipment]["type"],
            "cabinAvailability": seats,
            "totalSeatsAvailable": sum(seats.values()),
            "operatingStatus": op_status,
            "operatedBy": "Contoso Air",
        })

        delay = override.delay_minutes
        cancelled = live_status == "Cancelled"
        if override.last_updated:
            updated_day, updated_time = override.last_updated
        elif offset < 0:
            updated_day, updated_time = offset, shift_minutes(arr_local, delay)[-5:]
        else:
            updated_day, updated_time = 0, "05:00"
        statuses.append({
            "flightNumber": number,
            "date": dep_day.isoformat(),
            "origin": origin,
            "destination": dest,
            "status": live_status,
            "scheduledDeparture": dep_local,
            "estimatedDeparture": None if cancelled else shift_minutes(dep_local, delay),
            "scheduledArrival": arr_local,
            "estimatedArrival": None if cancelled else shift_minutes(arr_local, delay),
            "delayMinutes": delay,
            "isCancelled": cancelled,
            "disruption": override.disruption,
            "lastUpdated": f"{day(updated_day).isoformat()}T{updated_time}",
        })
    return flights, statuses


def _passengers(rng: random.Random, primary: dict[str, Any], adults: int, children: int,
                fixed: list[tuple[str, str]] | None = None) -> list[dict[str, Any]]:
    people = [{"firstName": primary["firstName"], "lastName": primary["lastName"], "passengerType": "Adult",
               "loyaltyNumber": primary["loyaltyNumber"]}]
    if fixed:
        for first, ptype in fixed:
            people.append({"firstName": first, "lastName": primary["lastName"], "passengerType": ptype})
    else:
        firsts = rng.sample(COMPANION_FIRST["adult"], adults - 1) + rng.sample(COMPANION_FIRST["child"], children)
        types = ["Adult"] * (adults - 1) + ["Child"] * children
        for first, ptype in zip(firsts, types):
            people.append({"firstName": first, "lastName": primary["lastName"], "passengerType": ptype})
    for i, p in enumerate(people, start=1):
        p["passengerId"] = f"P{i}"
        p.setdefault("loyaltyNumber", None)
    return [{"passengerId": p["passengerId"], "firstName": p["firstName"], "lastName": p["lastName"],
             "passengerType": p["passengerType"], "loyaltyNumber": p["loyaltyNumber"]} for p in people]


def _segment(flight: dict[str, Any], cabin: str, seg_status: str, idx: int) -> dict[str, Any]:
    return {
        "segmentId": f"S{idx}",
        "flightNumber": flight["flightNumber"],
        "date": flight["date"],
        "origin": flight["origin"],
        "destination": flight["destination"],
        "scheduledDeparture": flight["departureLocal"],
        "scheduledArrival": flight["arrivalLocal"],
        "cabin": cabin,
        "segmentStatus": seg_status,
    }


def build_reservations(customers: list[dict[str, Any]], flights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rng = random.Random(SEED + 3)
    by_id = {c["customerId"]: c for c in customers}
    fl = {(f["flightNumber"], f["date"]): f for f in flights}
    used_codes: set[str] = {"CT8K2P"}
    today = ANCHOR_DATE.isoformat()

    def flight(number: str, offset: int) -> dict[str, Any]:
        return fl[(number, day(offset).isoformat())]

    def res(code, cid, passengers, segments, cabin, status, booked_days_ago, fare="Standard", notes=None):
        r = {
            "confirmationCode": code,
            "primaryCustomerId": cid,
            "bookingDate": day(-booked_days_ago).isoformat(),
            "status": status,
            "cabin": cabin,
            "fareType": fare,
            "passengers": passengers,
            "segments": segments,
        }
        if notes:
            r["notes"] = notes
        return r

    out: list[dict[str, Any]] = []
    # --- Scenario reservations -------------------------------------------------------
    hero = by_id["CUST-1007"]
    out.append(res("CT8K2P", "CUST-1007",
                   _passengers(rng, hero, 2, 2, fixed=[("Jamie", "Adult"), ("Taylor", "Child"), ("Jordan", "Child")]),
                   [_segment(flight("CT218", 1), "Economy Plus", "Confirmed", 1)], "Economy Plus", "Confirmed", 41))
    out.append(res(make_code(rng, used_codes), "CUST-1007", _passengers(rng, hero, 1, 0),
                   [_segment(flight("CT204", -11), "Economy Plus", "Flown", 1),
                    _segment(flight("CT207", -7), "Economy Plus", "Flown", 2)], "Economy Plus", "Completed", 30))
    b1 = by_id["CUST-1012"]
    out.append(res(make_code(rng, used_codes), "CUST-1012",
                   _passengers(rng, b1, 2, 2, fixed=[("Arjun", "Adult"), ("Anika", "Child"), ("Dev", "Child")]),
                   [_segment(flight("CT540", 1), "Main Cabin", "Confirmed", 1)], "Main Cabin", "Confirmed", 55))
    b2 = by_id["CUST-1015"]
    out.append(res(make_code(rng, used_codes), "CUST-1015", _passengers(rng, b2, 2, 0, fixed=[("Dana", "Adult")]),
                   [_segment(flight("CT610", 2), "Main Cabin", "Confirmed", 1)], "Main Cabin", "Confirmed", 20))
    b3 = by_id["CUST-1018"]
    out.append(res(make_code(rng, used_codes), "CUST-1018",
                   _passengers(rng, b3, 1, 2, fixed=[("Mila", "Child"), ("Ivan", "Child")]),
                   [_segment(flight("CT580", 3), "Main Cabin", "Confirmed", 1)], "Main Cabin", "Confirmed", 33))
    d1 = by_id["CUST-1019"]
    out.append(res(make_code(rng, used_codes), "CUST-1019", _passengers(rng, d1, 1, 0),
                   [_segment(flight("CT102", -10), "Main Cabin", "Flown", 1),
                    _segment(flight("CT105", -6), "Main Cabin", "Flown", 2)], "Main Cabin", "Completed", 45))
    out.append(res(make_code(rng, used_codes), "CUST-1019", _passengers(rng, d1, 1, 0),
                   [_segment(flight("CT118", 5), "Main Cabin", "Cancelled", 1)], "Main Cabin", "Cancelled", 14,
                   notes="Cancelled by customer; travel credit issued."))
    d3 = by_id["CUST-1021"]
    out.append(res(make_code(rng, used_codes), "CUST-1021", _passengers(rng, d3, 1, 0),
                   [_segment(flight("CT655", 1), "Economy Plus", "Confirmed", 1)], "Economy Plus", "Confirmed", 12))
    d4 = by_id["CUST-1024"]
    out.append(res(make_code(rng, used_codes), "CUST-1024", _passengers(rng, d4, 2, 0, fixed=[("Karim", "Adult")]),
                   [_segment(flight("CT472", 2), "First", "Cancelled", 1)], "First", "Confirmed", 26,
                   notes="Segment marked cancelled by schedule-change process; awaiting reaccommodation."))

    # --- Background reservations for the remaining customers ---------------------------
    background_customers = [c for c in customers if c["customerId"] not in SCENARIO_CUSTOMERS]
    scenario_keys = {(n, day(o).isoformat()) for n, o in SCENARIO_FLIGHTS}
    usable = [f for f in flights if (f["flightNumber"], f["date"]) not in scenario_keys
              and not (f["operatingStatus"] == "Cancelled" and f["date"] >= today)]

    # Two other parties are also booked on the cancelled CT218, as in a real disruption.
    for cust in background_customers[:2]:
        out.append(res(make_code(rng, used_codes), cust["customerId"], _passengers(rng, cust, rng.choice([1, 2]), 0),
                       [_segment(flight("CT218", 1), "Main Cabin", "Confirmed", 1)], "Main Cabin", "Confirmed",
                       rng.randint(7, 60)))

    def pick_return(outbound: dict[str, Any]) -> dict[str, Any] | None:
        options = [f for f in usable if f["origin"] == outbound["destination"]
                   and f["destination"] == outbound["origin"] and f["date"] > outbound["date"]]
        return rng.choice(options) if options else None

    def pick_connection(first: dict[str, Any]) -> dict[str, Any] | None:
        arr = datetime.fromisoformat(first["arrivalLocal"])
        options = [f for f in usable if f["origin"] == first["destination"] and f["date"] == first["date"]
                   and f["destination"] != first["origin"]
                   and 45 <= (datetime.fromisoformat(f["departureLocal"]) - arr).total_seconds() / 60 <= 300]
        return rng.choice(options) if options else None

    ci = 0
    while len(out) < TARGET_RESERVATIONS:
        cust = background_customers[ci % len(background_customers)]
        ci += 1
        outbound = rng.choice(usable)
        cabin = rng.choices(CABINS, weights=[1, 2, 5])[0]
        size = rng.choices([1, 2, 3, 4, 5], weights=[8, 6, 2, 2, 1])[0]
        adults = size if size <= 2 else rng.choice([2, size])
        children = size - adults
        legs = [outbound]
        shape = rng.choices(["oneway", "roundtrip", "connection"], weights=[4, 4, 2])[0]
        if shape == "roundtrip" and (ret := pick_return(outbound)):
            legs.append(ret)
        elif shape == "connection" and (nxt := pick_connection(outbound)):
            legs.append(nxt)
        last_day = max(f["date"] for f in legs)
        customer_cancelled = rng.random() < 0.1
        if customer_cancelled:
            status = "Cancelled"
        elif last_day < today:
            status = "Completed"
        else:
            status = "Confirmed"
        segments = []
        for idx, f in enumerate(legs, start=1):
            if customer_cancelled:
                s_status = "Cancelled"
            elif f["date"] < today:
                s_status = "Reaccommodated" if f["operatingStatus"] == "Cancelled" else "Flown"
            else:
                s_status = "Confirmed"
            segments.append(_segment(f, cabin, s_status, idx))
        days_until = (date.fromisoformat(outbound["date"]) - ANCHOR_DATE).days
        booked_ago = max(1, rng.randint(5, 90) - days_until)
        out.append(res(make_code(rng, used_codes), cust["customerId"], _passengers(rng, cust, adults, children),
                       segments, cabin, status, booked_ago,
                       fare=rng.choices(["Basic", "Standard", "Flexible"], weights=[2, 6, 2])[0],
                       notes="Cancelled by customer." if customer_cancelled else None))
    return out


def build_dataset() -> dict[str, Any]:
    customers = build_customers()
    flights, statuses = build_flights()
    reservations = build_reservations(customers, flights)
    meta = {
        "description": "Synthetic, fictional data for the Contoso Air Customer Care demo.",
        "generator": "data/generate_data.py",
        "seed": SEED,
        "anchorDate": ANCHOR_DATE.isoformat(),
        "dateNote": "Dates are relative to anchorDate (the dataset's 'today'). "
                    "The tools API rebases them so anchorDate maps to the real current date.",
    }
    return {
        "customers.json": {"metadata": {**meta, "count": len(customers)}, "customers": customers},
        "reservations.json": {"metadata": {**meta, "count": len(reservations)}, "reservations": reservations},
        "flights.json": {"metadata": {**meta, "count": len(flights), "airports": AIRPORTS}, "flights": flights},
        "flight-status.json": {"metadata": {**meta, "count": len(statuses)}, "flightStatus": statuses},
        "fault-injection.json": {
            "metadata": {**meta, "description": "Deterministic simulated outages used by evaluation scenario D3."},
            "faults": [{
                "endpoint": "flight-status",
                "flightNumber": "CT655",
                "date": day(1).isoformat(),
                "httpStatus": 503,
                "message": "The flight status service is temporarily unavailable. Please try again later.",
            }],
        },
    }


# ---------------------------------------------------------------------------
# Validation (also used by tests and scripts/validate.py)
# ---------------------------------------------------------------------------

def validate_dataset(ds: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    customers = ds["customers.json"]["customers"]
    reservations = ds["reservations.json"]["reservations"]
    flights = ds["flights.json"]["flights"]
    statuses = ds["flight-status.json"]["flightStatus"]
    anchor = date.fromisoformat(ds["flights.json"]["metadata"]["anchorDate"])
    tomorrow = (anchor + timedelta(days=1)).isoformat()

    def check(cond: bool, msg: str) -> None:
        if not cond:
            errors.append(msg)

    check(len(customers) == 30, f"expected 30 customers, found {len(customers)}")
    check(len(reservations) == 60, f"expected 60 reservations, found {len(reservations)}")
    check(len(flights) == 150, f"expected 150 flight instances, found {len(flights)}")
    check(len(statuses) == len(flights), "every flight instance needs a status record")
    check(len({c["customerId"] for c in customers}) == len(customers), "duplicate customer IDs")
    check(len({r["confirmationCode"] for r in reservations}) == len(reservations), "duplicate confirmation codes")
    keys = {(f["flightNumber"], f["date"]) for f in flights}
    check(len(keys) == len(flights), "duplicate flight instances")
    check({(s["flightNumber"], s["date"]) for s in statuses} == keys, "status records do not match flights")
    check({c["loyaltyTier"] for c in customers} == {"Basic", "Silver", "Gold", "Platinum"}, "all loyalty tiers needed")
    check({r["status"] for r in reservations} >= {"Confirmed", "Completed", "Cancelled"}, "reservation statuses missing")
    check(sum(1 for s in statuses if s["status"] == "Cancelled") >= 5, "need several cancelled flights")
    check(sum(1 for s in statuses if s["status"] == "Delayed") >= 2, "need several delayed flights")
    check(any(len(r["passengers"]) == 1 for r in reservations) and any(len(r["passengers"]) > 2 for r in reservations),
          "need single and multi-passenger reservations")
    check(len({f["origin"] for f in flights}) >= 8, "need multiple origins")
    check(all(r["confirmationCode"] != UNKNOWN_CONFIRMATION_CODE for r in reservations),
          "D1 unknown confirmation code must not exist")
    check(all(f["flightNumber"] != UNKNOWN_FLIGHT_NUMBER for f in flights), "D2 unknown flight must not exist")

    cust_ids = {c["customerId"] for c in customers}
    for r in reservations:
        check(r["primaryCustomerId"] in cust_ids, f"{r['confirmationCode']}: unknown customer")
        for s in r["segments"]:
            check((s["flightNumber"], s["date"]) in keys, f"{r['confirmationCode']}: segment flight missing")
    status_by_key = {(s["flightNumber"], s["date"]): s for s in statuses}
    for f in flights:
        check(f["totalSeatsAvailable"] == sum(f["cabinAvailability"].values()), f"{f['flightNumber']} seat total")
        check(f["arrivalLocal"] > f["departureLocal"], f"{f['flightNumber']} arrival before departure")
        st = status_by_key[(f["flightNumber"], f["date"])]
        check((f["operatingStatus"] == "Cancelled") == st["isCancelled"], f"{f['flightNumber']} status mismatch")

    # Hero invariants (spec sections 4-5)
    hero = next((c for c in customers if c["customerId"] == "CUST-1007"), {})
    check(hero.get("firstName") == "Alex" and hero.get("lastName") == "Johnson" and hero.get("loyaltyTier") == "Gold"
          and hero.get("loyaltyNumber") == "CA8475921" and hero.get("homeAirport") == "SEA"
          and hero.get("email") == "alex.johnson@example.com", "hero customer does not match spec")
    hero_res = next((r for r in reservations if r["confirmationCode"] == "CT8K2P"), None)
    check(hero_res is not None, "hero reservation CT8K2P missing")
    if hero_res:
        names = [(p["firstName"], p["passengerType"]) for p in hero_res["passengers"]]
        check(names == [("Alex", "Adult"), ("Jamie", "Adult"), ("Taylor", "Child"), ("Jordan", "Child")],
              "hero passengers do not match spec")
        seg = hero_res["segments"][0]
        check(hero_res["primaryCustomerId"] == "CUST-1007" and hero_res["cabin"] == "Economy Plus"
              and hero_res["status"] == "Confirmed" and seg["flightNumber"] == "CT218" and seg["date"] == tomorrow
              and (seg["origin"], seg["destination"]) == ("SEA", "JFK"), "hero reservation does not match spec")
    ct218 = status_by_key.get(("CT218", tomorrow), {})
    disruption = ct218.get("disruption") or {}
    check(ct218.get("status") == "Cancelled" and ct218.get("scheduledDeparture", "").endswith("T10:30")
          and disruption.get("responsibility") == "Carrier" and disruption.get("reason") == "Operational disruption",
          "CT218 status does not match spec")
    fmap = {(f["flightNumber"], f["date"]): f for f in flights}
    ct226 = fmap.get(("CT226", tomorrow), {})
    check(ct226.get("departureLocal", "").endswith("T09:20") and ct226.get("totalSeatsAvailable", 0) >= 4
          and ct226.get("cabinAvailability", {}).get("Economy Plus", 0) >= 4, "CT226 must seat four in Economy Plus")
    ct232 = fmap.get(("CT232", tomorrow), {})
    check(ct232.get("departureLocal", "").endswith("T15:45") and ct232.get("totalSeatsAvailable") == 3,
          "CT232 must have exactly three seats")
    ct310, ct442 = fmap.get(("CT310", tomorrow), {}), fmap.get(("CT442", tomorrow), {})
    connection = {c: min(ct310.get("cabinAvailability", {}).get(c, 0), ct442.get("cabinAvailability", {}).get(c, 0))
                  for c in CABINS}
    check(ct310.get("departureLocal", "").endswith("T07:10")
          and connection == {"First": 0, "Economy Plus": 2, "Main Cabin": 4},
          "CT310 + CT442 connection must have 0/2/4 seats (First/Economy Plus/Main Cabin) on every leg")
    hero_day = [f for f in flights if f["date"] == tomorrow]
    sea_jfk = sorted(f["flightNumber"] for f in hero_day if (f["origin"], f["destination"]) == ("SEA", "JFK"))
    check(sea_jfk == ["CT218", "CT226", "CT232"], f"unexpected SEA -> JFK flights on the hero day: {sea_jfk}")
    other_sea = [f for f in hero_day if f["origin"] == "SEA" and f["destination"] not in ("JFK", "ORD")]
    check(len(other_sea) >= 3, "the hero day needs ordinary, unrelated SEA departures")
    to_jfk_from = {f["origin"] for f in hero_day if f["destination"] == "JFK"}
    check(not to_jfk_from & {f["destination"] for f in other_sea},
          "background SEA departures must not create extra SEA -> JFK connections")
    return errors


def serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def write_dataset(ds: dict[str, Any]) -> None:
    for name, payload in ds.items():
        with open(DATA_DIR / name, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(serialize(payload))


def check_files(ds: dict[str, Any]) -> list[str]:
    problems = []
    for name, payload in ds.items():
        path = DATA_DIR / name
        if not path.exists():
            problems.append(f"{name} is missing; run python data/generate_data.py")
        elif path.read_text(encoding="utf-8").replace("\r\n", "\n") != serialize(payload):
            problems.append(f"{name} is out of date; run python data/generate_data.py")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify committed files are current and valid")
    args = parser.parse_args()
    ds = build_dataset()
    errors = validate_dataset(ds)
    if errors:
        print("Dataset validation FAILED:\n  - " + "\n  - ".join(errors))
        return 1
    if args.check:
        problems = check_files(ds)
        if problems:
            print("\n".join(problems))
            return 1
        print("Synthetic data is current and valid.")
        return 0
    write_dataset(ds)
    counts = {k: v["metadata"].get("count", len(v.get("faults", []))) for k, v in ds.items()}
    print(f"Wrote synthetic dataset to {DATA_DIR}: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
