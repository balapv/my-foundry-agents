"""Data integrity tests for the synthetic Contoso Insurance claims data."""

from __future__ import annotations

import importlib.util
import re
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from conftest import DATA_DIR, forbidden_keys_in

AS_OF = date(2026, 11, 20)
RECORDS_AS_OF = "2026-11-20T08:00:00Z"
CLAIMS_SYSTEM_START = date(2023, 1, 1)
# Claims whose loss date is deliberately outside the policy period (see data/README.md).
OUT_OF_PERIOD_CLAIMS = {"CLM-10419": "expired", "CLM-10445": "cancelled"}

ID_FORMATS = {
    "customers": r"^CUST-\d{5}$",
    "policies": r"^PAP-\d{7}$",
    "vehicles": r"^VEH-\d{5}$",
    "claims": r"^CLM-\d{5}$",
    "archived": r"^AC-\d{4}-\d{5}$",
    "facilities": r"^RF-\d{3}$",
}
LIST_KEYS = {
    "customers.json": ("customers", "customerId"),
    "policies.json": ("policies", "policyId"),
    "vehicles.json": ("vehicles", "vehicleId"),
    "claims.json": ("claims", "claimId"),
    "claim-history.json": ("archivedClaims", "claimId"),
    "repair-facilities.json": ("repairFacilities", "repairFacilityId"),
}
VIN_VALUES = {**{str(i): i for i in range(10)}, **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))),
              "P": 7, "R": 9, **dict(zip("STUVWXYZ", range(2, 10)))}
VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
VIN_YEAR_CODES = dict(zip(range(2010, 2027), "ABCDEFGHJKLMNPRST"))


def d(value: str) -> date:
    return date.fromisoformat(value)


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def add_months(start: date, months: int) -> date:
    month = start.month - 1 + months
    return start.replace(year=start.year + month // 12, month=month % 12 + 1)


def coverage_end(policy: dict) -> date:
    """Exclusive end of the policy period: the cancellation date, else the term expiration date."""
    return d(policy["cancellation"]["effectiveDate"]) if policy["cancellation"] else d(policy["termExpirationDate"])


def listing(policy: dict, vehicle_id: str) -> dict:
    return next(v for v in policy["vehicles"] if v["vehicleId"] == vehicle_id)


def coverage(entry: dict, code: str) -> dict | None:
    return next((c for c in entry["coverages"] if c["coverageCode"] == code), None)


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_data", DATA_DIR / "generate_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Files, IDs and determinism
# ---------------------------------------------------------------------------


def test_every_file_is_marked_synthetic_with_one_snapshot_time(raw_files):
    assert set(raw_files) == set(LIST_KEYS)
    for name, payload in raw_files.items():
        assert payload["synthetic"] is True, name
        assert "synthetic" in payload["notice"].lower() and "fictional" in payload["notice"].lower(), name
        assert payload["recordsAsOf"] == RECORDS_AS_OF, name


def test_record_counts(raw_files):
    counts = {name: len(payload[LIST_KEYS[name][0]]) for name, payload in raw_files.items()}
    assert counts == {
        "customers.json": 30,
        "policies.json": 40,
        "vehicles.json": 35,
        "claims.json": 50,
        "claim-history.json": 12,
        "repair-facilities.json": 10,
    }


def test_ids_are_unique_and_well_formed(raw_files, data):
    for name, (list_key, id_key) in LIST_KEYS.items():
        ids = [r[id_key] for r in raw_files[name][list_key]]
        duplicates = [i for i, n in Counter(ids).items() if n > 1]
        assert not duplicates, f"{name}: duplicate IDs {duplicates}"
    for kind, pattern in ID_FORMATS.items():
        bad = [i for i in data[kind] if not re.match(pattern, i)]
        assert not bad, f"{kind}: malformed IDs {bad}"
    assert not set(data["claims"]) & set(data["archived"])
    document_ids = [doc["documentId"] for c in data["claims"].values() for doc in c["documents"]]
    assert len(document_ids) == len(set(document_ids))


def test_no_record_carries_an_assessment_or_conclusion_field(raw_files):
    for name, payload in raw_files.items():
        assert forbidden_keys_in(payload) == [], name


def test_generation_is_deterministic_and_files_are_current():
    generator = load_generator()
    first = {name: generator.serialize(content) for name, content in generator.build_dataset().items()}
    second = {name: generator.serialize(content) for name, content in generator.build_dataset().items()}
    assert first == second
    for name, text in first.items():
        assert (DATA_DIR / name).read_bytes() == text.encode("utf-8"), f"{name} differs from a fresh generation"
    assert generator.main(["--check"]) == 0


def test_data_files_use_lf_line_endings():
    for path in DATA_DIR.glob("*.json"):
        assert b"\r\n" not in path.read_bytes(), path.name


# ---------------------------------------------------------------------------
# Customers, vehicles and policies
# ---------------------------------------------------------------------------


def test_customer_cross_references(data):
    for customer in data["customers"].values():
        cid = customer["customerId"]
        assert customer["fullName"] == f"{customer['firstName']} {customer['lastName']}"
        owned_policies = sorted(p["policyId"] for p in data["policies"].values() if p["customerId"] == cid)
        owned_vehicles = sorted(v["vehicleId"] for v in data["vehicles"].values() if v["ownerCustomerId"] == cid)
        assert sorted(customer["policyIds"]) == owned_policies, cid
        assert sorted(customer["vehicleIds"]) == owned_vehicles, cid
        assert owned_policies, f"{cid} has no policy"
        for policy_id in owned_policies:
            assert d(customer["customerSince"]) <= d(data["policies"][policy_id]["inceptionDate"]), cid
        assert customer["email"].endswith("@example.com")
        assert re.fullmatch(r"\(\d{3}\) 555-01\d{2}", customer["phone"]), customer["phone"]


def test_policy_terms_and_statuses_are_coherent(data):
    for policy in data["policies"].values():
        pid = policy["policyId"]
        effective, expiration = d(policy["termEffectiveDate"]), d(policy["termExpirationDate"])
        assert policy["customerId"] in data["customers"], pid
        assert policy["termMonths"] in (6, 12), pid
        assert d(policy["inceptionDate"]) <= effective < expiration, pid
        assert add_months(effective, policy["termMonths"]) == expiration, pid
        assert policy["termPremium"] > 0
        status, cancellation = policy["status"], policy["cancellation"]
        if status == "Active":
            assert cancellation is None and effective <= AS_OF < expiration, pid
        elif status == "Expired":
            assert cancellation is None and expiration <= AS_OF, pid
        elif status == "Cancelled":
            assert cancellation is not None, pid
            assert effective < d(cancellation["effectiveDate"]) <= min(expiration, AS_OF), pid
        else:
            pytest.fail(f"{pid}: unknown status {status}")
        assert any(dr["relationship"] == "Named insured" for dr in policy["drivers"]), pid
        assert {c["coverageCode"] for c in policy["policyCoverages"]} >= {"BI", "PD"}, pid


def test_policy_vehicle_listings(data):
    for policy in data["policies"].values():
        pid = policy["policyId"]
        assert policy["vehicles"], pid
        assert any(v["removedDate"] is None for v in policy["vehicles"]), f"{pid} lists no current vehicle"
        for entry in policy["vehicles"]:
            vehicle = data["vehicles"][entry["vehicleId"]]
            assert vehicle["ownerCustomerId"] == policy["customerId"], (pid, entry["vehicleId"])
            added = d(entry["addedDate"])
            assert d(policy["inceptionDate"]) <= added, (pid, entry["vehicleId"])
            assert d(vehicle["acquiredDate"]) <= added, (pid, entry["vehicleId"])
            if entry["removedDate"]:
                assert added < d(entry["removedDate"]) <= AS_OF, (pid, entry["vehicleId"])
            if vehicle["disposedDate"]:
                assert entry["removedDate"] and d(entry["removedDate"]) <= d(vehicle["disposedDate"])
            codes = [c["coverageCode"] for c in entry["coverages"]]
            assert len(codes) == len(set(codes)), (pid, entry["vehicleId"])
            for code, allowed in (("COLL", {250, 500, 1000, 1500, 2000}), ("COMP", {100, 250, 500, 1000})):
                if cov := coverage(entry, code):
                    assert cov["deductible"] in allowed, (pid, code, cov["deductible"])
            for code in ("RENT", "ROAD", "GAP"):
                if cov := coverage(entry, code):
                    assert cov["deductible"] is None
            if "RENT" in codes or "GAP" in codes:
                assert "COLL" in codes, (pid, entry["vehicleId"])
            if vehicle["ownership"]["type"] in ("Financed", "Leased"):
                assert {"COLL", "COMP"} <= set(codes), (pid, entry["vehicleId"])
                assert entry["lossPayee"] == vehicle["ownership"]["lienholder"], (pid, entry["vehicleId"])
            else:
                assert entry["lossPayee"] is None


def test_vehicles(data):
    vins = [v["vin"] for v in data["vehicles"].values()]
    assert len(vins) == len(set(vins))
    for vehicle in data["vehicles"].values():
        vin = vehicle["vin"]
        assert re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin), vin
        assert vin.startswith("0"), "synthetic VINs use an unassigned WMI beginning with 0"
        check = sum(VIN_VALUES[ch] * w for ch, w in zip(vin, VIN_WEIGHTS)) % 11
        assert vin[8] == ("X" if check == 10 else str(check)), f"{vin}: bad check digit"
        assert vin[9] == VIN_YEAR_CODES[vehicle["year"]], vin
        assert vehicle["ownerCustomerId"] in data["customers"]
        assert vehicle["year"] - 1 <= d(vehicle["acquiredDate"]).year <= AS_OF.year
        lienholder = vehicle["ownership"]["lienholder"]
        assert (lienholder is None) == (vehicle["ownership"]["type"] == "Owned"), vehicle["vehicleId"]
        listed = [p for p in data["policies"].values() if any(e["vehicleId"] == vehicle["vehicleId"] for e in p["vehicles"])]
        assert listed, f"{vehicle['vehicleId']} is not on any policy"


def test_repair_facilities(data):
    for facility in data["facilities"].values():
        rates = facility["laborRates"]
        assert rates["bodyPerHour"] > 0 and rates["refinishPerHour"] > 0 and rates["mechanicalPerHour"] > 0
        assert re.fullmatch(r"\(\d{3}\) 555-01\d{2}", facility["phone"])


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


def test_claim_references_resolve(data):
    for claim in data["claims"].values():
        cid = claim["claimId"]
        policy = data["policies"][claim["policyId"]]
        assert claim["customerId"] == policy["customerId"], cid
        assert claim["customerId"] in data["customers"], cid
        assert claim["vehicleId"] in data["vehicles"], cid
        assert any(e["vehicleId"] == claim["vehicleId"] for e in policy["vehicles"]), cid
        if claim["repairFacilityId"]:
            assert claim["repairFacilityId"] in data["facilities"], cid
        if claim["estimate"]:
            assert claim["estimate"]["repairFacilityId"] == claim["repairFacilityId"], cid
            assert claim["estimate"]["grossAmount"] > 0, cid


def test_loss_dates_fall_within_policy_and_vehicle_periods(data):
    for claim in data["claims"].values():
        cid = claim["claimId"]
        policy = data["policies"][claim["policyId"]]
        entry = listing(policy, claim["vehicleId"])
        loss = d(claim["lossDate"])
        vehicle_end = d(entry["removedDate"]) if entry["removedDate"] else date.max
        assert d(entry["addedDate"]) <= loss < vehicle_end, cid
        assert d(policy["inceptionDate"]) <= loss, cid
        in_period = loss < coverage_end(policy)
        if cid in OUT_OF_PERIOD_CLAIMS:
            assert not in_period, f"{cid} should have a loss date after the policy period"
            assert policy["status"].lower() == OUT_OF_PERIOD_CLAIMS[cid]
        else:
            assert in_period, f"{cid}: loss date {loss} is outside the policy period"


def test_claim_types_match_listed_coverages(data):
    required = {"Collision": "COLL", "Comprehensive": "COMP"}
    causes = {
        "Collision": {"Two-vehicle collision", "Single-vehicle collision", "Hit while parked"},
        "Comprehensive": {"Animal strike", "Glass breakage", "Hail", "Theft", "Vandalism"},
        "Property Damage Liability": {"Property damage to another vehicle"},
    }
    for claim in data["claims"].values():
        assert claim["causeOfLoss"] in causes[claim["claimType"]], claim["claimId"]
        if code := required.get(claim["claimType"]):
            entry = listing(data["policies"][claim["policyId"]], claim["vehicleId"])
            assert coverage(entry, code) is not None, claim["claimId"]


def test_claim_dates_and_timestamps(data):
    as_of = ts(RECORDS_AS_OF)
    for claim in data["claims"].values():
        cid = claim["claimId"]
        loss = d(claim["lossDate"])
        assert CLAIMS_SYSTEM_START <= loss <= AS_OF, cid
        assert re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", claim["lossTime"]), cid
        tz = ZoneInfo(claim["lossTimeZone"])
        local_loss = datetime.combine(loss, datetime.strptime(claim["lossTime"], "%H:%M").time(), tz)
        reported = ts(claim["reportedAt"])
        assert local_loss < reported <= as_of, cid
        assert ts(claim["createdAt"]) == reported, cid
        assert reported <= ts(claim["lastUpdatedAt"]) <= as_of, cid
        for doc in claim["documents"]:
            received = ts(doc["receivedAt"])
            assert reported <= received <= ts(claim["lastUpdatedAt"]), (cid, doc["documentId"])
        if claim["closedDate"]:
            assert reported.astimezone(tz).date() <= d(claim["closedDate"]) <= AS_OF, cid
        if claim["estimate"]:
            assert loss <= d(claim["estimate"]["estimateDate"]) <= AS_OF, cid


def test_claim_numbers_follow_report_order(data):
    ordered = sorted(data["claims"].values(), key=lambda c: c["reportedAt"])
    assert [c["claimId"] for c in ordered] == sorted(data["claims"])


def test_claim_status_closure_and_settlement(data):
    for claim in data["claims"].values():
        cid = claim["claimId"]
        closed = claim["status"].startswith("Closed")
        assert (claim["closedDate"] is not None) == closed, cid
        assert (claim["closureReason"] is not None) == closed, cid
        settlement = claim["settlement"]
        assert (settlement is not None) == (claim["status"] == "Closed - Paid"), cid
        if claim["status"] == "Closed - Paid":
            assert claim["closureReason"] == "Payment issued", cid
        if settlement:
            assert round(settlement["settledAmount"] - settlement["deductibleApplied"], 2) == settlement["totalPaid"], cid
            assert settlement["totalPaid"] > 0, cid
            code = {"Collision": "COLL", "Comprehensive": "COMP"}.get(claim["claimType"])
            entry = listing(data["policies"][claim["policyId"]], claim["vehicleId"])
            expected = coverage(entry, code)["deductible"] if code else 0
            assert settlement["deductibleApplied"] == expected, cid


def test_claim_documents_and_police_details(data):
    for claim in data["claims"].values():
        cid = claim["claimId"]
        number = cid.split("-")[1]
        ids = [doc["documentId"] for doc in claim["documents"]]
        assert ids == [f"DOC-{number}-{i:02d}" for i in range(1, len(ids) + 1)], cid
        received = [doc["receivedAt"] for doc in claim["documents"]]
        assert received == sorted(received), cid
        types = Counter(doc["documentType"] for doc in claim["documents"])
        police = claim["policeReport"]
        if police["reportedToPolice"]:
            assert police["agency"] and police["reportNumber"], cid
        else:
            assert police["agency"] is None and police["reportNumber"] is None, cid
            assert types["Police report"] == 0, cid
        if claim["estimate"]:
            assert types["Repair estimate"] >= 1, cid
        if claim["otherParties"]:
            assert claim["causeOfLoss"] in ("Two-vehicle collision", "Property damage to another vehicle"), cid
        assert claim["reportedDamage"]["areas"], cid


# ---------------------------------------------------------------------------
# Archived claim history
# ---------------------------------------------------------------------------


def test_archived_claims(data):
    for archived in data["archived"].values():
        aid = archived["claimId"]
        loss = d(archived["lossDate"])
        assert loss < CLAIMS_SYSTEM_START, aid
        assert aid.startswith(f"AC-{loss.year}-"), aid
        policy = data["policies"][archived["policyId"]]
        vehicle = data["vehicles"][archived["vehicleId"]]
        assert archived["customerId"] == policy["customerId"] == vehicle["ownerCustomerId"], aid
        entry = listing(policy, archived["vehicleId"])
        assert d(entry["addedDate"]) <= loss, aid
        assert not entry["removedDate"] or loss < d(entry["removedDate"]), aid
        assert archived["vehicleDescription"] == f"{vehicle['year']} {vehicle['make']} {vehicle['model']}", aid
        assert loss <= d(archived["reportedDate"]) <= d(archived["closedDate"]) <= AS_OF, aid
        assert archived["status"].startswith("Closed"), aid
        amounts = (archived["settledAmount"], archived["deductibleApplied"], archived["totalPaid"])
        if archived["status"] == "Closed - Paid":
            assert round(amounts[0] - amounts[1], 2) == amounts[2] > 0, aid
        else:
            assert amounts == (None, None, None), aid


# ---------------------------------------------------------------------------
# Hero scenario facts
# ---------------------------------------------------------------------------


def test_hero_customer_policy_and_vehicle(data):
    customer = data["customers"]["CUST-24817"]
    assert customer["fullName"] == "Jordan Lee"
    assert customer["policyIds"] == ["PAP-4471920"]

    policy = data["policies"]["PAP-4471920"]
    assert policy["customerId"] == "CUST-24817"
    assert policy["status"] == "Active"
    assert policy["cancellation"] is None
    assert d(policy["termEffectiveDate"]) <= date(2026, 11, 12) < d(policy["termExpirationDate"])

    entry = listing(policy, "VEH-58213")
    assert entry["removedDate"] is None
    collision = coverage(entry, "COLL")
    assert collision is not None and collision["deductible"] == 1000

    vehicle = data["vehicles"]["VEH-58213"]
    assert (vehicle["year"], vehicle["make"], vehicle["model"]) == (2024, "Contoso", "Trailstar")
    assert vehicle["bodyStyle"].startswith("Sport utility vehicle")
    assert vehicle["ownerCustomerId"] == "CUST-24817"


def test_hero_claim(data):
    claim = data["claims"]["CLM-10482"]
    assert (claim["customerId"], claim["policyId"], claim["vehicleId"]) == ("CUST-24817", "PAP-4471920", "VEH-58213")
    assert claim["claimType"] == "Collision"
    assert claim["causeOfLoss"] == "Two-vehicle collision"
    assert claim["status"] == "In Review"
    assert claim["lossDate"] == "2026-11-12"
    assert len(claim["otherParties"]) == 1
    assert claim["policeReport"]["reportedToPolice"] is True
    assert claim["estimate"]["grossAmount"] == 7850.00
    assert claim["reportedDamage"]["areas"] == ["Rear bumper", "Right rear quarter panel", "Right tail lamp"]
    types = Counter(doc["documentType"] for doc in claim["documents"])
    assert types == {"Claim form": 1, "Photograph": 5, "Police report": 1, "Repair estimate": 1}
    assert claim["settlement"] is None and claim["closedDate"] is None


def test_hero_prior_claim_history(data):
    claims = [c for c in data["claims"].values() if c["customerId"] == "CUST-24817"]
    archived = [c for c in data["archived"].values() if c["customerId"] == "CUST-24817"]
    assert sorted(c["claimId"] for c in claims) == ["CLM-10329", "CLM-10482"]
    assert archived == []
    prior = data["claims"]["CLM-10329"]
    assert (prior["claimType"], prior["causeOfLoss"], prior["status"]) == ("Comprehensive", "Glass breakage", "Closed - Paid")
