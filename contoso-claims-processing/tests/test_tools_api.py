"""Claims Operations API tests: contract conformance, factual responses and error behavior."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import build_openapi
import main
from conftest import ROOT, forbidden_keys_in
from openapi_validation import iter_schemas, response_schema, validate

TOOLS_DIR = ROOT / "tools"
SPEC = json.loads((TOOLS_DIR / "openapi.json").read_text(encoding="utf-8"))
OPERATIONS = {
    "get_claim": ("/claims/{claimId}", "claimId", "claims", "CLAIM_NOT_FOUND", "CLM-99999"),
    "get_policy": ("/policies/{policyId}", "policyId", "policies", "POLICY_NOT_FOUND", "PAP-9999999"),
    "get_customer_claim_history": (
        "/customers/{customerId}/claim-history", "customerId", "customers", "CUSTOMER_NOT_FOUND", "CUST-99999",
    ),
    "get_vehicle": ("/vehicles/{vehicleId}", "vehicleId", "vehicles", "VEHICLE_NOT_FOUND", "VEH-99999"),
}
DATA_KEYS = {
    "get_claim": {"recordsAsOf", "claim", "repairFacility"},
    "get_policy": {"recordsAsOf", "policy", "policyholder", "vehicleDetails"},
    "get_customer_claim_history": {"recordsAsOf", "customer", "claimCount", "claims"},
    "get_vehicle": {"recordsAsOf", "vehicle", "owner", "insurance"},
}


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def no_simulated_outage(monkeypatch):
    monkeypatch.delenv("CLAIMS_API_SIMULATE_OUTAGE", raising=False)
    monkeypatch.delenv("TOOLS_API_PUBLIC_URL", raising=False)


def call(client: TestClient, operation_id: str, record_id: str) -> dict:
    path = OPERATIONS[operation_id][0]
    url = re.sub(r"\{[^}]+\}", record_id, path)
    response = client.get(url)
    assert response.status_code == 200, (url, response.status_code)
    assert response.headers["content-type"].startswith("application/json")
    return response.json()


def assert_conforms(operation_id: str, body: dict) -> None:
    errors = validate(body, response_schema(SPEC, OPERATIONS[operation_id][0]))
    assert errors == [], f"{operation_id}: {errors[:5]}"


# ---------------------------------------------------------------------------
# OpenAPI contract
# ---------------------------------------------------------------------------


def test_openapi_file_is_current():
    assert build_openapi.main(["--check"]) == 0


def test_openapi_operations_match_the_application_routes():
    assert SPEC["openapi"] == "3.0.3"
    spec_ops = {op["operationId"]: (path, method) for path, item in SPEC["paths"].items() for method, op in item.items()}
    assert spec_ops == {op_id: (path, "get") for op_id, (path, *_rest) in OPERATIONS.items()}
    routes = {
        route.path: route.name
        for route in main.app.routes
        if getattr(route, "include_in_schema", False) and hasattr(route, "methods")
    }
    assert routes == {path: op_id for op_id, (path, *_rest) in OPERATIONS.items()}
    for op_id, (path, param, *_rest) in OPERATIONS.items():
        parameters = SPEC["paths"][path]["get"]["parameters"]
        assert [(p["name"], p["in"], p["required"]) for p in parameters] == [(param, "path", True)]
    assert SPEC["servers"] == [{"url": build_openapi.PLACEHOLDER_SERVER}]


def test_openapi_schemas_are_closed_and_inline():
    assert "$ref" not in json.dumps(SPEC)
    assert "components" not in SPEC
    for op_id, (path, *_rest) in OPERATIONS.items():
        for where, schema in iter_schemas(response_schema(SPEC, path)):
            assert schema.get("description"), f"{op_id} {where}: missing description"
            if schema.get("type") == "object":
                assert schema.get("additionalProperties") is False, f"{op_id} {where}"
                if where != "$":
                    assert sorted(schema["required"]) == sorted(schema["properties"]), f"{op_id} {where}"


def test_openapi_property_names_carry_no_assessment_fields():
    names = set()
    for _op_id, (path, *_rest) in OPERATIONS.items():
        for _where, schema in iter_schemas(response_schema(SPEC, path)):
            names.update(schema.get("properties", {}))
    assert forbidden_keys_in({name: None for name in names}) == []


def test_api_code_and_contract_contain_no_hero_specific_values():
    hero_literals = ["10482", "Jordan", "Lee", "headlamp", "4471920", "58213", "24817", "Trailstar", "Harborline"]
    for path in [*TOOLS_DIR.glob("*.py"), TOOLS_DIR / "openapi.json"]:
        text = path.read_text(encoding="utf-8")
        found = [literal for literal in hero_literals if re.search(rf"\b{literal}\b", text, re.IGNORECASE)]
        assert found == [], f"{path.name}: {found}"


# ---------------------------------------------------------------------------
# Every record conforms to the contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("operation_id", list(OPERATIONS))
def test_every_record_returns_a_conforming_factual_response(client, data, operation_id):
    collection = OPERATIONS[operation_id][2]
    assert data[collection]
    for record_id in data[collection]:
        body = call(client, operation_id, record_id)
        assert "error" not in body, (record_id, body.get("error"))
        assert set(body) == DATA_KEYS[operation_id], record_id
        assert body["recordsAsOf"] == "2026-11-20T08:00:00Z"
        assert_conforms(operation_id, body)
        assert forbidden_keys_in(body) == [], record_id


def test_get_claim_returns_the_record_unchanged(client, data):
    for claim_id, claim in data["claims"].items():
        body = call(client, "get_claim", claim_id)
        assert body["claim"] == claim
        facility_id = claim["repairFacilityId"]
        if facility_id is None:
            assert body["repairFacility"] is None
        else:
            facility = data["facilities"][facility_id]
            assert body["repairFacility"] == {
                key: facility[key] for key in ("repairFacilityId", "name", "networkStatus", "address", "phone")
            }


def test_get_policy_resolves_policyholder_and_vehicles(client, data):
    for policy_id, policy in data["policies"].items():
        body = call(client, "get_policy", policy_id)
        assert body["policy"] == policy
        customer = data["customers"][policy["customerId"]]
        assert body["policyholder"] == {
            "customerId": customer["customerId"], "fullName": customer["fullName"], "address": customer["address"],
        }
        listed = [v["vehicleId"] for v in policy["vehicles"]]
        assert [v["vehicleId"] for v in body["vehicleDetails"]] == listed
        for details in body["vehicleDetails"]:
            vehicle = data["vehicles"][details["vehicleId"]]
            assert details["vin"] == vehicle["vin"]
            assert details["description"] == f"{vehicle['year']} {vehicle['make']} {vehicle['model']} {vehicle['trim']}"


def test_claim_history_is_complete_and_ordered(client, data):
    empty = 0
    for customer_id in data["customers"]:
        body = call(client, "get_customer_claim_history", customer_id)
        expected = {c["claimId"] for c in data["claims"].values() if c["customerId"] == customer_id}
        expected |= {c["claimId"] for c in data["archived"].values() if c["customerId"] == customer_id}
        ids = [entry["claimId"] for entry in body["claims"]]
        assert set(ids) == expected and len(ids) == len(expected), customer_id
        assert body["claimCount"] == len(expected)
        keys = [(entry["lossDate"], entry["claimId"]) for entry in body["claims"]]
        assert keys == sorted(keys, reverse=True), customer_id
        for entry in body["claims"]:
            source = data["claims"].get(entry["claimId"]) or data["archived"][entry["claimId"]]
            assert entry["recordSource"] == ("Claims system" if entry["claimId"] in data["claims"] else "Archive")
            for key in ("policyId", "vehicleId", "claimType", "causeOfLoss", "lossDate", "status", "closedDate"):
                assert entry[key] == source[key], (entry["claimId"], key)
            settlement = source.get("settlement") if entry["recordSource"] == "Claims system" else source
            for key in ("settledAmount", "deductibleApplied", "totalPaid"):
                assert entry[key] == (settlement[key] if settlement else None), (entry["claimId"], key)
        empty += not expected
    assert empty >= 1, "the dataset should include customers with no claims"


def test_vehicle_insurance_listing_matches_policy_records(client, data):
    for vehicle_id in data["vehicles"]:
        body = call(client, "get_vehicle", vehicle_id)
        listings = [
            (policy, entry)
            for policy in data["policies"].values()
            for entry in policy["vehicles"]
            if entry["vehicleId"] == vehicle_id
        ]
        assert sorted(p["policyId"] for p in body["insurance"]["policies"]) == sorted(p["policyId"] for p, _ in listings)
        expected = any(p["status"] == "Active" and e["removedDate"] is None for p, e in listings)
        assert body["insurance"]["listedOnActivePolicy"] is expected, vehicle_id


# ---------------------------------------------------------------------------
# Hero scenario through the API
# ---------------------------------------------------------------------------


def test_hero_scenario_facts(client):
    claim = call(client, "get_claim", "CLM-10482")
    assert claim["claim"]["customerId"] == "CUST-24817"
    assert claim["claim"]["claimType"] == "Collision"
    assert claim["claim"]["causeOfLoss"] == "Two-vehicle collision"
    assert claim["claim"]["estimate"]["grossAmount"] == 7850.00
    assert claim["repairFacility"]["repairFacilityId"] == "RF-104"

    policy = call(client, "get_policy", "PAP-4471920")
    assert policy["policy"]["status"] == "Active"
    assert policy["policyholder"]["fullName"] == "Jordan Lee"
    hero_listing = next(v for v in policy["policy"]["vehicles"] if v["vehicleId"] == "VEH-58213")
    collision = next(c for c in hero_listing["coverages"] if c["coverageCode"] == "COLL")
    assert collision["deductible"] == 1000

    vehicle = call(client, "get_vehicle", "VEH-58213")
    assert vehicle["vehicle"]["model"] == "Trailstar" and vehicle["vehicle"]["year"] == 2024
    assert vehicle["insurance"]["listedOnActivePolicy"] is True

    history = call(client, "get_customer_claim_history", "CUST-24817")
    assert [c["claimId"] for c in history["claims"]] == ["CLM-10482", "CLM-10329"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("operation_id", list(OPERATIONS))
def test_unknown_ids_return_not_found(client, operation_id):
    *_rest, not_found_code, unknown_id = OPERATIONS[operation_id]
    body = call(client, operation_id, unknown_id)
    assert body == {"error": {**body["error"], "code": not_found_code, "httpStatus": 404, "retryable": False}}
    assert unknown_id in body["error"]["message"]
    assert_conforms(operation_id, body)


@pytest.mark.parametrize("operation_id", list(OPERATIONS))
@pytest.mark.parametrize("bad_id", ["12345", "CLM-1", "XYZ-00000", "CLM-10482;DROP", "%20"])
def test_malformed_ids_return_invalid_request(client, operation_id, bad_id):
    body = call(client, operation_id, bad_id)
    assert set(body) == {"error"}
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["httpStatus"] == 400 and body["error"]["retryable"] is False
    assert_conforms(operation_id, body)


@pytest.mark.parametrize(
    "operation_id, raw_id, canonical",
    [
        ("get_claim", "clm-10482", "CLM-10482"),
        ("get_policy", "%20pap-4471920%20", "PAP-4471920"),
        ("get_customer_claim_history", "cust-24817", "CUST-24817"),
        ("get_vehicle", "Veh-58213", "VEH-58213"),
    ],
)
def test_ids_are_case_insensitive_and_trimmed(client, operation_id, raw_id, canonical):
    body = call(client, operation_id, raw_id)
    assert "error" not in body
    assert canonical in json.dumps(body)


def test_simulated_outage_for_all_operations(client, monkeypatch):
    monkeypatch.setenv("CLAIMS_API_SIMULATE_OUTAGE", "all")
    for operation_id in OPERATIONS:
        body = call(client, operation_id, "not-even-valid")
        assert set(body) == {"error"}
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert body["error"]["httpStatus"] == 503 and body["error"]["retryable"] is True
        assert_conforms(operation_id, body)


def test_simulated_outage_for_one_operation(client, monkeypatch):
    monkeypatch.setenv("CLAIMS_API_SIMULATE_OUTAGE", "get_policy")
    assert call(client, "get_policy", "PAP-4471920")["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "error" not in call(client, "get_claim", "CLM-10482")
    assert "error" not in call(client, "get_vehicle", "VEH-58213")


def test_unsupported_methods_are_rejected(client):
    assert client.post("/claims/CLM-10482").status_code == 405
    assert client.delete("/policies/PAP-4471920").status_code == 405


# ---------------------------------------------------------------------------
# Service endpoints
# ---------------------------------------------------------------------------


def test_served_openapi_points_at_the_running_service(client, monkeypatch):
    served = client.get("/openapi.json").json()
    assert served["servers"] == [{"url": "http://testserver"}]
    assert served["paths"] == SPEC["paths"]
    monkeypatch.setenv("TOOLS_API_PUBLIC_URL", "https://claims-tools.example.com/")
    assert client.get("/openapi.json").json()["servers"] == [{"url": "https://claims-tools.example.com"}]


def test_health_and_docs(client, data):
    health = client.get("/health").json()
    assert health == {
        "status": "ok", "recordsAsOf": "2026-11-20T08:00:00Z",
        "claims": len(data["claims"]), "policies": len(data["policies"]),
    }
    docs = client.get("/docs")
    assert docs.status_code == 200 and "swagger" in docs.text.lower()


def test_store_rejects_inconsistent_snapshots(tmp_path: Path):
    for source in (ROOT / "data").glob("*.json"):
        (tmp_path / source.name).write_bytes(source.read_bytes())
    altered = json.loads((tmp_path / "claims.json").read_text(encoding="utf-8"))
    altered["recordsAsOf"] = "2026-11-21T08:00:00Z"
    (tmp_path / "claims.json").write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(RuntimeError):
        main.ClaimsStore(tmp_path)
