"""Deterministic synthetic data generator for the Contoso Insurance claims demo.

Every person, address, vehicle, VIN, policy and claim produced here is fictional.
Contoso Insurance is a fictional company.

Run from the contoso-claims-processing/ directory:

    python data/generate_data.py           # (re)write data/*.json
    python data/generate_data.py --check   # verify the committed files are current

The output is fully determined by SEED and the hand-authored records below, so the
same code always produces byte-identical files. Dates are static (records are as of
RECORDS_AS_OF); nothing depends on the current date or time.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SEED = 20261120
RECORDS_AS_OF = "2026-11-20T08:00:00Z"
AS_OF = date(2026, 11, 20)
CLAIMS_SYSTEM_START = date(2023, 1, 1)
DATA_DIR = Path(__file__).resolve().parent

SYNTHETIC_NOTICE = (
    "Synthetic demonstration data. Contoso Insurance is fictional; every customer, "
    "policy, vehicle, VIN, claim and address in this file is invented."
)

# ---------------------------------------------------------------------------
# Reference tables (all fictional)
# ---------------------------------------------------------------------------

# city -> (state, IANA time zone, ZIP prefix, phone area code)
CITIES = {
    "Maple Harbor": ("OR", "America/Los_Angeles", "974", "541"),
    "Brightwater": ("OR", "America/Los_Angeles", "973", "503"),
    "Riverton Falls": ("OR", "America/Los_Angeles", "975", "541"),
    "Pine Hollow": ("WA", "America/Los_Angeles", "983", "360"),
    "Eastgate Springs": ("ID", "America/Boise", "836", "208"),
    "Sunvale": ("CA", "America/Los_Angeles", "956", "530"),
    "Copper Mesa": ("AZ", "America/Phoenix", "852", "928"),
    "Lakeshore Bluffs": ("CO", "America/Denver", "805", "970"),
    "Granite Bend": ("NV", "America/Los_Angeles", "894", "775"),
    "Willow Crossing": ("UT", "America/Denver", "840", "435"),
}

STREET_NAMES = [
    "Alder", "Aspen", "Bayview", "Birch", "Cascade", "Cedar", "Elm", "Fir", "Harbor",
    "Hawthorne", "Juniper", "Lakeview", "Larch", "Madrona", "Orchard", "Ridgecrest",
    "Sequoia", "Summit", "Tamarack", "Willow",
]
STREET_SUFFIXES = ["St", "Ave", "Ln", "Dr", "Ct", "Way", "Pl"]

FIRST_NAMES = [
    "Alex", "Avery", "Blake", "Cameron", "Dakota", "Devon", "Elliot", "Emerson", "Finley",
    "Harper", "Hayden", "Jamie", "Kendall", "Logan", "Parker", "Peyton", "Quinn", "Reese",
    "Riley", "Rowan", "Sage", "Skyler", "Taylor", "Drew", "Ari", "Noor", "Priya", "Mateo",
    "Lena", "Tomas", "Mei", "Sofia", "Omar", "Yuki", "Daniel", "Grace", "Nadia", "Ivan",
    "Leah", "Marisol",
]
LAST_NAMES = [
    "Alvarez", "Bennett", "Brooks", "Castillo", "Chen", "Dawson", "Ellis", "Fischer",
    "Garcia", "Hughes", "Ibarra", "Jensen", "Kim", "Larsen", "Mendez", "Nakamura", "Novak",
    "Okafor", "Patel", "Quintero", "Ramirez", "Sato", "Schmidt", "Silva", "Sullivan",
    "Tanaka", "Turner", "Varga", "Walsh", "Yilmaz", "Young", "Zhou", "Hart", "Rivera",
    "Foster", "Morales", "Lindqvist", "Baker", "Price", "Moreno",
]
# Names used only for other drivers involved in losses (never Contoso customers).
OTHER_PARTY_FIRST = ["Robin", "Jesse", "Shawn", "Kai", "Remy", "Lou", "Toni", "Sam", "Frankie", "Jordy"]
OTHER_PARTY_LAST = ["Abbott", "Cruz", "Delgado", "Ferris", "Holt", "Keane", "Marsh", "Pruitt", "Soto", "Vance"]
OTHER_INSURERS = [
    "Northwind Mutual Insurance", "Tailspin Casualty Company", "Proseware Insurance",
    "Relecloud Auto Insurance", "Lamna Insurance Group",
]
LENDERS = ["Woodgrove Bank", "Proseware Financial", "Fabrikam Motor Credit", "Northwind Auto Finance"]
LESSORS = ["Fabrikam Motor Credit", "Northwind Auto Finance", "Woodgrove Bank"]

COLORS = [
    "Glacier White", "Graphite Gray Metallic", "Midnight Black", "Silver Mist Metallic",
    "Ruby Red", "Evergreen Pearl", "Sandstone Beige", "Harbor Blue Metallic",
]

# make -> (VIN world manufacturer identifier, plant code)
MAKES = {
    "Contoso": ("0CT", "M"), "Fabrikam": ("0FB", "F"), "Northwind": ("0NW", "N"),
    "Litware": ("0LW", "L"), "Adatum": ("0AD", "D"), "Tailspin": ("0TS", "T"),
}

# (make, model, model code, body style, body code, trims, fuel type, first year, last year)
MODELS = [
    ("Contoso", "Trailstar", "TS", "Sport utility vehicle, 4-door", "U",
     [("Base", "FWD"), ("Touring", "AWD"), ("Summit", "AWD")], "Gasoline", 2017, 2026),
    ("Contoso", "Aria", "AR", "Sedan, 4-door", "S", [("S", "FWD"), ("SE", "FWD")], "Gasoline", 2012, 2025),
    ("Contoso", "Lumen", "LM", "Hatchback, 5-door", "H",
     [("Standard Range", "RWD"), ("Long Range", "AWD")], "Electric", 2021, 2026),
    ("Fabrikam", "Ridgeback", "RB", "Pickup, crew cab", "P", [("XL", "4WD"), ("Trail", "4WD")], "Gasoline", 2014, 2025),
    ("Fabrikam", "Coastal", "CS", "Minivan", "M", [("LX", "FWD"), ("Touring", "FWD")], "Hybrid", 2015, 2026),
    ("Northwind", "Breeze", "BZ", "Sedan, 4-door", "S", [("LE", "FWD"), ("XLE", "FWD")], "Hybrid", 2012, 2026),
    ("Northwind", "Kestrel", "KS", "Sport utility vehicle, 4-door", "U",
     [("Sport", "AWD"), ("Limited", "AWD")], "Gasoline", 2016, 2026),
    ("Litware", "Pulse", "PL", "Hatchback, 5-door", "H", [("Base", "FWD"), ("Sport", "FWD")], "Gasoline", 2013, 2024),
    ("Litware", "Solace", "SL", "Sedan, 4-door", "S", [("Premium", "AWD")], "Gasoline", 2018, 2026),
    ("Adatum", "Haven", "HV", "Minivan", "M", [("Plus", "FWD")], "Gasoline", 2014, 2025),
    ("Adatum", "Strider", "SD", "Pickup, extended cab", "P", [("Work", "RWD"), ("Sport", "4WD")], "Gasoline", 2012, 2024),
    ("Tailspin", "Glide", "GL", "Coupe, 2-door", "C", [("GT", "RWD")], "Gasoline", 2016, 2025),
]
MODEL_BY_NAME = {(m[0], m[1]): m for m in MODELS}

# Model-year codes (VIN position 10)
YEAR_CODES = {2012: "C", 2013: "D", 2014: "E", 2015: "F", 2016: "G", 2017: "H", 2018: "J",
              2019: "K", 2020: "L", 2021: "M", 2022: "N", 2023: "P", 2024: "R", 2025: "S", 2026: "T"}

REPAIR_FACILITIES = [
    # id, estimate prefix, name, services, network, joined, street, city, phone line, rates
    ("RF-101", "BW", "Brightwater Collision & Glass", ["Collision repair", "Auto glass"],
     "Contoso Direct Repair Network", "2017-03-01", "915 Cedar Ave", "Brightwater", 1, (66, 66, 120, 82, 44)),
    ("RF-102", "PH", "Pine Hollow Auto Body", ["Collision repair"],
     "Independent", None, "2210 Ridgecrest Dr", "Pine Hollow", 2, (72, 72, 135, 90, 48)),
    ("RF-103", "RF", "Riverton Falls Collision Center", ["Collision repair"],
     "Contoso Direct Repair Network", "2019-06-15", "48 Orchard Way", "Riverton Falls", 3, (64, 64, 118, 80, 43)),
    ("RF-104", "HL", "Harborline Auto Body & Paint", ["Collision repair", "Refinish", "ADAS calibration coordination"],
     "Contoso Direct Repair Network", "2016-09-01", "3140 Bayview Dr", "Maple Harbor", 4, (68, 68, 125, 85, 46)),
    ("RF-105", "ES", "Eastgate Springs Body Works", ["Collision repair"],
     "Contoso Direct Repair Network", "2020-02-01", "771 Aspen St", "Eastgate Springs", 5, (60, 60, 110, 78, 40)),
    ("RF-106", "SV", "Sunvale Precision Collision", ["Collision repair", "Refinish"],
     "Contoso Direct Repair Network", "2018-11-01", "5600 Summit Ave", "Sunvale", 6, (78, 78, 145, 98, 52)),
    ("RF-107", "CM", "Copper Mesa Auto Glass", ["Auto glass"],
     "Contoso Direct Repair Network", "2021-04-01", "1302 Juniper Ln", "Copper Mesa", 7, (70, 70, 120, 0, 0)),
    ("RF-108", "LB", "Lakeshore Bluffs Collision", ["Collision repair"],
     "Independent", None, "389 Lakeview Dr", "Lakeshore Bluffs", 8, (70, 70, 130, 88, 47)),
    ("RF-109", "GB", "Granite Bend Glass & Body", ["Collision repair", "Auto glass"],
     "Contoso Direct Repair Network", "2016-05-01", "64 Elm Ct", "Granite Bend", 9, (69, 69, 128, 86, 46)),
    ("RF-110", "WC", "Willow Crossing Autoworks", ["Collision repair", "Mechanical repair"],
     "Independent", None, "1188 Willow Pl", "Willow Crossing", 10, (62, 62, 115, 80, 42)),
]
FACILITY_PREFIX = {f[0]: f[1] for f in REPAIR_FACILITIES}

COVERAGE_NAMES = {
    "BI": "Bodily Injury Liability",
    "PD": "Property Damage Liability",
    "UMBI": "Uninsured/Underinsured Motorist Bodily Injury",
    "PIP": "Personal Injury Protection",
    "MED": "Medical Payments",
    "COLL": "Collision",
    "COMP": "Comprehensive (Other Than Collision)",
    "RENT": "Rental Reimbursement",
    "ROAD": "Roadside Assistance",
    "GAP": "Loan/Lease Gap",
}
PIP_STATES = {"OR": 15000, "WA": 10000, "UT": 3000}
LIABILITY_TIERS = [  # (BI per person, BI per accident, PD per accident, weight)
    (50000, 100000, 50000, 3),
    (100000, 300000, 100000, 5),
    (250000, 500000, 250000, 2),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def rng_for(name: str) -> random.Random:
    """Independent deterministic stream per section, so editing one section does not reshuffle others."""
    return random.Random(f"{SEED}:{name}")


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_z(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def local_to_utc(d: date, hhmm: str, tz: str) -> datetime:
    hour, minute = (int(p) for p in hhmm.split(":"))
    return datetime.combine(d, time(hour, minute), tzinfo=ZoneInfo(tz)).astimezone(timezone.utc)


def add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, d.day)  # day is always <= 28 for generated inception dates


def rand_date(rng: random.Random, lo: date, hi: date) -> date:
    """Uniform date in [lo, hi] (inclusive)."""
    if hi < lo:
        raise ValueError(f"empty date range {lo}..{hi}")
    return lo + timedelta(days=rng.randint(0, (hi - lo).days))


def money(value: float) -> float:
    return round(value + 1e-9, 2)


VIN_TRANSLIT = {**{str(i): i for i in range(10)},
                "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
                "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
                "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9}
VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def vin_check_digit(vin: str) -> str:
    total = sum(VIN_TRANSLIT[c] * w for c, w in zip(vin, VIN_WEIGHTS))
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def make_vin(make: str, model_code: str, trim_index: int, body_code: str, year: int, serial: str) -> str:
    """17-character synthetic VIN. World manufacturer identifiers begin with '0', which is not
    assigned to any real manufacturer, so these VINs cannot match a real vehicle."""
    wmi, plant = MAKES[make]
    partial = f"{wmi}{model_code}{trim_index + 1}{body_code}A0{YEAR_CODES[year]}{plant}{serial}"
    return partial[:8] + vin_check_digit(partial) + partial[9:]


def rear_closure(body_style: str) -> str:
    if body_style.startswith(("Sedan", "Coupe")):
        return "Trunk lid"
    if body_style.startswith("Pickup"):
        return "Tailgate"
    return "Liftgate"


class Phones:
    """Allocates unique fictional phone numbers in the reserved 555-0100..555-0199 range."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.used: set[str] = set()

    def take(self, area: str, line: int | None = None) -> str:
        while True:
            n = line if line is not None else self.rng.randint(100, 199)
            number = f"({area}) 555-0{n:03d}"
            if number not in self.used:
                self.used.add(number)
                return number
            if line is not None:
                raise ValueError(f"phone number collision: {number}")


def address(rng: random.Random, city: str) -> dict:
    state, _tz, zip_prefix, _area = CITIES[city]
    return {
        "street": f"{rng.randint(12, 9890)} {rng.choice(STREET_NAMES)} {rng.choice(STREET_SUFFIXES)}",
        "city": city,
        "state": state,
        "postalCode": f"{zip_prefix}{rng.randint(1, 99):02d}",
    }


# ---------------------------------------------------------------------------
# Repair facilities
# ---------------------------------------------------------------------------


def build_repair_facilities(phones: Phones) -> list[dict]:
    rng = rng_for("facilities")
    out = []
    for fid, _prefix, name, services, network, joined, street, city, phone_line, rates in REPAIR_FACILITIES:
        state, _tz, zip_prefix, area = CITIES[city]
        body, refinish, mechanical, frame, materials = rates
        out.append({
            "repairFacilityId": fid,
            "name": name,
            "services": services,
            "networkStatus": network,
            "networkJoinedDate": joined,
            "address": {"street": street, "city": city, "state": state,
                        "postalCode": f"{zip_prefix}{rng.randint(1, 99):02d}"},
            "phone": phones.take(area, 100 + phone_line),
            "laborRates": {
                "bodyPerHour": float(body),
                "refinishPerHour": float(refinish),
                "mechanicalPerHour": float(mechanical),
                "framePerHour": float(frame) if frame else None,
                "paintMaterialsPerRefinishHour": float(materials) if materials else None,
            },
        })
    return out


# ---------------------------------------------------------------------------
# Hero records (hand-authored; see docs/IMPLEMENTATION-SPEC.md sections 6-9 and 25-27)
# ---------------------------------------------------------------------------

HERO_CUSTOMER = {
    "customerId": "CUST-24817",
    "firstName": "Jordan",
    "lastName": "Lee",
    "address": {"street": "418 Tamarack Ct", "city": "Maple Harbor", "state": "OR", "postalCode": "97431"},
    "phoneLine": 148,
    "email": "jordan.lee@example.com",
    "preferredContactMethod": "Email",
}
HERO_POLICY_ID = "PAP-4471920"
HERO_VEHICLE_ID = "VEH-58213"
HERO_PRIOR_VEHICLE_ID = "VEH-51946"
HERO_CLAIM_ID = "CLM-10482"


def hero_vehicles() -> list[dict]:
    return [
        {
            "vehicleId": HERO_VEHICLE_ID,
            "vin": make_vin("Contoso", "TS", 1, "U", 2024, "318057"),
            "year": 2024, "make": "Contoso", "model": "Trailstar", "trim": "Touring",
            "bodyStyle": "Sport utility vehicle, 4-door",
            "exteriorColor": "Harbor Blue Metallic",
            "drivetrain": "AWD", "fuelType": "Gasoline",
            "ownerCustomerId": HERO_CUSTOMER["customerId"],
            "acquiredDate": "2024-05-18", "disposedDate": None,
            "ownership": {"type": "Financed", "lienholder": "Woodgrove Bank"},
            "primaryUse": "Commute",
            "garaging": {"city": "Maple Harbor", "state": "OR"},
            "equipment": ["LED headlamps", "LED tail lamps", "Rear camera", "Rear parking sensors",
                          "Blind-spot monitoring", "Lane-keeping assist", "Adaptive cruise control",
                          "Power liftgate", "Roof rails"],
        },
        {
            "vehicleId": HERO_PRIOR_VEHICLE_ID,
            "vin": make_vin("Northwind", "BZ", 0, "S", 2017, "260941"),
            "year": 2017, "make": "Northwind", "model": "Breeze", "trim": "LE",
            "bodyStyle": "Sedan, 4-door",
            "exteriorColor": "Silver Mist Metallic",
            "drivetrain": "FWD", "fuelType": "Hybrid",
            "ownerCustomerId": HERO_CUSTOMER["customerId"],
            "acquiredDate": "2019-07-02", "disposedDate": "2024-05-18",
            "ownership": {"type": "Owned", "lienholder": None},
            "primaryUse": "Commute",
            "garaging": {"city": "Maple Harbor", "state": "OR"},
            "equipment": ["Halogen headlamps", "Rear camera"],
        },
    ]


def coverage(code: str, deductible: float | None = None, limits: list[tuple[str, float]] | None = None) -> dict:
    return {
        "coverageCode": code,
        "coverageName": COVERAGE_NAMES[code],
        "deductible": float(deductible) if deductible is not None else None,
        "limits": [{"limitType": t, "amount": float(a)} for t, a in (limits or [])],
    }


def hero_policy() -> dict:
    full = lambda: [  # noqa: E731
        coverage("COLL", 1000), coverage("COMP", 500),
        coverage("RENT", None, [("Per day", 40), ("Maximum per loss", 1200)]),
        coverage("ROAD", None, [("Per occurrence", 100)]),
    ]
    return {
        "policyId": HERO_POLICY_ID,
        "customerId": HERO_CUSTOMER["customerId"],
        "productName": "Contoso Insurance Personal Auto Policy",
        "status": "Active",
        "ratingState": "OR",
        "inceptionDate": "2022-04-01",
        "termMonths": 12,
        "termEffectiveDate": "2026-04-01",
        "termExpirationDate": "2027-04-01",
        "cancellation": None,
        "paymentPlan": "Monthly",
        "termPremium": 1684.20,
        "drivers": [{"fullName": "Jordan Lee", "relationship": "Named insured", "licenseState": "OR"}],
        "policyCoverages": [
            coverage("BI", None, [("Per person", 100000), ("Per accident", 300000)]),
            coverage("PD", None, [("Per accident", 100000)]),
            coverage("UMBI", None, [("Per person", 100000), ("Per accident", 300000)]),
            coverage("PIP", None, [("Per person", 15000)]),
        ],
        "vehicles": [
            {"vehicleId": HERO_PRIOR_VEHICLE_ID, "addedDate": "2022-04-01", "removedDate": "2024-05-18",
             "lossPayee": None, "coverages": full()},
            {"vehicleId": HERO_VEHICLE_ID, "addedDate": "2024-05-18", "removedDate": None,
             "lossPayee": "Woodgrove Bank", "coverages": full()},
        ],
    }


HERO_CLAIMS = [
    {
        # The current claim (spec section 27). Facts only: no assessment fields.
        "claimId": HERO_CLAIM_ID,
        "vehicleId": HERO_VEHICLE_ID,
        "claimType": "Collision",
        "causeOfLoss": "Two-vehicle collision",
        "status": "In Review",
        "lossDate": "2026-11-12", "lossTime": "14:25",
        "lossLocation": {"description": "Harbor Point Shopping Center parking lot",
                         "street": "2200 block of Harbor Ave", "city": "Maple Harbor", "state": "OR"},
        "reportedLocal": ("2026-11-12", "19:05"),
        "reportChannel": "Online",
        "description": (
            "I was driving slowly through the Harbor Point Shopping Center parking lot looking for a space. "
            "A gray pickup truck backed out of a parking space on my right and hit the back right corner of "
            "my SUV. The rear bumper is pushed in, the back right side panel is dented and scraped, and the "
            "right taillight is broken. Nobody was hurt. The other driver and I exchanged information, and a "
            "police officer came and took a report."
        ),
        "reportedDamage": {
            "summary": "Rear bumper pushed in at the right corner; right rear quarter panel dented and scraped; "
                       "right tail lamp broken.",
            "areas": ["Rear bumper", "Right rear quarter panel", "Right tail lamp"],
        },
        "vehicleDrivable": True,
        "injuriesReported": False,
        "otherParties": [{"role": "Other driver", "name": "Casey Morgan",
                          "vehicleDescription": "2021 Fabrikam Ridgeback pickup, gray",
                          "insurer": "Northwind Mutual Insurance"}],
        "policeReport": {"reportedToPolice": True, "agency": "Maple Harbor Police Department",
                         "reportNumber": "MHPD-26-018734"},
        "repairFacilityId": "RF-104",
        "estimate": {"estimateId": "EST-HL-26-3391", "repairFacilityId": "RF-104",
                     "estimateDate": "2026-11-16", "grossAmount": 7850.00},
        "documents": [
            ("Claim form", "Auto claim - first notice of loss (online submission)", "Policyholder", "2026-11-13T03:05:00Z"),
            ("Photograph", "Right rear corner, three-quarter view", "Policyholder", "2026-11-13T03:05:00Z"),
            ("Photograph", "Right rear corner, close view", "Policyholder", "2026-11-13T03:05:00Z"),
            ("Photograph", "Rear of vehicle", "Policyholder", "2026-11-13T03:05:00Z"),
            ("Photograph", "Right side of vehicle", "Policyholder", "2026-11-13T03:05:00Z"),
            ("Photograph", "Front and left side of vehicle", "Policyholder", "2026-11-13T03:05:00Z"),
            ("Police report", "Maple Harbor Police Department traffic collision report MHPD-26-018734",
             "Police agency", "2026-11-17T16:40:00Z"),
            ("Repair estimate", "Repair estimate EST-HL-26-3391", "Repair facility", "2026-11-17T18:22:00Z"),
        ],
        "settlement": None, "closedDate": None, "closureReason": None,
        "lastUpdatedAt": "2026-11-17T18:22:00Z",
    },
    {
        "claimId": None,  # assigned by reported order
        "vehicleId": HERO_VEHICLE_ID,
        "claimType": "Comprehensive",
        "causeOfLoss": "Glass breakage",
        "status": "Closed - Paid",
        "lossDate": "2025-03-04", "lossTime": "08:40",
        "lossLocation": {"description": "Coast Highway northbound near Brightwater", "street": None,
                         "city": "Brightwater", "state": "OR"},
        "reportedLocal": ("2025-03-04", "17:20"),
        "reportChannel": "Phone",
        "description": "A rock thrown up by a truck on Coast Highway hit the windshield. "
                       "There is a crack on the passenger side that is spreading.",
        "reportedDamage": {"summary": "Cracked windshield.", "areas": ["Windshield"]},
        "vehicleDrivable": True,
        "injuriesReported": False,
        "otherParties": [],
        "policeReport": {"reportedToPolice": False, "agency": None, "reportNumber": None},
        "repairFacilityId": "RF-101",
        "estimate": {"estimateId": "EST-BW-25-0418", "repairFacilityId": "RF-101",
                     "estimateDate": "2025-03-06", "grossAmount": 1180.00},
        "documents": [
            ("Claim form", "Auto claim - first notice of loss (phone)", "Contoso Insurance", "2025-03-05T01:20:00Z"),
            ("Photograph", "Photograph 1 of 2", "Policyholder", "2025-03-05T16:02:00Z"),
            ("Photograph", "Photograph 2 of 2", "Policyholder", "2025-03-05T16:02:00Z"),
            ("Repair estimate", "Repair estimate EST-BW-25-0418", "Repair facility", "2025-03-06T21:15:00Z"),
            ("Repair invoice", "Final repair invoice", "Repair facility", "2025-03-13T19:30:00Z"),
        ],
        "settlement": {"settledAmount": 1180.00, "deductibleApplied": 500.00, "totalPaid": 680.00},
        "closedDate": "2025-03-14", "closureReason": "Payment issued",
        "lastUpdatedAt": "2025-03-14T17:45:00Z",
    },
]


# ---------------------------------------------------------------------------
# Background customers, vehicles and policies
# ---------------------------------------------------------------------------

# Customer slots (index 0 is the hero). Indexes are internal to the generator.
HIST_EXPIRED = range(1, 7)        # previous Expired policy, now on a new Active policy
HIST_CANCELLED = range(7, 11)     # previous Cancelled policy, now on a new Active policy
NOW_EXPIRED = (26, 27)            # only policy is Expired
NOW_CANCELLED = (28, 29)          # only policy is Cancelled
TWO_VEHICLES = {3, 8, 16, 22}
FULL_COVERAGE_REQUIRED = {11, 12, 13, 14, 15, 26, 28}
NO_CLAIMS = set(range(20, 26))


def pick_model(rng: random.Random, acquired: date, prefer_new: bool) -> tuple[tuple, int]:
    while True:
        model = rng.choice(MODELS)
        first, last = model[7], model[8]
        lo = max(first, acquired.year - 10)
        hi = min(last, acquired.year + 1)
        if lo > hi:
            continue
        new_years = [y for y in (acquired.year, acquired.year + 1) if lo <= y <= hi]
        if prefer_new and new_years:
            return model, rng.choice(new_years)
        return model, rng.randint(lo, hi)


def equipment_for(rng: random.Random, model: tuple, year: int) -> list[str]:
    body = model[3]
    items = ["LED headlamps" if year >= 2020 else "Halogen headlamps"]
    if year >= 2018:
        items.append("Rear camera")
    optional = ["Blind-spot monitoring", "Rear parking sensors", "Lane-keeping assist",
                "Adaptive cruise control", "Heated seats", "Sunroof"]
    if body.startswith(("Sport utility", "Minivan")):
        optional.append("Power liftgate")
    if body.startswith("Pickup"):
        optional.append("Tow package")
    if year >= 2018:
        items.extend(sorted(rng.sample(optional, rng.randint(1, 3)), key=optional.index))
    return items


def coverage_profile(rng: random.Random, vehicle: dict, force_full: bool) -> list[dict]:
    age = AS_OF.year - vehicle["year"]
    owned = vehicle["ownership"]["type"] == "Owned"
    roll = rng.random()
    if not force_full and owned and age >= 9 and roll < 0.45:
        return []  # liability only
    covs = []
    if force_full or not (owned and age >= 9 and roll < 0.55):
        covs.append(coverage("COLL", rng.choices([250, 500, 1000, 1500, 2000], [1, 5, 5, 2, 1])[0]))
    covs.append(coverage("COMP", rng.choices([100, 250, 500, 1000], [1, 3, 5, 2])[0]))
    if rng.random() < 0.6:
        per_day = rng.choice([30, 40, 50])
        covs.append(coverage("RENT", None, [("Per day", per_day), ("Maximum per loss", per_day * 30)]))
    if rng.random() < 0.5:
        covs.append(coverage("ROAD", None, [("Per occurrence", 100)]))
    if not owned and vehicle["year"] >= 2021 and rng.random() < 0.5 and covs[0]["coverageCode"] == "COLL":
        covs.append(coverage("GAP"))
    return covs


def policy_coverages(rng: random.Random, state: str) -> tuple[list[dict], float]:
    bi_pp, bi_pa, pd, _w = rng.choices(LIABILITY_TIERS, [t[3] for t in LIABILITY_TIERS])[0]
    covs = [
        coverage("BI", None, [("Per person", bi_pp), ("Per accident", bi_pa)]),
        coverage("PD", None, [("Per accident", pd)]),
        coverage("UMBI", None, [("Per person", bi_pp), ("Per accident", bi_pa)]),
    ]
    if state in PIP_STATES:
        covs.append(coverage("PIP", None, [("Per person", PIP_STATES[state])]))
    else:
        covs.append(coverage("MED", None, [("Per person", rng.choice([1000, 5000, 10000]))]))
    tier_factor = {50000: 1.0, 100000: 1.15, 250000: 1.35}[bi_pp]
    return covs, tier_factor


def premium(rng: random.Random, tier_factor: float, vehicle_coverages: list[list[dict]], term_months: int) -> float:
    annual = 0.0
    for covs in vehicle_coverages:
        annual += 640 * tier_factor
        for c in covs:
            code, ded = c["coverageCode"], c["deductible"]
            if code == "COLL":
                annual += 520 * {250: 1.35, 500: 1.15, 1000: 0.9, 1500: 0.8, 2000: 0.72}[int(ded)]
            elif code == "COMP":
                annual += 180 * {100: 1.4, 250: 1.15, 500: 1.0, 1000: 0.8}[int(ded)]
            elif code == "RENT":
                annual += 48
            elif code == "ROAD":
                annual += 22
            elif code == "GAP":
                annual += 60
    annual *= rng.uniform(0.92, 1.08)
    return money(annual * term_months / 12)


def terms_until(inception: date, months: int, end: date) -> list[tuple[date, date]]:
    """All policy terms starting before `end`."""
    out, k = [], 0
    while True:
        start = add_months(inception, k * months)
        if start >= end:
            return out
        out.append((start, add_months(inception, (k + 1) * months)))
        k += 1


def term_containing(inception: date, months: int, d: date) -> tuple[date, date]:
    return terms_until(inception, months, d + timedelta(days=1))[-1]


def build_people_vehicles_policies(phones: Phones) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Returns customers, vehicles, policies and internal per-customer plans (for claims)."""
    rng = rng_for("customers")
    vrng = rng_for("vehicles")
    prng = rng_for("policies")

    used_names = {("Jordan", "Lee"), ("Casey", "Morgan")}
    used_ids = {HERO_CUSTOMER["customerId"]}
    used_vehicle_ids = {HERO_VEHICLE_ID, HERO_PRIOR_VEHICLE_ID}
    used_policy_ids = {HERO_POLICY_ID}
    used_serials: set[str] = set()

    customers, vehicles, policies, plans = [], [], [], []

    # Hero
    hero = dict(HERO_CUSTOMER)
    hero_phone = phones.take("541", hero.pop("phoneLine"))
    customers.append({
        "customerId": hero["customerId"], "firstName": hero["firstName"], "lastName": hero["lastName"],
        "fullName": f"{hero['firstName']} {hero['lastName']}", "customerSince": "2022-04-01",
        "address": hero["address"], "phone": hero_phone, "email": hero["email"],
        "preferredContactMethod": hero["preferredContactMethod"],
        "policyIds": [HERO_POLICY_ID], "vehicleIds": [HERO_VEHICLE_ID, HERO_PRIOR_VEHICLE_ID],
    })
    vehicles.extend(hero_vehicles())
    policies.append(hero_policy())
    plans.append({"index": 0, "customerId": hero["customerId"], "policies": [policies[0]]})

    def new_id(prefix: str, lo: int, hi: int, used: set[str], width: int | None = None) -> str:
        while True:
            n = rng.randint(lo, hi)
            value = f"{prefix}{n:0{width}d}" if width else f"{prefix}{n}"
            if value not in used:
                used.add(value)
                return value

    def new_vehicle_id() -> str:
        while True:
            value = f"VEH-{vrng.randint(50000, 59999)}"
            if value not in used_vehicle_ids:
                used_vehicle_ids.add(value)
                return value

    def new_serial() -> str:
        while True:
            s = f"{vrng.randint(100000, 999999)}"
            if s not in used_serials and "10482" not in s:
                used_serials.add(s)
                return s

    for idx in range(1, 30):
        while True:
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            if (first, last) not in used_names:
                used_names.add((first, last))
                break
        city = rng.choice(list(CITIES))
        state, _tz, _zip, area = CITIES[city]
        customer_id = new_id("CUST-", 10000, 39999, used_ids)

        # --- policy timeline -------------------------------------------------
        timeline = []  # list of dicts: inception, months, status, end, cancellation
        if idx in HIST_EXPIRED or idx in HIST_CANCELLED:
            h_inc = rand_date(prng, date(2016, 3, 1), date(2019, 12, 28)).replace(day=prng.randint(1, 28))
            h_months = prng.choice([6, 12, 12])
            if idx in HIST_EXPIRED:
                n_terms = prng.randint(2, 6) * (12 // h_months)
                h_end = add_months(h_inc, n_terms * h_months)
                timeline.append({"inception": h_inc, "months": h_months, "status": "Expired", "end": h_end,
                                 "cancellation": None})
                gap = prng.choice([0, 0, prng.randint(14, 120)])
            else:
                h_end = rand_date(prng, add_months(h_inc, 8), add_months(h_inc, 40))
                reason = "Rewritten to new policy" if idx in (7, 8) else "Non-payment of premium"
                timeline.append({"inception": h_inc, "months": h_months, "status": "Cancelled", "end": h_end,
                                 "cancellation": {"effectiveDate": iso(h_end), "reason": reason}})
                gap = 0 if reason == "Rewritten to new policy" else prng.randint(20, 150)
            c_inc = h_end + timedelta(days=gap)
            if c_inc.day > 28:
                c_inc = c_inc.replace(day=28)
            timeline.append({"inception": c_inc, "months": prng.choice([6, 12]), "status": "Active", "end": None,
                             "cancellation": None})
        elif idx in NOW_EXPIRED:
            inc = rand_date(prng, date(2019, 1, 1), date(2024, 6, 28)).replace(day=prng.randint(1, 28))
            terms = terms_until(inc, 6, date(2026, 9, 20))
            end = [t for t in terms if t[1] >= date(2026, 3, 20)][0][1]
            timeline.append({"inception": inc, "months": 6, "status": "Expired", "end": end, "cancellation": None})
        elif idx in NOW_CANCELLED:
            inc = rand_date(prng, date(2018, 1, 1), date(2025, 5, 28)).replace(day=prng.randint(1, 28))
            end = rand_date(prng, date(2026, 6, 1), date(2026, 9, 20))
            reason = "Non-payment of premium" if idx == 28 else "Insured request"
            timeline.append({"inception": inc, "months": prng.choice([6, 12]), "status": "Cancelled", "end": end,
                             "cancellation": {"effectiveDate": iso(end), "reason": reason}})
        else:
            hi = date(2020, 6, 28) if idx == 11 else date(2025, 12, 28)
            lo = date(2016, 1, 1) if idx == 11 else date(2014, 1, 1)
            inc = rand_date(prng, lo, hi).replace(day=prng.randint(1, 28))
            timeline.append({"inception": inc, "months": prng.choice([6, 12, 12]), "status": "Active", "end": None,
                             "cancellation": None})

        first_inception = timeline[0]["inception"]
        last_end = timeline[-1]["end"] or AS_OF

        # --- vehicles --------------------------------------------------------
        cust_vehicles = []
        n_vehicles = 2 if idx in TWO_VEHICLES else 1
        for v_i in range(n_vehicles):
            if v_i == 0:
                acquired = first_inception - timedelta(days=vrng.randint(0, 75))
            else:
                acquired = rand_date(vrng, first_inception + timedelta(days=30), last_end - timedelta(days=30))
            prefer_new = vrng.random() < 0.5
            model, year = pick_model(vrng, acquired, prefer_new)
            make, model_name, code, body, body_code, trims, fuel, _fy, _ly = model
            trim_index = vrng.randrange(len(trims))
            trim, drive = trims[trim_index]
            is_new = year >= acquired.year
            if idx in FULL_COVERAGE_REQUIRED and year < 2018:
                year = max(2018, model[7])
                if year > acquired.year + 1:
                    acquired = date(year - 1, 10, 1)
                    if acquired > first_inception:
                        acquired = first_inception
                        year = min(model[8], acquired.year + 1)
            own_roll = vrng.random()
            if is_new:
                own = "Financed" if own_roll < 0.55 else ("Leased" if own_roll < 0.7 else "Owned")
            else:
                own = "Financed" if own_roll < 0.35 else "Owned"
            lien = vrng.choice(LENDERS) if own == "Financed" else (vrng.choice(LESSORS) if own == "Leased" else None)
            vehicle = {
                "vehicleId": new_vehicle_id(),
                "vin": make_vin(make, code, trim_index, body_code, year, new_serial()),
                "year": year, "make": make, "model": model_name, "trim": trim,
                "bodyStyle": body, "exteriorColor": vrng.choice(COLORS),
                "drivetrain": drive, "fuelType": fuel,
                "ownerCustomerId": customer_id,
                "acquiredDate": iso(acquired), "disposedDate": None,
                "ownership": {"type": own, "lienholder": lien},
                "primaryUse": vrng.choices(["Commute", "Pleasure", "Business"], [6, 3, 1])[0],
                "garaging": {"city": city, "state": state},
                "equipment": equipment_for(vrng, model, year),
            }
            cust_vehicles.append(vehicle)
        vehicles.extend(cust_vehicles)
        vehicle_covs = {v["vehicleId"]: coverage_profile(prng, v, idx in FULL_COVERAGE_REQUIRED) for v in cust_vehicles}
        if idx == 11:  # keeps the comprehensive deductible below the hail settlement used in its claims
            vehicle_covs[cust_vehicles[0]["vehicleId"]] = [
                coverage("COLL", 500), coverage("COMP", 250),
                coverage("RENT", None, [("Per day", 40), ("Maximum per loss", 1200)])]

        # --- drivers ---------------------------------------------------------
        drivers = [{"fullName": f"{first} {last}", "relationship": "Named insured", "licenseState": state}]
        if prng.random() < 0.35:
            other_first = prng.choice([n for n in FIRST_NAMES if n != first])
            drivers.append({"fullName": f"{other_first} {last}",
                            "relationship": prng.choice(["Spouse/partner", "Household member"]),
                            "licenseState": state})

        # --- policies --------------------------------------------------------
        cust_policies = []
        pol_covs, tier = policy_coverages(prng, state)
        for t in timeline:
            policy_id = f"PAP-{prng.randint(3000000, 4999999)}"
            while policy_id in used_policy_ids:
                policy_id = f"PAP-{prng.randint(3000000, 4999999)}"
            used_policy_ids.add(policy_id)
            end = t["end"]
            if t["status"] == "Active":
                term = term_containing(t["inception"], t["months"], AS_OF)
            elif t["status"] == "Expired":
                term = terms_until(t["inception"], t["months"], end)[-1]
            else:
                term = term_containing(t["inception"], t["months"], end - timedelta(days=1))
            coverage_end = end or date.max
            entries = []
            for v in cust_vehicles:
                acquired = date.fromisoformat(v["acquiredDate"])
                if acquired >= coverage_end:
                    continue
                entries.append({
                    "vehicleId": v["vehicleId"],
                    "addedDate": iso(max(t["inception"], acquired)),
                    "removedDate": None,
                    "lossPayee": v["ownership"]["lienholder"],
                    "coverages": vehicle_covs[v["vehicleId"]],
                })
            if not entries:
                raise RuntimeError(f"policy without vehicles for customer slot {idx}")
            policy = {
                "policyId": policy_id,
                "customerId": customer_id,
                "productName": "Contoso Insurance Personal Auto Policy",
                "status": t["status"],
                "ratingState": state,
                "inceptionDate": iso(t["inception"]),
                "termMonths": t["months"],
                "termEffectiveDate": iso(term[0]),
                "termExpirationDate": iso(term[1]),
                "cancellation": t["cancellation"],
                "paymentPlan": prng.choice(["Paid in full", "Monthly", "Monthly"]),
                "termPremium": premium(prng, tier, [e["coverages"] for e in entries], t["months"]),
                "drivers": drivers,
                "policyCoverages": pol_covs,
                "vehicles": entries,
            }
            cust_policies.append(policy)
        policies.extend(cust_policies)

        customers.append({
            "customerId": customer_id, "firstName": first, "lastName": last, "fullName": f"{first} {last}",
            "customerSince": iso(first_inception),
            "address": address(rng, city),
            "phone": phones.take(area),
            "email": f"{first.lower()}.{last.lower()}@example.com",
            "preferredContactMethod": rng.choice(["Email", "Phone", "Text message"]),
            "policyIds": [p["policyId"] for p in cust_policies],
            "vehicleIds": [v["vehicleId"] for v in cust_vehicles],
        })
        plans.append({"index": idx, "customerId": customer_id, "policies": cust_policies})
    return customers, vehicles, policies, plans


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

PHYSICAL_DAMAGE_RANGES = {  # cause -> (min, max) settled amount
    "Two-vehicle collision": (1800, 12500),
    "Single-vehicle collision": (1200, 9500),
    "Hit while parked": (900, 4800),
    "Hail": (2200, 8800),
    "Glass breakage": (380, 1450),
    "Theft": (14000, 31000),
    "Animal strike": (2600, 9200),
    "Vandalism": (650, 3600),
    "Falling object": (1500, 6400),
    "Property damage to another vehicle": (1400, 8800),
}


def narrative(rng: random.Random, cause: str, vehicle: dict, city: str) -> tuple[str, list[str], dict]:
    """Returns (description, reported damage areas, location) for a generated claim."""
    side = rng.choice(["left", "right"])
    side_cap = side.capitalize()
    closure = rear_closure(vehicle["bodyStyle"])
    s1, s2 = rng.sample(STREET_NAMES, 2)
    state = CITIES[city][0]
    road = f"County Road {rng.choice([7, 12, 18, 22, 31, 47])}"
    places = [f"{city} Marketplace parking lot", f"{city} Community College parking lot",
              f"{city} Medical Center parking garage", f"{city} Station park-and-ride lot"]
    intersection = {"description": f"Intersection of {s1} {rng.choice(STREET_SUFFIXES)} and {s2} "
                                   f"{rng.choice(STREET_SUFFIXES)}", "street": None, "city": city, "state": state}
    lot = {"description": rng.choice(places), "street": None, "city": city, "state": state}
    on_road = {"description": f"{road} near {city}", "street": None, "city": city, "state": state}
    home = {"description": "Street outside the policyholder's residence", "street": None, "city": city,
            "state": state}

    if cause == "Two-vehicle collision":
        variant = rng.randrange(3)
        if variant == 0:
            return ("I was stopped at a red light when the vehicle behind me did not stop in time and hit the back "
                    "of my car.", ["Rear bumper", closure], intersection)
        if variant == 1:
            return (f"I was turning left on a green arrow when another driver went through the red light and hit the "
                    f"{side} front of my vehicle.",
                    ["Front bumper", f"{side_cap} front fender", f"{side_cap} headlamp"], intersection)
        return (f"Another vehicle merged into my lane on {road} and scraped along the {side} side of my vehicle.",
                [f"{side_cap} front door", f"{side_cap} rear door", f"{side_cap} side mirror"], on_road)
    if cause == "Single-vehicle collision":
        variant = rng.randrange(3)
        if variant == 0:
            return (f"The road was icy on {road} and my vehicle slid into the guardrail on the {side} side.",
                    ["Front bumper", f"{side_cap} front fender", f"{side_cap} headlamp"], on_road)
        if variant == 1:
            return ("I was backing out of a parking space and hit a concrete post.", ["Rear bumper", closure], lot)
        return (f"I hit a deep pothole on {road}. The {side} front wheel is bent and the tire went flat.",
                [f"{side_cap} front wheel", f"{side_cap} front tire"], on_road)
    if cause == "Hit while parked":
        if rng.random() < 0.6:
            return (f"My vehicle was parked at the {lot['description']}. When I came back, the {side} rear door was "
                    f"dented and scraped. No note was left.",
                    [f"{side_cap} rear door", f"{side_cap} rear quarter panel"], lot)
        return ("My car was parked overnight on the street outside my home. In the morning the rear bumper was "
                "cracked and scuffed.", ["Rear bumper"], home)
    if cause == "Hail":
        return (f"A hailstorm passed through {city} while my vehicle was parked outside. The hood, roof and "
                f"{closure.lower()} have many small dents.", ["Hood", "Roof", closure], home)
    if cause == "Glass breakage":
        return (f"A rock thrown up by a truck on {road} hit the windshield and cracked it.", ["Windshield"], on_road)
    if cause == "Theft":
        return (f"My vehicle was stolen from the {lot['description']}. Police recovered it two days later with the "
                f"steering column and ignition damaged.", ["Steering column", "Ignition", "Driver door lock"], lot)
    if cause == "Animal strike":
        return (f"A deer ran onto {road} at dusk and I could not avoid it.",
                ["Front bumper", "Grille", "Hood", f"{side_cap} headlamp"], on_road)
    if cause == "Vandalism":
        return (f"Someone scratched deep lines into the paint on the {side} side while my vehicle was parked at the "
                f"{lot['description']}.", [f"{side_cap} front door", f"{side_cap} rear door"], lot)
    if cause == "Falling object":
        return ("A large tree branch fell on my parked vehicle during a windstorm.", ["Roof", "Windshield"], home)
    if cause == "Property damage to another vehicle":
        if rng.random() < 0.5:
            return (f"I misjudged the distance while parking at the {lot['description']} and hit the rear bumper of a "
                    f"parked vehicle.", ["Other party's vehicle: rear bumper"], lot)
        return (f"Traffic stopped suddenly on {road} and I rear-ended the vehicle in front of me.",
                ["Other party's vehicle: rear bumper", "Other party's vehicle: trunk lid"], on_road)
    raise ValueError(cause)


CAUSES = {
    "Collision": [("Two-vehicle collision", 5), ("Single-vehicle collision", 3), ("Hit while parked", 3)],
    "Comprehensive": [("Hail", 2), ("Glass breakage", 4), ("Theft", 1), ("Animal strike", 2), ("Vandalism", 2),
                      ("Falling object", 1)],
    "Property Damage Liability": [("Property damage to another vehicle", 1)],
}
POLICE_PROBABILITY = {"Two-vehicle collision": 0.7, "Single-vehicle collision": 0.2, "Hit while parked": 0.3,
                      "Theft": 1.0, "Vandalism": 0.6, "Property damage to another vehicle": 0.5}


def agency_for(city: str) -> tuple[str, str]:
    initials = "".join(w[0] for w in city.split())
    return f"{city} Police Department", f"{initials}PD"


def coverage_windows(policy: dict) -> list[tuple[dict, dict, date, date]]:
    """(policy, vehicle entry, first covered date, first uncovered date) for each vehicle on a policy."""
    if policy["status"] == "Active":
        policy_end = date.max
    elif policy["status"] == "Expired":
        policy_end = date.fromisoformat(policy["termExpirationDate"])
    else:
        policy_end = date.fromisoformat(policy["cancellation"]["effectiveDate"])
    out = []
    for entry in policy["vehicles"]:
        start = date.fromisoformat(entry["addedDate"])
        end = date.fromisoformat(entry["removedDate"]) if entry["removedDate"] else policy_end
        out.append((policy, entry, start, min(end, policy_end)))
    return out


def vehicle_coverage_codes(entry: dict) -> set[str]:
    return {c["coverageCode"] for c in entry["coverages"]}


def deductible_for(entry: dict, claim_type: str) -> float:
    code = {"Collision": "COLL", "Comprehensive": "COMP"}.get(claim_type)
    if code is None:
        return 0.0
    for c in entry["coverages"]:
        if c["coverageCode"] == code:
            return c["deductible"]
    raise ValueError(f"vehicle {entry['vehicleId']} has no {code}")


class ClaimFactory:
    def __init__(self, facilities: list[dict], vehicles: dict[str, dict], customers: dict[str, dict]):
        self.rng = rng_for("claims")
        self.facilities = facilities
        self.vehicles = vehicles
        self.customers = customers
        self.police_numbers: set[str] = set()
        self.estimate_numbers: set[str] = set()

    def facility_for(self, state: str, cause: str) -> str:
        glass = cause == "Glass breakage"
        candidates = [f for f in self.facilities
                      if f["address"]["state"] == state
                      and ("Auto glass" in f["services"] if glass else "Collision repair" in f["services"])]
        if not candidates:
            candidates = [f for f in self.facilities
                          if ("Auto glass" in f["services"] if glass else "Collision repair" in f["services"])]
        return self.rng.choice(candidates)["repairFacilityId"]

    def police_number(self, prefix: str, year: int) -> str:
        while True:
            value = f"{prefix}-{year % 100:02d}-{self.rng.randint(1000, 39999):06d}"
            if value not in self.police_numbers:
                self.police_numbers.add(value)
                return value

    def estimate_number(self, facility_id: str, year: int) -> str:
        while True:
            value = f"EST-{FACILITY_PREFIX[facility_id]}-{year % 100:02d}-{self.rng.randint(1000, 9999)}"
            if value not in self.estimate_numbers:
                self.estimate_numbers.add(value)
                return value

    def build(self, *, customer_id: str, policy: dict, entry: dict, claim_type: str, cause: str, loss_date: date,
              status: str | None = None, report_delay: int | None = None, channel: str | None = None,
              story: tuple[str, list[str], dict] | None = None, police: str | None = None,
              estimate: bool | None = None, photos: int | None = None) -> dict:
        """Builds one claim record. Optional keyword arguments pin scenario-specific facts;
        anything left as None is generated."""
        rng = self.rng
        vehicle = self.vehicles[entry["vehicleId"]]
        city = vehicle["garaging"]["city"] if rng.random() < 0.85 else rng.choice(
            [c for c, v in CITIES.items() if v[0] == vehicle["garaging"]["state"]])
        state, tz, _zip, _area = CITIES[city]
        description, areas, location = story or narrative(rng, cause, vehicle, city)
        if story:
            city, state = location["city"], location["state"]
            tz = CITIES[city][1]

        loss_time = f"{rng.randint(6, 21):02d}:{rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]):02d}"
        loss_utc = local_to_utc(loss_date, loss_time, tz)
        delay = report_delay if report_delay is not None else rng.choices([0, 1, 2, 3, 5], [4, 3, 1, 1, 1])[0]
        report_date = loss_date + timedelta(days=delay)
        while True:
            report_time = f"{rng.randint(7, 21):02d}:{rng.randint(0, 59):02d}"
            reported = local_to_utc(report_date, report_time, tz)
            if reported >= loss_utc + timedelta(minutes=45):
                break
            report_date += timedelta(days=1) if rng.random() < 0.2 else timedelta(0)
        if report_date >= AS_OF:
            raise ValueError("claim reported after records date")
        age = (AS_OF - report_date).days

        if status is None:
            if age <= 3:
                status = "Submitted"
            elif age <= 40:
                status = rng.choices(["In Review", "Pending Documentation", "Closed - Withdrawn", "Closed - Paid"],
                                     [6, 3, 1, 2 if age > 20 else 0])[0]
            else:
                status = rng.choices(["Closed - Paid", "Closed - Denied", "Closed - Withdrawn"], [78, 9, 13])[0]
        closed = status.startswith("Closed")

        deductible = deductible_for(entry, claim_type)
        lo, hi = PHYSICAL_DAMAGE_RANGES[cause]
        settled = money(rng.uniform(max(lo, deductible + 250), max(hi, deductible + 600)))
        closure_reason = None
        settlement = None
        closed_date = None
        if closed:
            closed_date = report_date + timedelta(days=rng.randint(8, max(9, min(75, age - 1))))
            if status == "Closed - Paid":
                settlement = {"settledAmount": settled, "deductibleApplied": float(deductible),
                              "totalPaid": money(settled - deductible)}
                closure_reason = "Payment issued"
            elif status == "Closed - Denied":
                if claim_type == "Property Damage Liability":
                    closure_reason = "Liability not accepted"
                else:
                    closure_reason = "Repair cost below deductible"
            else:
                closure_reason = "Withdrawn by policyholder"

        drivable = cause in {"Glass breakage", "Hail", "Vandalism", "Hit while parked"} or rng.random() < 0.75
        if cause == "Theft":
            drivable = False
        injuries = cause in {"Two-vehicle collision", "Property damage to another vehicle"} and rng.random() < 0.12

        other_parties = []
        if cause in {"Two-vehicle collision", "Property damage to another vehicle"}:
            model, year = pick_model(rng, loss_date, rng.random() < 0.3)
            other_parties.append({
                "role": "Other driver",
                "name": f"{rng.choice(OTHER_PARTY_FIRST)} {rng.choice(OTHER_PARTY_LAST)}",
                "vehicleDescription": f"{year} {model[0]} {model[1]} {model[3].split(',')[0].lower()}, "
                                      f"{rng.choice(COLORS).split()[0].lower()}",
                "insurer": rng.choice(OTHER_INSURERS),
            })

        if police is None:
            police = "received" if rng.random() < POLICE_PROBABILITY.get(cause, 0.1) else "none"
        if police == "none":
            police_report = {"reportedToPolice": False, "agency": None, "reportNumber": None}
        else:
            agency, prefix = agency_for(city)
            police_report = {"reportedToPolice": True, "agency": agency,
                             "reportNumber": self.police_number(prefix, loss_date.year)}

        last_event = reported
        documents: list[tuple[str, str, str, datetime]] = []
        form_title = {"Online": "Auto claim - first notice of loss (online submission)",
                      "Mobile app": "Auto claim - first notice of loss (mobile app)",
                      "Phone": "Auto claim - first notice of loss (phone)",
                      "Agent": "Auto claim - first notice of loss (agent)"}
        channel = channel or rng.choices(["Online", "Phone", "Mobile app", "Agent"], [4, 3, 3, 1])[0]
        documents.append(("Claim form", form_title[channel],
                          "Policyholder" if channel in {"Online", "Mobile app"} else "Contoso Insurance", reported))
        if photos is None:
            photos = 0 if cause == "Theft" else (2 if cause == "Glass breakage" else rng.randint(2, 6))
        photo_time = reported if channel in {"Online", "Mobile app"} else reported + timedelta(hours=rng.randint(2, 30))
        if status == "Submitted":
            photo_time = reported
        for n in range(photos):
            documents.append(("Photograph", f"Photograph {n + 1} of {photos}", "Policyholder", photo_time))

        def later(days_lo: int, days_hi: int) -> datetime:
            limit = datetime.combine(closed_date or AS_OF, time(0), tzinfo=timezone.utc)
            when = reported + timedelta(days=rng.randint(days_lo, days_hi), hours=rng.randint(1, 8))
            return min(when, limit - timedelta(hours=rng.randint(2, 20)))

        if police == "received" and status != "Submitted":
            agency_name = police_report["agency"]
            documents.append(("Police report", f"{agency_name} report {police_report['reportNumber']}",
                              "Police agency", later(2, 8)))

        repair_facility = None
        estimate_record = None
        physical = cause != "Theft" and claim_type != "Property Damage Liability"
        if estimate is None:
            estimate = physical and status not in {"Submitted"} and not (
                status == "Closed - Withdrawn" and rng.random() < 0.5)
        if estimate:
            repair_facility = self.facility_for(state, cause)
            estimate_at = later(2, 7)
            if status == "Closed - Paid":
                gross = money(settled * rng.uniform(0.9, 1.0))
            elif status == "Closed - Denied":
                gross = money(deductible * rng.uniform(0.45, 0.9))
            else:
                gross = settled
            estimate_record = {"estimateId": self.estimate_number(repair_facility, estimate_at.year),
                               "repairFacilityId": repair_facility,
                               "estimateDate": iso((estimate_at - timedelta(hours=6)).date()),
                               "grossAmount": gross}
            documents.append(("Repair estimate", f"Repair estimate {estimate_record['estimateId']}",
                              "Repair facility", estimate_at))
        if status == "Closed - Paid":
            if cause == "Theft":
                documents.append(("Total loss valuation", "Vehicle valuation report", "Contoso Insurance",
                                  later(5, 12)))
            elif physical:
                documents.append(("Repair invoice", "Final repair invoice", "Repair facility",
                                  datetime.combine(closed_date, time(0), tzinfo=timezone.utc)
                                  - timedelta(hours=rng.randint(6, 30))))
            else:
                documents.append(("Repair invoice", "Other party's repair invoice", "Other party",
                                  datetime.combine(closed_date, time(0), tzinfo=timezone.utc)
                                  - timedelta(hours=rng.randint(6, 30))))

        for doc in documents:
            last_event = max(last_event, doc[3])
        if closed_date:
            last_event = max(last_event, datetime.combine(closed_date, time(17, rng.randint(0, 59)),
                                                          tzinfo=timezone.utc))
        elif status != "Submitted":
            last_event = max(last_event, later(1, max(2, min(age - 1, 12))))

        return {
            "claimId": None,
            "customerId": customer_id,
            "policyId": policy["policyId"],
            "vehicleId": entry["vehicleId"],
            "claimType": claim_type,
            "causeOfLoss": cause,
            "status": status,
            "lossDate": iso(loss_date),
            "lossTime": loss_time,
            "lossTimeZone": tz,
            "lossLocation": location,
            "reportedAt": iso_z(reported),
            "reportChannel": channel,
            "description": description,
            "reportedDamage": {"summary": "; ".join(areas) + ".", "areas": areas},
            "vehicleDrivable": drivable,
            "injuriesReported": injuries,
            "otherParties": other_parties,
            "policeReport": police_report,
            "repairFacilityId": repair_facility,
            "estimate": estimate_record,
            "documents": [{"documentId": None, "documentType": t, "title": title, "source": src,
                           "receivedAt": iso_z(at)} for t, title, src, at in sorted(documents, key=lambda d: d[3])],
            "settlement": settlement,
            "closedDate": iso(closed_date),
            "closureReason": closure_reason,
            "createdAt": iso_z(reported),
            "lastUpdatedAt": iso_z(last_event),
        }


def hero_claim_records(policy: dict) -> list[dict]:
    out = []
    for spec in HERO_CLAIMS:
        loss_city = spec["lossLocation"]["city"]
        tz = CITIES[loss_city][1]
        rep_date, rep_time = spec["reportedLocal"]
        reported = iso_z(local_to_utc(date.fromisoformat(rep_date), rep_time, tz))
        out.append({
            "claimId": spec["claimId"],
            "customerId": HERO_CUSTOMER["customerId"],
            "policyId": policy["policyId"],
            "vehicleId": spec["vehicleId"],
            "claimType": spec["claimType"],
            "causeOfLoss": spec["causeOfLoss"],
            "status": spec["status"],
            "lossDate": spec["lossDate"],
            "lossTime": spec["lossTime"],
            "lossTimeZone": tz,
            "lossLocation": spec["lossLocation"],
            "reportedAt": reported,
            "reportChannel": spec["reportChannel"],
            "description": spec["description"],
            "reportedDamage": spec["reportedDamage"],
            "vehicleDrivable": spec["vehicleDrivable"],
            "injuriesReported": spec["injuriesReported"],
            "otherParties": spec["otherParties"],
            "policeReport": spec["policeReport"],
            "repairFacilityId": spec["repairFacilityId"],
            "estimate": spec["estimate"],
            "documents": [{"documentId": None, "documentType": t, "title": title, "source": src, "receivedAt": at}
                          for t, title, src, at in spec["documents"]],
            "settlement": spec["settlement"],
            "closedDate": spec["closedDate"],
            "closureReason": spec["closureReason"],
            "createdAt": reported,
            "lastUpdatedAt": spec["lastUpdatedAt"],
        })
    return out


def scenario_claims(factory: ClaimFactory, plans: dict[int, dict]) -> list[dict]:
    """Structured situations that later evaluations can use. They are ordinary records:
    nothing in them labels the situation they represent (see data/README.md)."""
    out = []

    def current(idx: int) -> tuple[str, dict, dict]:
        plan = plans[idx]
        policy = plan["policies"][-1]
        return plan["customerId"], policy, policy["vehicles"][0]

    # Customer with several claims over time (slot 11).
    cid, policy, entry = current(11)
    vehicle = factory.vehicles[entry["vehicleId"]]
    city = vehicle["garaging"]["city"]
    for loss, ctype, cause, status in [
        (date(2023, 6, 14), "Comprehensive", "Hail", "Closed - Paid"),
        (date(2024, 2, 8), "Collision", "Single-vehicle collision", "Closed - Paid"),
        (date(2025, 7, 22), "Comprehensive", "Vandalism", "Closed - Withdrawn"),
        (date(2026, 10, 9), "Collision", "Hit while parked", "In Review"),
    ]:
        out.append(factory.build(customer_id=cid, policy=policy, entry=entry, claim_type=ctype, cause=cause,
                                 loss_date=loss, status=status,
                                 story=narrative(factory.rng, cause, vehicle, city)))

    # Two claims for the same vehicle, one day apart, similar circumstances (slot 12).
    cid, policy, entry = current(12)
    vehicle = factory.vehicles[entry["vehicleId"]]
    city, state = vehicle["garaging"]["city"], vehicle["garaging"]["state"]
    lot = {"description": f"{city} Marketplace parking lot", "street": None, "city": city, "state": state}
    out.append(factory.build(
        customer_id=cid, policy=policy, entry=entry, claim_type="Collision", cause="Hit while parked",
        loss_date=date(2026, 10, 27), status="In Review", report_delay=1, channel="Phone", police="none",
        story=(f"My car was parked at the {city} Marketplace parking lot. When I came back, the left rear door and "
               f"left rear quarter panel were dented and scraped. No note was left.",
               ["Left rear door", "Left rear quarter panel"], lot), photos=3, estimate=True))
    out.append(factory.build(
        customer_id=cid, policy=policy, entry=entry, claim_type="Collision", cause="Hit while parked",
        loss_date=date(2026, 10, 28), status="Pending Documentation", report_delay=2, channel="Mobile app",
        police="none",
        story=(f"While I was shopping at the {city} Marketplace, someone hit my parked car and drove away. The left "
               f"rear door is dented and the paint is scraped.", ["Left rear door"], lot), photos=2, estimate=False))

    # Loss date after the only policy expired (slot 26).
    cid, policy, entry = current(26)
    vehicle = factory.vehicles[entry["vehicleId"]]
    out.append(factory.build(customer_id=cid, policy=policy, entry=entry, claim_type="Collision",
                             cause="Two-vehicle collision", loss_date=date(2026, 10, 5), status="In Review",
                             report_delay=1, police="received", estimate=True))

    # Loss date after the only policy was cancelled (slot 28).
    cid, policy, entry = current(28)
    out.append(factory.build(customer_id=cid, policy=policy, entry=entry, claim_type="Comprehensive",
                             cause="Vandalism", loss_date=date(2026, 10, 19), status="In Review",
                             report_delay=1, police="received", estimate=True))

    # Police report filed but not yet received by Contoso (slot 13).
    cid, policy, entry = current(13)
    out.append(factory.build(customer_id=cid, policy=policy, entry=entry, claim_type="Collision",
                             cause="Two-vehicle collision", loss_date=date(2026, 11, 3),
                             status="Pending Documentation", report_delay=1, channel="Phone",
                             police="reported", estimate=True, photos=4))

    # Straightforward open collision claim with all documents received (slot 14).
    cid, policy, entry = current(14)
    vehicle = factory.vehicles[entry["vehicleId"]]
    city, state = vehicle["garaging"]["city"], vehicle["garaging"]["state"]
    s1, s2 = "Cedar", "Summit"
    out.append(factory.build(
        customer_id=cid, policy=policy, entry=entry, claim_type="Collision", cause="Two-vehicle collision",
        loss_date=date(2026, 11, 6), status="In Review", report_delay=0, channel="Online", police="received",
        estimate=True, photos=4,
        story=("I was stopped at a red light when the vehicle behind me did not stop in time and hit the back of "
               "my car.", ["Rear bumper", rear_closure(vehicle["bodyStyle"])],
               {"description": f"Intersection of {s1} Ave and {s2} St", "street": None, "city": city,
                "state": state})))

    # Recent single-vehicle claim, not reported to police (slot 15).
    cid, policy, entry = current(15)
    vehicle = factory.vehicles[entry["vehicleId"]]
    city, state = vehicle["garaging"]["city"], vehicle["garaging"]["state"]
    out.append(factory.build(
        customer_id=cid, policy=policy, entry=entry, claim_type="Collision", cause="Single-vehicle collision",
        loss_date=date(2026, 11, 16), status="Submitted", report_delay=1, channel="Mobile app", police="none",
        estimate=False, photos=2,
        story=("I was backing out of a parking space and hit a concrete post.",
               ["Rear bumper", rear_closure(vehicle["bodyStyle"])],
               {"description": f"{city} Community College parking lot", "street": None, "city": city,
                "state": state})))
    return out


def background_claims(factory: ClaimFactory, plans: dict[int, dict], existing: list[dict], count: int) -> list[dict]:
    rng = rng_for("background-claims")
    pool = [i for i in plans if i != 0 and i not in NO_CLAIMS and i not in {11, 12, 26, 28}]
    per_customer: dict[str, int] = {}
    by_vehicle: dict[str, list[date]] = {}
    for c in existing:
        per_customer[c["customerId"]] = per_customer.get(c["customerId"], 0) + 1
        by_vehicle.setdefault(c["vehicleId"], []).append(date.fromisoformat(c["lossDate"]))

    out = []
    attempts = 0
    while len(out) < count:
        attempts += 1
        if attempts > 5000:
            raise RuntimeError("could not place background claims")
        idx = rng.choice(pool)
        plan = plans[idx]
        if per_customer.get(plan["customerId"], 0) >= 3:
            continue
        windows = [w for p in plan["policies"] for w in coverage_windows(p)]
        policy, entry, start, end = rng.choice(windows)
        recent = len(out) < 6
        lo = max(start, CLAIMS_SYSTEM_START, AS_OF - timedelta(days=60) if recent else date.min)
        hi = min(end - timedelta(days=1), AS_OF - timedelta(days=8))
        if hi < lo:
            continue
        loss = rand_date(rng, lo, hi)
        if any(abs((loss - d).days) < 45 for d in by_vehicle.get(entry["vehicleId"], [])):
            continue
        codes = vehicle_coverage_codes(entry)
        types = [("Property Damage Liability", 2)]
        if "COLL" in codes:
            types.append(("Collision", 9))
        if "COMP" in codes:
            types.append(("Comprehensive", 7))
        claim_type = rng.choices([t for t, _ in types], [w for _, w in types])[0]
        causes = CAUSES[claim_type]
        cause = rng.choices([c for c, _ in causes], [w for _, w in causes])[0]
        if cause in {"Theft"} and recent:
            continue
        claim = factory.build(customer_id=plan["customerId"], policy=policy, entry=entry, claim_type=claim_type,
                              cause=cause, loss_date=loss)
        out.append(claim)
        per_customer[plan["customerId"]] = per_customer.get(plan["customerId"], 0) + 1
        by_vehicle.setdefault(entry["vehicleId"], []).append(loss)
    return out


def assign_claim_ids(claims: list[dict]) -> None:
    """Claim numbers increase with report time (gaps are claims from other lines of business);
    numbering is anchored so the current hero claim keeps its published number."""
    rng = rng_for("claim-ids")
    claims.sort(key=lambda c: (c["reportedAt"], c["lossDate"], c["vehicleId"]))
    anchor = next(i for i, c in enumerate(claims) if c["claimId"] == HERO_CLAIM_ID)
    numbers = [0] * len(claims)
    numbers[anchor] = int(HERO_CLAIM_ID.split("-")[1])
    for i in range(anchor - 1, -1, -1):
        numbers[i] = numbers[i + 1] - rng.randint(2, 9)
    for i in range(anchor + 1, len(claims)):
        numbers[i] = numbers[i - 1] + rng.randint(1, 3)
    for claim, number in zip(claims, numbers):
        claim["claimId"] = f"CLM-{number}"
        for n, doc in enumerate(claim["documents"], start=1):
            doc["documentId"] = f"DOC-{number}-{n:02d}"


def archived_claims(plans: dict[int, dict], vehicles: dict[str, dict], count: int) -> list[dict]:
    """Closed claims from the legacy claims system (losses before CLAIMS_SYSTEM_START)."""
    rng = rng_for("archive")
    candidates = []
    for idx, plan in plans.items():
        if idx == 0 or idx in NO_CLAIMS:
            continue
        for p in plan["policies"]:
            for policy, entry, start, end in coverage_windows(p):
                hi = min(end, CLAIMS_SYSTEM_START) - timedelta(days=30)
                if hi > start + timedelta(days=60):
                    candidates.append((idx, plan["customerId"], policy, entry, start, hi))
    picked = [c for c in candidates if c[0] == 11][:1]
    others = [c for c in candidates if c[0] != 11]
    rng.shuffle(others)
    picked += others[: count - len(picked)]
    used: set[str] = set()
    out = []
    for idx, customer_id, policy, entry, start, hi in picked:
        loss = rand_date(rng, start + timedelta(days=30), hi)
        codes = vehicle_coverage_codes(entry)
        options = [("Property Damage Liability", "Property damage to another vehicle")]
        if "COLL" in codes:
            options += [("Collision", "Two-vehicle collision"), ("Collision", "Single-vehicle collision")]
        if "COMP" in codes:
            options += [("Comprehensive", "Glass breakage"), ("Comprehensive", "Hail"),
                        ("Comprehensive", "Animal strike")]
        claim_type, cause = rng.choice(options)
        status = rng.choices(["Closed - Paid", "Closed - Denied", "Closed - Withdrawn"], [8, 1, 1])[0]
        deductible = deductible_for(entry, claim_type)
        lo, hi_amt = PHYSICAL_DAMAGE_RANGES[cause]
        settled = money(rng.uniform(max(lo, deductible + 250), max(hi_amt, deductible + 600)))
        while True:
            claim_id = f"AC-{loss.year}-{rng.randint(10000, 49999)}"
            if claim_id not in used:
                used.add(claim_id)
                break
        reported = loss + timedelta(days=rng.choice([0, 1, 1, 2, 4]))
        closed = reported + timedelta(days=rng.randint(9, 60))
        vehicle = vehicles[entry["vehicleId"]]
        out.append({
            "claimId": claim_id,
            "customerId": customer_id,
            "policyId": policy["policyId"],
            "vehicleId": entry["vehicleId"],
            "vehicleDescription": f"{vehicle['year']} {vehicle['make']} {vehicle['model']}",
            "claimType": claim_type,
            "causeOfLoss": cause,
            "lossDate": iso(loss),
            "reportedDate": iso(reported),
            "status": status,
            "closedDate": iso(closed),
            "settledAmount": settled if status == "Closed - Paid" else None,
            "deductibleApplied": float(deductible) if status == "Closed - Paid" else None,
            "totalPaid": money(settled - deductible) if status == "Closed - Paid" else None,
        })
    out.sort(key=lambda c: (c["lossDate"], c["claimId"]))
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build_dataset() -> dict[str, dict]:
    phones = Phones(rng_for("phones"))
    facilities = build_repair_facilities(phones)
    customers, vehicles, policies, plan_list = build_people_vehicles_policies(phones)
    plans = {p["index"]: p for p in plan_list}
    vehicle_index = {v["vehicleId"]: v for v in vehicles}
    customer_index = {c["customerId"]: c for c in customers}

    factory = ClaimFactory(facilities, vehicle_index, customer_index)
    claims = hero_claim_records(policies[0])
    claims += scenario_claims(factory, plans)
    claims += background_claims(factory, plans, claims, 50 - len(claims))
    assign_claim_ids(claims)
    archive = archived_claims(plans, vehicle_index, 12)

    def envelope(key: str, records: list[dict], source: str) -> dict:
        return {"dataset": "Contoso Insurance synthetic claims data", "synthetic": True, "notice": SYNTHETIC_NOTICE,
                "recordsAsOf": RECORDS_AS_OF, "source": source, key: records}

    return {
        "customers.json": envelope("customers", sorted(customers, key=lambda c: c["customerId"]),
                                   "Customer master"),
        "policies.json": envelope("policies", sorted(policies, key=lambda p: p["policyId"]),
                                  "Policy administration system"),
        "vehicles.json": envelope("vehicles", sorted(vehicles, key=lambda v: v["vehicleId"]),
                                  "Insured vehicle registry"),
        "claims.json": envelope("claims", claims, "Claims system (losses on or after 2023-01-01)"),
        "claim-history.json": envelope("archivedClaims", archive,
                                       "Archived claims from the legacy claims system (losses before 2023-01-01)"),
        "repair-facilities.json": envelope("repairFacilities", facilities, "Repair facility directory"),
    }


def serialize(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="verify the committed data files match a fresh generation; write nothing")
    args = parser.parse_args(argv)

    dataset = build_dataset()
    stale = []
    for name, content in dataset.items():
        path = DATA_DIR / name
        text = serialize(content)
        if args.check:
            current = path.read_bytes().decode("utf-8") if path.exists() else None
            if current != text:
                stale.append(name)
        else:
            path.write_bytes(text.encode("utf-8"))
    if args.check:
        if stale:
            print("Data files are out of date: " + ", ".join(stale))
            print("Run: python data/generate_data.py")
            return 1
        print(f"Data files are current ({len(dataset)} files).")
        return 0
    counts = {name: len(next(v for k, v in content.items() if isinstance(v, list))) for name, content in dataset.items()}
    print("Wrote " + ", ".join(f"{name} ({n})" for name, n in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
