"""Contoso Air Operations API (mock).

One FastAPI service exposes the three read-only operations the Foundry agent calls
through a single OpenAPI tool:

* get_customer_reservations    GET /customers/{customerId}/reservations
* get_flight_status            GET /flight-status/{flightNumber}?date=
* search_alternative_flights   GET /flight-search/alternatives

The hand-authored OpenAPI 3.0 definition (tools/openapi.json) is the contract given to
Foundry. It is served at /openapi.json with this host's URL filled in, ready to paste
into the Foundry portal. Each operation's route lives in its own module.

Run locally:  uvicorn main:app --app-dir tools --port 8000
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html

from common.data_store import get_store
from common.dates import demo_today
from common.errors import tool_error
from flight_search_api.router import router as flight_search_router
from flight_status_api.router import router as flight_status_router
from reservation_api.router import router as reservation_router

TOOLS_DIR = Path(__file__).resolve().parent
OPENAPI_SPEC = TOOLS_DIR / "openapi.json"
SERVER_PLACEHOLDER = "https://YOUR-TOOLS-API-HOST"

# FastAPI's generated schema is disabled so that /openapi.json serves the curated contract.
app = FastAPI(
    title="Contoso Air Operations API",
    description="Deterministic synthetic airline operations data for the Contoso Air Customer Care demo. All data is fictional.",
    version="1.0.0",
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)
app.include_router(reservation_router)
app.include_router(flight_status_router)
app.include_router(flight_search_router)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    details = "; ".join(f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
    return tool_error(400, "INVALID_REQUEST", details or "The request is invalid.")


@app.get("/health", include_in_schema=False)
def health():
    store = get_store()
    return {"status": "ok", "currentDate": demo_today().isoformat(), "flights": len(store.flights)}


def load_openapi_spec(server_url: str | None = None) -> dict:
    """Load the Operations API definition, optionally pointing it at ``server_url``."""
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
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Contoso Air Operations API")
