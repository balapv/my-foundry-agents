"""Web app backend: a channel/relay to the configured Foundry agent version, with no customer-service logic."""

import importlib.util
import json
import shutil
import subprocess
import sys
from types import SimpleNamespace

import httpx
import openai
import pytest
from azure.core.exceptions import ClientAuthenticationError
from fastapi.testclient import TestClient

from agent import foundry_common as fc
from main import app as tools_app


def _load_server():
    spec = importlib.util.spec_from_file_location("webapp_server", fc.REPO_ROOT / "webapp" / "backend" / "server.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


server = _load_server()
tools_client = TestClient(tools_app)
AGENT = "contoso-air-customer-care"


def ev(kind, **fields):
    return SimpleNamespace(type=kind, **fields)


def hero_stream():
    """Event sequence shaped like the live Foundry stream for the hero scenario."""
    final = SimpleNamespace(
        id="resp_1",
        output_text="I'm sorry your flight CT218 was cancelled.\u30104:0\u2020flight-disruption-policy.pdf\u3011 **CT226** has 4 seats.",
        output=[],
    )
    return [
        ev("response.created"),
        ev("response.output_item.added", item={"type": "message", "id": "msg_c", "phase": "commentary"}),
        ev("response.output_text.delta", item_id="msg_c", delta="Let me look up your reservation."),
        ev("response.output_item.added", item={"type": "openapi_call", "name": "contoso_air_operations_get_customer_reservations"}),
        ev("response.output_item.added", item={"type": "openapi_call_output", "name": "contoso_air_operations_get_customer_reservations"}),
        ev("response.output_item.added", item={"type": "openapi_call", "name": "contoso_air_operations_get_flight_status"}),
        ev("response.output_item.added", item={"type": "file_search_call", "queries": ["cancellation"]}),
        ev("response.output_item.added", item={"type": "openapi_call", "name": "contoso_air_operations_search_alternative_flights",
                                               "arguments": "{\"origin\": \"SEA\"}"}),
        ev("response.output_item.added", item={"type": "reasoning"}),
        ev("response.output_item.added", item={"type": "message", "id": "msg_f", "phase": "final_answer"}),
        ev("response.output_text.delta", item_id="msg_f", delta="I'm sorry your flight CT218 was cancelled.\u30104:0\u2020flight-"),
        ev("response.output_text.delta", item_id="msg_f", delta="disruption-policy.pdf\u3011 **CT226** has 4 seats."),
        ev("response.completed", response=final),
    ]


class FakeResponses:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.events, BaseException):
            raise self.events
        return iter(self.events)


class FakeOpenAI:
    def __init__(self, events):
        self.responses = FakeResponses(events)
        self.conversations = SimpleNamespace(create=lambda **kwargs: SimpleNamespace(id="conv_1"))


def tools_fetcher(_settings, customer_id):
    response = tools_client.get(f"/customers/{customer_id}/reservations")
    response.raise_for_status()
    return response.json()


def status_fetcher(_settings, flight_number, date):
    response = tools_client.get(f"/flight-status/{flight_number}", params={"date": date})
    response.raise_for_status()
    return response.json()


def make_client(events, fetcher=tools_fetcher, customer_id="CUST-1007", agent_version="7", **kwargs):
    fake = FakeOpenAI(events)
    settings = fc.Settings(project_endpoint="https://example.invalid", agent_name=AGENT,
                           tools_api_base_url="https://tools.example.invalid", demo_customer_id=customer_id,
                           agent_version=agent_version)
    app = server.create_app(settings=settings, openai_client_factory=lambda: fake, reservations_fetcher=fetcher,
                            status_fetcher=status_fetcher, **kwargs)
    return TestClient(app), fake


def parse_sse(body):
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def chat(client, message="My flight was cancelled."):
    session_id = client.post("/api/session").json()["sessionId"]
    response = client.post("/api/chat", json={"sessionId": session_id, "message": message})
    return response, parse_sse(response.text)


def test_session_returns_greeting_trip_card_and_suggestions():
    client, _ = make_client([])
    data = client.post("/api/session").json()
    assert data["sessionId"]
    assert data["firstName"] == "Alex" and data["loyaltyTier"] == "Gold"
    trip = data["trip"]
    assert trip["confirmationCode"] == "CT8K2P" and trip["cabin"] == "Economy Plus"
    assert len(trip["passengers"]) == 4
    segment = trip["segments"][0]
    assert segment["flightNumber"] == "CT218" and segment["date"] == "2026-05-15"  # tests pin DEMO_TODAY
    assert (segment["originCity"], segment["destinationCity"]) == ("Seattle", "New York")
    assert segment["flightStatus"] == "Cancelled"
    config = fc.load_config()
    assert data["heroPrompt"] == config["heroPrompt"]
    assert data["starterPrompts"] == config["starterPrompts"]


def test_session_without_trips_and_with_tools_api_down():
    client, _ = make_client([], customer_id="CUST-1019")
    data = client.post("/api/session").json()
    assert data["firstName"] and data["trip"] is None

    def broken(*_args):
        raise RuntimeError("tools API unavailable")

    client, _ = make_client([], fetcher=broken)
    data = client.post("/api/session").json()
    assert data["sessionId"] and data["trip"] is None


def test_chat_streams_progress_and_clean_reply_from_the_configured_agent_version():
    client, fake = make_client(hero_stream())
    response, events = chat(client)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    statuses = [data["message"] for kind, data in events if kind == "status"]
    assert statuses == ["Checking your trip…", "Checking flight status…", "Checking Contoso Air policies…",
                        "Finding alternative flights…", "Reviewing your options…"]
    streamed = "".join(data["text"] for kind, data in events if kind == "delta")
    assert streamed == "I'm sorry your flight CT218 was cancelled. **CT226** has 4 seats."
    kind, done = events[-1]
    assert kind == "done" and "\u3010" not in done["text"] and "CT226" in done["text"]

    # Commentary, tool names, arguments and payloads never reach the browser.
    for hidden in ("Let me look up", "contoso_air_operations", "openapi_call", "file_search", "origin", "SEA"):
        assert hidden not in response.text

    call = fake.responses.calls[0]
    assert call["stream"] is True and call["conversation"] == "conv_1"
    assert call["extra_body"] == {"agent_reference": {"name": AGENT, "type": "agent_reference", "version": "7"}}


def test_agent_version_comes_from_state_file_and_falls_back_to_latest(monkeypatch):
    monkeypatch.setattr(fc, "read_state", lambda: {"agentName": AGENT, "activeAgentVersion": 12})
    client, fake = make_client(hero_stream(), agent_version="")
    chat(client)
    assert fake.responses.calls[0]["extra_body"]["agent_reference"]["version"] == "12"
    assert client.get("/api/health").json()["agentVersion"] == "12"

    monkeypatch.setattr(fc, "read_state", lambda: {})
    client, fake = make_client(hero_stream(), agent_version="")
    chat(client)
    assert "version" not in fake.responses.calls[0]["extra_body"]["agent_reference"]


def test_customer_context_comes_from_the_server_session_only():
    client, fake = make_client(hero_stream())
    session_id = client.post("/api/session").json()["sessionId"]
    spoofed = client.post("/api/chat", json={"sessionId": session_id, "message": "Hi", "customerId": "CUST-1002"})
    assert spoofed.status_code == 422 and "CUST-1002" not in spoofed.text
    assert fake.responses.calls == []

    created = []
    fake.conversations.create = lambda **kwargs: created.append(kwargs) or SimpleNamespace(id="conv_1")
    client.post("/api/chat", json={"sessionId": session_id, "message": "Hi"})
    assert "CUST-1007" in created[0]["items"][0]["content"]
    assert created[0]["items"][0]["role"] == "developer"


def test_chat_reuses_conversation_across_turns():
    client, fake = make_client(hero_stream())
    session_id = client.post("/api/session").json()["sessionId"]
    for text in ("First question", "Follow-up question"):
        client.post("/api/chat", json={"sessionId": session_id, "message": text})
    assert [c["conversation"] for c in fake.responses.calls] == ["conv_1", "conv_1"]
    assert fake.responses.calls[1]["input"] == "Follow-up question"


REQUEST = httpx.Request("POST", "https://example.invalid/openai/v1/responses")


@pytest.mark.parametrize(
    "failure, category, message",
    [
        (RuntimeError("boom https://internal.example token=abc"), "unexpected", server.GENERIC_ERROR),
        (ClientAuthenticationError("DefaultAzureCredential failed"), "authentication", server.GENERIC_ERROR),
        (openai.AuthenticationError("401", response=httpx.Response(401, request=REQUEST), body=None),
         "authentication", server.GENERIC_ERROR),
        (openai.APIConnectionError(request=REQUEST), "foundry_unavailable", server.GENERIC_ERROR),
        (openai.InternalServerError("503", response=httpx.Response(503, request=REQUEST), body=None),
         "foundry_unavailable", server.GENERIC_ERROR),
        (openai.APITimeoutError(request=REQUEST), "timeout", server.CUSTOMER_ERRORS["timeout"]),
        (openai.RateLimitError("429", response=httpx.Response(429, request=REQUEST), body=None),
         "busy", server.CUSTOMER_ERRORS["busy"]),
    ],
)
def test_chat_errors_are_friendly_classified_and_logged(failure, category, message, caplog):
    client, _ = make_client(failure)
    _response, events = chat(client)
    assert len(events) == 1
    kind, data = events[0]
    assert kind == "error" and data["message"] == message
    assert set(data) == {"message", "reference"} and len(data["reference"]) == 8
    assert f"category={category}" in caplog.text and data["reference"] in caplog.text


def test_failed_agent_response_and_timeout_mid_stream():
    failed = [ev("response.created"), ev("response.failed", response=SimpleNamespace(error="server_error"))]
    client, _ = make_client(failed)
    _response, events = chat(client)
    assert events[-1] == ("error", {"message": server.GENERIC_ERROR, "reference": events[-1][1]["reference"]})

    def slow_stream():
        yield ev("response.created")
        import time
        time.sleep(0.05)
        yield ev("response.output_item.added", item={"type": "reasoning"})

    client, fake = make_client(slow_stream(), turn_timeout_seconds=0.01)
    _response, events = chat(client)
    assert events[-1][0] == "error" and events[-1][1]["message"] == server.CUSTOMER_ERRORS["timeout"]
    assert fake.responses.calls[0]["timeout"] == 0.01


def test_chat_rejects_unknown_session_and_empty_message():
    client, _ = make_client([])
    assert client.post("/api/chat", json={"sessionId": "nope", "message": "Hi"}).status_code == 404
    session_id = client.post("/api/session").json()["sessionId"]
    assert client.post("/api/chat", json={"sessionId": session_id, "message": ""}).status_code == 422
    assert client.delete(f"/api/session/{session_id}").json() == {"deleted": True}


def test_frontend_is_served():
    client, _ = make_client([])
    page = client.get("/")
    assert page.status_code == 200
    assert "Contoso Air" in page.text and "Travel Assistant" in page.text


def test_frontend_is_a_channel_only():
    """The browser code never names tools or customers and does no customer-service reasoning."""
    frontend = fc.REPO_ROOT / "webapp" / "frontend"
    source = "\n".join(p.read_text(encoding="utf-8") for p in frontend.glob("*.*"))
    for forbidden in ("contoso_air_operations", "search_alternative_flights", "get_flight_status",
                      "CUST-1007", "CT226", "customerId", "policy"):
        assert forbidden not in source


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is not installed")
def test_frontend_script_parses():
    result = subprocess.run(["node", "--check", str(fc.REPO_ROOT / "webapp" / "frontend" / "app.js")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "deltas, expected",
    [
        (["plain text"], "plain text"),
        (["a\u30101:0\u2020x.pdf\u3011b"], "ab"),
        (["a\u3010", "1:0\u2020x", ".pdf\u3011b"], "ab"),
        (["unterminated \u3010bracket"], "unterminated \u3010bracket"),
    ],
)
def test_citation_filter_handles_split_markers(deltas, expected):
    citation_filter = server.CitationFilter()
    assert "".join(citation_filter.feed(d) for d in deltas) + citation_filter.flush() == expected
