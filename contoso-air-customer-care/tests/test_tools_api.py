import json
import re

import pytest
from fastapi.testclient import TestClient

from main import OPENAPI_SPEC, SERVER_PLACEHOLDER, app

TODAY, TOMORROW = "2026-05-14", "2026-05-15"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def option_summary(body):
    return [(o["flightNumbers"], o["totalSeatsAvailable"]) for o in body["options"]]


# --- Reservation API ----------------------------------------------------------------

def test_hero_reservation(client):
    body = client.get("/customers/CUST-1007/reservations").json()
    assert body["currentDate"] == TODAY
    assert body["customer"] == {"customerId": "CUST-1007", "firstName": "Alex", "lastName": "Johnson",
                                "loyaltyNumber": "CA8475921", "loyaltyTier": "Gold", "homeAirport": "SEA"}
    (res,) = body["reservations"]
    assert res["confirmationCode"] == "CT8K2P" and res["cabin"] == "Economy Plus" and res["status"] == "Confirmed"
    assert [p["firstName"] for p in res["passengers"]] == ["Alex", "Jamie", "Taylor", "Jordan"]
    assert [p["passengerType"] for p in res["passengers"]] == ["Adult", "Adult", "Child", "Child"]
    seg = res["segments"][0]
    assert (seg["flightNumber"], seg["date"], seg["origin"], seg["destination"]) == ("CT218", TOMORROW, "SEA", "JFK")
    assert seg["scheduledDeparture"] == f"{TOMORROW}T10:30"


def test_dates_rebase_to_current_day(client, monkeypatch):
    monkeypatch.setenv("DEMO_TODAY", "2026-09-30")
    body = client.get("/customers/CUST-1007/reservations").json()
    assert body["currentDate"] == "2026-09-30"
    assert body["reservations"][0]["segments"][0]["date"] == "2026-10-01"
    status = client.get("/flight-status/CT218", params={"date": "2026-10-01"}).json()
    assert status["status"] == "Cancelled" and status["date"] == "2026-10-01"
    search = client.get("/flight-search/alternatives", params={
        "origin": "SEA", "destination": "JFK", "travelDate": "2026-10-01", "passengerCount": 4}).json()
    assert [o["flightNumbers"] for o in search["options"]] == [["CT310", "CT442"], ["CT226"], ["CT232"]]


def agent_error(resp, http_status):
    """Tool errors are HTTP 200 so Foundry passes them to the model (see common/errors.py)."""
    assert resp.status_code == 200
    error = resp.json()["error"]
    assert error["httpStatus"] == http_status
    return error


def test_lookup_by_confirmation_code(client):
    assert client.get("/customers/CUST-1007/reservations", params={"confirmationCode": "ct8k2p"}).status_code == 200
    for cid, code in (("CUST-1019", "QX7M4R"), ("CUST-1019", "CT8K2P")):
        resp = client.get(f"/customers/{cid}/reservations", params={"confirmationCode": code})
        assert agent_error(resp, 404)["code"] == "RESERVATION_NOT_FOUND"


def test_customer_without_upcoming_trips(client):
    body = client.get("/customers/CUST-1019/reservations").json()
    assert body["reservations"] == [] and "no upcoming" in body["message"].lower()


def test_unknown_customer(client):
    resp = client.get("/customers/CUST-9999/reservations")
    assert agent_error(resp, 404)["code"] == "CUSTOMER_NOT_FOUND"


# --- Flight Status API --------------------------------------------------------------

def test_ct218_is_cancelled_by_carrier(client):
    body = client.get("/flight-status/CT218", params={"date": TOMORROW}).json()
    assert body["status"] == "Cancelled" and body["isCancelled"] is True
    assert body["scheduledDeparture"] == f"{TOMORROW}T10:30" and body["estimatedDeparture"] is None
    assert body["disruption"]["responsibility"] == "Carrier"
    assert body["disruption"]["category"] == "Controllable"
    assert body["disruption"]["reason"] == "Operational disruption"
    assert body["lastUpdated"] == f"{TODAY}T06:12"


def test_last_updated_is_never_after_now(client, monkeypatch):
    monkeypatch.setenv("DEMO_TIME", "05:30")
    body = client.get("/flight-status/CT218", params={"date": TOMORROW}).json()
    assert body["status"] == "Cancelled" and body["lastUpdated"] == f"{TODAY}T05:30"
    # CT760 departs Dallas (two hours ahead of Seattle): its clamp is in Dallas local time.
    monkeypatch.setenv("DEMO_TIME", "00:30")
    assert client.get("/flight-status/CT760", params={"date": TOMORROW}).json()["lastUpdated"] == f"{TODAY}T02:30"


def test_unknown_flight(client):
    resp = client.get("/flight-status/CT999", params={"date": TOMORROW})
    assert agent_error(resp, 404)["code"] == "FLIGHT_NOT_FOUND"


def test_flight_not_operating_that_day(client):
    resp = client.get("/flight-status/CT218", params={"date": "2026-08-01"})
    assert agent_error(resp, 404)["code"] == "FLIGHT_NOT_FOUND"


def test_fault_injection_reports_unavailable(client):
    resp = client.get("/flight-status/CT655", params={"date": TOMORROW})
    error = agent_error(resp, 503)
    assert error["code"] == "SERVICE_UNAVAILABLE" and error["retryable"] is True


def test_conflicting_record_flight_operates(client):
    assert client.get("/flight-status/CT472", params={"date": "2026-05-16"}).json()["status"] == "On Time"


def test_invalid_date_uses_error_shape(client):
    resp = client.get("/flight-status/CT218", params={"date": "tomorrow"})
    assert agent_error(resp, 400)["code"] == "INVALID_REQUEST"


# --- Flight Search API --------------------------------------------------------------

def search(client, origin, destination, travel_date, count=1, cabin=None, **extra):
    params = {"origin": origin, "destination": destination, "travelDate": travel_date, "passengerCount": count, **extra}
    if cabin:
        params["preferredCabin"] = cabin
    return client.get("/flight-search/alternatives", params=params).json()


FORBIDDEN_KEY_PARTS = ("eligib", "recommend", "rank", "score", "best", "prefer", "suitab", "policy")


def keys(value, path=""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield f"{path}.{k}", k
            yield from keys(v, f"{path}.{k}")
    elif isinstance(value, list):
        for item in value:
            yield from keys(item, path)


def test_hero_alternatives_are_chronological_facts(client):
    body = search(client, "SEA", "JFK", TOMORROW, 4, "Economy Plus")
    # Chronological by departure: the 07:10 connection, then CT226 (09:20), then CT232 (15:45).
    assert option_summary(body) == [(["CT310", "CT442"], 6), (["CT226"], 16), (["CT232"], 3)]
    assert [o["optionId"] for o in body["options"]] == ["OPT-1", "OPT-2", "OPT-3"]
    conn, ct226, ct232 = body["options"]
    assert conn["type"] == "Connection" and conn["connectionAirport"] == "ORD" and conn["layoverMinutes"] == 110
    assert conn["departureLocal"] == f"{TOMORROW}T07:10" and conn["arrivalLocal"] == f"{TOMORROW}T18:20"
    assert conn["cabinAvailability"] == {"First": 0, "Economy Plus": 2, "Main Cabin": 4}
    assert ct226["type"] == "Nonstop" and ct226["departureLocal"] == f"{TOMORROW}T09:20"
    assert ct226["arrivalLocal"] == f"{TOMORROW}T17:45"
    assert ct226["cabinAvailability"] == {"First": 1, "Economy Plus": 6, "Main Cabin": 9}
    assert ct232["departureLocal"] == f"{TOMORROW}T15:45" and ct232["arrivalLocal"] == "2026-05-16T00:10"
    assert ct232["cabinAvailability"] == {"First": 0, "Economy Plus": 1, "Main Cabin": 2}
    assert all(seg["status"] == "On Time" for o in body["options"] for seg in o["segments"])
    assert body["search"] == {"origin": "SEA", "destination": "JFK", "travelDate": TOMORROW, "passengerCount": 4,
                              "preferredCabin": "Economy Plus", "preferNonstop": None}


def test_responses_contain_no_policy_or_recommendation_fields(client):
    responses = [
        client.get("/customers/CUST-1007/reservations").json(),
        client.get("/flight-status/CT218", params={"date": TOMORROW}).json(),
        search(client, "SEA", "JFK", TOMORROW, 4, "Economy Plus"),
        search(client, "SFO", "BOS", TOMORROW, 4),
    ]
    for body in responses:
        for path, key in keys(body):
            if path.startswith(".search."):
                continue  # echoed request inputs, e.g. preferredCabin
            assert not any(part in key.lower() for part in FORBIDDEN_KEY_PARTS), path
    assert "eligib" not in json.dumps(responses).lower()
    assert "recommend" not in json.dumps(responses).lower()


def test_context_parameters_do_not_filter_or_reorder(client):
    baseline = search(client, "SEA", "JFK", TOMORROW)
    for kwargs in ({"count": 4, "cabin": "Economy Plus"}, {"count": 9, "cabin": "First"},
                   {"count": 4, "preferNonstop": "true"}):
        body = search(client, "SEA", "JFK", TOMORROW, **kwargs)
        assert body["options"] == baseline["options"]


def test_connection_availability_is_per_cabin_minimum_across_legs(client):
    for args in (("SEA", "JFK", TOMORROW), ("SFO", "BOS", TOMORROW), ("LAX", "ORD", "2026-05-16"),
                 ("PDX", "BOS", "2026-05-17")):
        for option in search(client, *args)["options"]:
            legs = option["segments"]
            assert option["cabinAvailability"] == {c: min(leg["cabinAvailability"][c] for leg in legs)
                                                   for c in ("First", "Economy Plus", "Main Cabin")}
            assert option["totalSeatsAvailable"] == sum(option["cabinAvailability"].values())
            assert option["stops"] == len(legs) - 1


def test_same_day_search_excludes_departed_flights(client, monkeypatch):
    # CT144 SEA->DFW departs 11:55 Seattle time (the demo time zone) today.
    monkeypatch.setenv("DEMO_TIME", "11:54")
    assert option_summary(search(client, "SEA", "DFW", TODAY))[0][0] == ["CT144"]
    monkeypatch.setenv("DEMO_TIME", "11:55")
    body = search(client, "SEA", "DFW", TODAY)
    assert "error" not in body and body["resultCount"] == 0


def test_cancelled_flights_never_offered(client):
    for args in (("SEA", "JFK", TOMORROW), ("SFO", "BOS", TOMORROW)):
        for option in search(client, *args)["options"]:
            assert "CT218" not in option["flightNumbers"]
            assert all(seg["status"] != "Cancelled" for seg in option["segments"])


def test_hero_day_has_unrelated_seattle_departures(client):
    for destination in ("LAX", "SFO", "DEN"):
        assert search(client, "SEA", destination, TOMORROW)["resultCount"] >= 1


def test_b1_no_option_seats_four_same_day(client):
    body = search(client, "SFO", "BOS", TOMORROW, 4)
    assert option_summary(body) == [(["CT352", "CT460"], 2), (["CT544"], 2)]
    next_day = search(client, "SFO", "BOS", "2026-05-16", 4)
    assert option_summary(next_day) == [(["CT540"], 11)]


def test_b2_nonstop_and_connection_both_fit(client):
    body = search(client, "LAX", "ORD", "2026-05-16", 2)
    assert option_summary(body) == [(["CT720", "CT820"], 4), (["CT614"], 5)]


def test_b3_only_connection_fits(client):
    body = search(client, "PDX", "BOS", "2026-05-17", 3)
    assert option_summary(body) == [(["CT372", "CT466"], 5), (["CT584"], 2)]


def test_empty_result_is_not_an_error(client, monkeypatch):
    monkeypatch.setenv("DEMO_TIME", "23:59")
    body = search(client, "SEA", "DFW", TODAY)
    assert "error" not in body and body["options"] == [] and body["resultCount"] == 0
    assert "eligible" not in body["message"].lower()


def test_search_validation(client):
    assert search(client, "SEA", "XXX", TOMORROW)["error"]["code"] == "UNKNOWN_AIRPORT"
    assert search(client, "SEA", "SEA", TOMORROW)["error"]["code"] == "INVALID_ROUTE"
    assert search(client, "SEA", "JFK", "2026-05-01")["error"]["code"] == "DATE_IN_PAST"
    assert search(client, "SEA", "JFK", "2026-02-30")["error"]["code"] == "INVALID_DATE"
    assert search(client, "SEA", "JFK", TOMORROW, cabin="Business")["error"]["code"] == "INVALID_CABIN"
    assert search(client, "SEA", "JFK", TOMORROW, count=10)["error"]["code"] == "INVALID_REQUEST"


# --- OpenAPI definitions -------------------------------------------------------------

AGENT_OPERATIONS = {"get_customer_reservations", "get_flight_status", "search_alternative_flights"}


def load_spec():
    return json.loads(OPENAPI_SPEC.read_text(encoding="utf-8"))


def test_single_spec_exposes_three_agent_operations():
    spec = load_spec()
    assert spec["openapi"].startswith("3.0")
    assert spec["info"]["title"] == "Contoso Air Operations API"
    assert spec["servers"] == [{"url": SERVER_PLACEHOLDER}]
    assert "$ref" not in json.dumps(spec)
    operations = [op for methods in spec["paths"].values() for op in methods.values()]
    assert {op["operationId"] for op in operations} == AGENT_OPERATIONS and len(operations) == 3
    assert not list(OPENAPI_SPEC.parent.glob("*/openapi.json")), "only one OpenAPI specification is allowed"


def test_openapi_spec_matches_routes():
    app_spec = app.openapi()["paths"]
    assert {p for p in app_spec} == set(load_spec()["paths"]), "every served route must be in the spec"
    for path, methods in load_spec()["paths"].items():
        for method, operation in methods.items():
            assert re.fullmatch(r"[A-Za-z_-]+", operation["operationId"])
            served = app_spec[path][method]
            assert served["operationId"] == operation["operationId"]
            assert {p["name"] for p in served["parameters"]} == {p["name"] for p in operation["parameters"]}


def test_openapi_documents_error_envelope():
    for methods in load_spec()["paths"].values():
        for operation in methods.values():
            assert set(operation["responses"]) == {"200"}
            schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
            assert {"code", "message", "httpStatus", "retryable"} <= set(schema["properties"]["error"]["properties"])


def operation(op_id):
    return next(op for m in load_spec()["paths"].values() for op in m.values() if op["operationId"] == op_id)


def response_schema(op_id):
    return operation(op_id)["responses"]["200"]["content"]["application/json"]["schema"]["properties"]


@pytest.mark.parametrize("op_id,codes", [
    ("get_customer_reservations", {"CUSTOMER_NOT_FOUND", "RESERVATION_NOT_FOUND", "INVALID_REQUEST"}),
    ("get_flight_status", {"FLIGHT_NOT_FOUND", "INVALID_DATE", "INVALID_REQUEST", "SERVICE_UNAVAILABLE"}),
    ("search_alternative_flights", {"UNKNOWN_AIRPORT", "INVALID_ROUTE", "INVALID_CABIN", "INVALID_DATE",
                                    "DATE_IN_PAST", "INVALID_REQUEST"}),
])
def test_openapi_lists_each_operations_error_codes(op_id, codes):
    error = response_schema(op_id)["error"]["properties"]
    assert set(error["code"]["enum"]) == codes
    assert all(code in operation(op_id)["description"] for code in codes)


def test_openapi_describes_agent_reasoning_fields():
    for path, key in keys(load_spec()):
        if ".properties." in f"{path}." or path.endswith(".properties"):
            assert not any(part in key.lower() for part in ("eligib", "recommend", "rank", "score")), path
    search_op = operation("search_alternative_flights")
    assert "chronological" in search_op["description"] and "NOT ranked" in search_op["description"]
    params = {p["name"]: p for p in search_op["parameters"]}
    assert {n for n, p in params.items() if p["required"]} == {"origin", "destination", "travelDate"}
    for name in ("passengerCount", "preferredCabin", "preferNonstop"):
        assert "does not filter or reorder" in params[name]["description"]
    assert params["preferredCabin"]["schema"]["enum"] == ["First", "Economy Plus", "Main Cabin"]
    option = response_schema("search_alternative_flights")["options"]["items"]["properties"]
    assert "NOT a reservation" in option["optionId"]["description"]
    assert "EVERY leg" in option["cabinAvailability"]["description"]
    assert "spread across" in option["totalSeatsAvailable"]["description"]
    assert option["type"]["enum"] == ["Nonstop", "Connection"]
    for field in ("departureLocal", "arrivalLocal", "totalTravelMinutes", "connectionAirport", "layoverMinutes"):
        assert option[field]["description"]
    assert option["segments"]["items"]["properties"]["status"]["enum"] == ["On Time", "Delayed"]
    status = response_schema("get_flight_status")
    assert status["status"]["enum"] == ["On Time", "Delayed", "Cancelled", "Landed"]
    assert status["delayMinutes"]["description"]
    assert set(status["disruption"]["properties"]["responsibility"]["enum"]) == {"Carrier", "Weather", "Air traffic control"}
    reservation = response_schema("get_customer_reservations")["reservations"]["items"]["properties"]
    assert reservation["cabin"]["enum"] == ["First", "Economy Plus", "Main Cabin"]
    segment = reservation["segments"]["items"]["properties"]
    assert set(segment["segmentStatus"]["enum"]) == {"Confirmed", "Flown", "Cancelled", "Reaccommodated"}


def test_openapi_served_with_host(client):
    spec = client.get("/openapi.json").json()
    assert spec["servers"] == [{"url": "http://testserver"}]
    assert {op["operationId"] for m in spec["paths"].values() for op in m.values()} == AGENT_OPERATIONS


def test_swagger_ui_uses_curated_spec(client):
    page = client.get("/docs")
    assert page.status_code == 200 and "/openapi.json" in page.text
