"""Contoso Insurance Claims Operations API.

Read-only access to Contoso Insurance claims-system records for the claims review
agent:

* ``get_claim``                   GET /claims/{claimId}
* ``get_policy``                  GET /policies/{policyId}
* ``get_customer_claim_history``  GET /customers/{customerId}/claim-history
* ``get_vehicle``                 GET /vehicles/{vehicleId}

The API answers "what do our business records say?". It returns stored facts only.
It does not interpret policy language, decide coverage, compare claim evidence,
score risk or recommend claim actions; those responsibilities belong to the agent
and the adjuster.

The hand-authored OpenAPI 3.0 definition (tools/openapi.json, built by
tools/build_openapi.py) is the contract given to Foundry. It is served at
/openapi.json with this host's public URL filled in.

All data is synthetic. Contoso Insurance is a fictional company.

Run locally from contoso-claims-processing/:

    uvicorn main:app --app-dir tools --port 8000
"""

from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = TOOLS_DIR.parent / "data"
OPENAPI_SPEC = TOOLS_DIR / "openapi.json"

OPERATIONS = ("get_claim", "get_policy", "get_customer_claim_history", "get_vehicle")
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

ID_PATTERNS = {
    "claim": re.compile(r"^CLM-\d{5}$"),
    "policy": re.compile(r"^PAP-\d{7}$"),
    "customer": re.compile(r"^CUST-\d{5}$"),
    "vehicle": re.compile(r"^VEH-\d{5}$"),
}
ID_EXAMPLES = {"claim": "CLM-10001", "policy": "PAP-1000001", "customer": "CUST-10001", "vehicle": "VEH-10001"}

# FastAPI's generated schema is disabled so that /openapi.json serves the curated contract.
app = FastAPI(
    title="Contoso Insurance Claims Operations API",
    version="1.0.0",
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)


# ---------------------------------------------------------------------------
# Errors
#
# Foundry's OpenAPI tool treats a non-2xx response as a failed tool call, so the
# model never sees the error body. Operation errors are therefore returned as HTTP
# 200 with {"error": {code, message, httpStatus, retryable}}. httpStatus records the
# conventional status for logs and clients.
# ---------------------------------------------------------------------------


def error_body(status_code: int, code: str, message: str) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "httpStatus": status_code,
            "retryable": status_code in RETRYABLE_STATUSES,
        }
    }


def tool_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=200, content=error_body(status_code, code, message))


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    return tool_error(400, "INVALID_REQUEST", "The request is not valid for this operation.")


def normalize_id(kind: str, raw: str) -> str | None:
    value = raw.strip().upper()
    return value if ID_PATTERNS[kind].match(value) else None


def invalid_id(kind: str, raw: str) -> JSONResponse:
    return tool_error(
        400,
        "INVALID_REQUEST",
        f"'{raw}' is not a valid {kind} ID. Expected the format {ID_EXAMPLES[kind]}.",
    )


def simulated_outage(operation_id: str) -> JSONResponse | None:
    """Demo/test switch: CLAIMS_API_SIMULATE_OUTAGE=all or a comma list of operationIds."""
    setting = os.environ.get("CLAIMS_API_SIMULATE_OUTAGE", "")
    targets = {item.strip() for item in setting.split(",") if item.strip()}
    if "all" in targets or operation_id in targets:
        return tool_error(
            503,
            "SERVICE_UNAVAILABLE",
            "The claims system is temporarily unavailable. The request can be retried later.",
        )
    return None


# ---------------------------------------------------------------------------
# Data store
# ---------------------------------------------------------------------------


class ClaimsStore:
    """In-memory, read-only view of the synthetic claims-system data files."""

    def __init__(self, data_dir: Path):
        def load(file_name: str, list_key: str, id_key: str) -> tuple[str, dict]:
            payload = json.loads((data_dir / file_name).read_text(encoding="utf-8"))
            return payload["recordsAsOf"], {r[id_key]: r for r in payload[list_key]}

        as_of_values = set()
        for attr, args in {
            "customers": ("customers.json", "customers", "customerId"),
            "policies": ("policies.json", "policies", "policyId"),
            "vehicles": ("vehicles.json", "vehicles", "vehicleId"),
            "claims": ("claims.json", "claims", "claimId"),
            "archived_claims": ("claim-history.json", "archivedClaims", "claimId"),
            "repair_facilities": ("repair-facilities.json", "repairFacilities", "repairFacilityId"),
        }.items():
            as_of, records = load(*args)
            as_of_values.add(as_of)
            setattr(self, attr, records)
        if len(as_of_values) != 1:
            raise RuntimeError(f"data files disagree on recordsAsOf: {sorted(as_of_values)}")
        self.records_as_of = as_of_values.pop()


@lru_cache(maxsize=1)
def get_store() -> ClaimsStore:
    return ClaimsStore(Path(os.environ.get("CLAIMS_DATA_DIR") or DEFAULT_DATA_DIR))


def vehicle_description(vehicle: dict) -> str:
    return f"{vehicle['year']} {vehicle['make']} {vehicle['model']} {vehicle['trim']}"


def history_vehicle_description(vehicle: dict) -> str:
    """Year, make and model: the form used by archived claim records."""
    return f"{vehicle['year']} {vehicle['make']} {vehicle['model']}"


def local_date(timestamp: str, time_zone: str) -> str:
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return moment.astimezone(ZoneInfo(time_zone)).date().isoformat()


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


@app.get("/claims/{claimId}")
def get_claim(claimId: str):
    if outage := simulated_outage("get_claim"):
        return outage
    claim_id = normalize_id("claim", claimId)
    if claim_id is None:
        return invalid_id("claim", claimId)
    store = get_store()
    claim = store.claims.get(claim_id)
    if claim is None:
        return tool_error(404, "CLAIM_NOT_FOUND", f"No claim with ID {claim_id} exists in the claims system.")

    facility = store.repair_facilities.get(claim["repairFacilityId"]) if claim["repairFacilityId"] else None
    facility_summary = None
    if facility:
        facility_summary = {
            key: facility[key]
            for key in ("repairFacilityId", "name", "networkStatus", "address", "phone")
        }
    return {"recordsAsOf": store.records_as_of, "claim": claim, "repairFacility": facility_summary}


@app.get("/policies/{policyId}")
def get_policy(policyId: str):
    if outage := simulated_outage("get_policy"):
        return outage
    policy_id = normalize_id("policy", policyId)
    if policy_id is None:
        return invalid_id("policy", policyId)
    store = get_store()
    policy = store.policies.get(policy_id)
    if policy is None:
        return tool_error(404, "POLICY_NOT_FOUND", f"No policy with ID {policy_id} exists in the policy system.")

    customer = store.customers[policy["customerId"]]
    listed = []
    for entry in policy["vehicles"]:
        vehicle = store.vehicles[entry["vehicleId"]]
        listed.append(
            {
                "vehicleId": vehicle["vehicleId"],
                "vin": vehicle["vin"],
                "description": vehicle_description(vehicle),
                "bodyStyle": vehicle["bodyStyle"],
            }
        )
    return {
        "recordsAsOf": store.records_as_of,
        "policy": policy,
        "policyholder": {
            "customerId": customer["customerId"],
            "fullName": customer["fullName"],
            "address": customer["address"],
        },
        "vehicleDetails": listed,
    }


@app.get("/customers/{customerId}/claim-history")
def get_customer_claim_history(customerId: str):
    if outage := simulated_outage("get_customer_claim_history"):
        return outage
    customer_id = normalize_id("customer", customerId)
    if customer_id is None:
        return invalid_id("customer", customerId)
    store = get_store()
    customer = store.customers.get(customer_id)
    if customer is None:
        return tool_error(404, "CUSTOMER_NOT_FOUND", f"No customer with ID {customer_id} exists.")

    entries = []
    for claim in store.claims.values():
        if claim["customerId"] != customer_id:
            continue
        settlement = claim["settlement"] or {}
        entries.append(
            {
                "claimId": claim["claimId"],
                "recordSource": "Claims system",
                "policyId": claim["policyId"],
                "vehicleId": claim["vehicleId"],
                "vehicleDescription": history_vehicle_description(store.vehicles[claim["vehicleId"]]),
                "claimType": claim["claimType"],
                "causeOfLoss": claim["causeOfLoss"],
                "lossDate": claim["lossDate"],
                "reportedDate": local_date(claim["reportedAt"], claim["lossTimeZone"]),
                "status": claim["status"],
                "closedDate": claim["closedDate"],
                "settledAmount": settlement.get("settledAmount"),
                "deductibleApplied": settlement.get("deductibleApplied"),
                "totalPaid": settlement.get("totalPaid"),
            }
        )
    for archived in store.archived_claims.values():
        if archived["customerId"] != customer_id:
            continue
        entry = {key: value for key, value in archived.items() if key != "customerId"}
        entry["recordSource"] = "Archive"
        entries.append(entry)

    entries.sort(key=lambda e: (e["lossDate"], e["claimId"]), reverse=True)
    key_order = (
        "claimId", "recordSource", "policyId", "vehicleId", "vehicleDescription", "claimType", "causeOfLoss",
        "lossDate", "reportedDate", "status", "closedDate", "settledAmount", "deductibleApplied", "totalPaid",
    )
    claims = [{key: entry[key] for key in key_order} for entry in entries]
    return {
        "recordsAsOf": store.records_as_of,
        "customer": {
            "customerId": customer["customerId"],
            "fullName": customer["fullName"],
            "customerSince": customer["customerSince"],
        },
        "claimCount": len(claims),
        "claims": claims,
    }


@app.get("/vehicles/{vehicleId}")
def get_vehicle(vehicleId: str):
    if outage := simulated_outage("get_vehicle"):
        return outage
    vehicle_id = normalize_id("vehicle", vehicleId)
    if vehicle_id is None:
        return invalid_id("vehicle", vehicleId)
    store = get_store()
    vehicle = store.vehicles.get(vehicle_id)
    if vehicle is None:
        return tool_error(404, "VEHICLE_NOT_FOUND", f"No vehicle with ID {vehicle_id} exists.")

    owner = store.customers[vehicle["ownerCustomerId"]]
    listings = []
    for policy in sorted(store.policies.values(), key=lambda p: p["policyId"]):
        for entry in policy["vehicles"]:
            if entry["vehicleId"] == vehicle_id:
                listings.append(
                    {
                        "policyId": policy["policyId"],
                        "policyStatus": policy["status"],
                        "addedDate": entry["addedDate"],
                        "removedDate": entry["removedDate"],
                        "coverageCodes": [c["coverageCode"] for c in entry["coverages"]],
                    }
                )
    currently_listed = any(l["policyStatus"] == "Active" and l["removedDate"] is None for l in listings)
    return {
        "recordsAsOf": store.records_as_of,
        "vehicle": vehicle,
        "owner": {"customerId": owner["customerId"], "fullName": owner["fullName"]},
        "insurance": {"listedOnActivePolicy": currently_listed, "policies": listings},
    }


# ---------------------------------------------------------------------------
# Service endpoints
# ---------------------------------------------------------------------------


@app.get("/health", include_in_schema=False)
def health():
    store = get_store()
    return {
        "status": "ok",
        "recordsAsOf": store.records_as_of,
        "claims": len(store.claims),
        "policies": len(store.policies),
    }


def load_openapi_spec(server_url: str | None = None) -> dict:
    """Load the Claims Operations API definition, optionally pointing it at ``server_url``."""
    spec = json.loads(OPENAPI_SPEC.read_text(encoding="utf-8"))
    if server_url:
        spec = copy.deepcopy(spec)
        spec["servers"] = [{"url": server_url.rstrip("/")}]
    return spec


@app.get("/openapi.json", include_in_schema=False)
def openapi_spec(request: Request):
    public_url = os.environ.get("TOOLS_API_PUBLIC_URL") or str(request.base_url)
    return load_openapi_spec(public_url)


@app.get("/docs", include_in_schema=False)
def docs():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Contoso Insurance Claims Operations API")
