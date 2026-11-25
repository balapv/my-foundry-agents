"""Agent definition and shared Foundry helper tests (no Azure calls)."""

import json
import re

import pytest

from agent import foundry_common as fc


@pytest.fixture(scope="module")
def config():
    return fc.load_config()


def test_definition_has_file_search_and_one_operations_openapi_tool(config):
    definition = fc.build_agent_definition(config, "gpt-5.4-mini", "https://tools.example.test/", "vs_123").as_dict()
    assert definition.get("kind", "prompt") == "prompt"
    assert definition["model"] == "gpt-5.4-mini"
    assert "Contoso Air" in definition["instructions"]
    types = [t["type"] for t in definition["tools"]]
    assert types == ["file_search", "openapi"]
    assert definition["tools"][0]["vector_store_ids"] == ["vs_123"]
    tool = definition["tools"][1]["openapi"]
    assert tool["name"] == "contoso_air_operations"
    assert tool["spec"]["servers"] == [{"url": "https://tools.example.test"}]
    assert tool["auth"]["type"] == "anonymous"
    operation_ids = {op["operationId"] for path in tool["spec"]["paths"].values() for op in path.values()}
    assert operation_ids == {"get_customer_reservations", "get_flight_status", "search_alternative_flights"}


def test_config_matches_spec_and_repo(config):
    assert config["agentName"] == "contoso-air-customer-care"
    assert config["displayName"] == "Contoso Air Customer Care"
    assert len(config["knowledge"]["files"]) == 4
    assert all((fc.REPO_ROOT / f).exists() for f in config["knowledge"]["files"])
    assert [t["specFile"] for t in config["tools"]] == ["tools/openapi.json"]
    assert (fc.REPO_ROOT / "tools/openapi.json").exists()
    assert len(config["starterPrompts"]) == 4


def test_committed_spec_keeps_placeholder_server():
    assert not list(fc.REPO_ROOT.glob("tools/*/openapi.json")), "only tools/openapi.json should exist"
    spec = json.loads((fc.REPO_ROOT / "tools/openapi.json").read_text(encoding="utf-8"))
    assert spec["servers"][0]["url"] == fc.OPENAPI_SERVER_PLACEHOLDER


def test_instructions_cover_spec_behaviors():
    text = fc.load_instructions()
    for phrase in ("Never invent", "Policy before entitlements", "Never claim an action happened",
                   "Explicit confirmation first", "Separate facts from advice", "Authenticated session context",
                   "CUST-1007", "chronological order of departure only", "not a recommendation",
                   "cabinAvailability", "totalSeatsAvailable", "optionId", "retryable", "Special circumstances"):
        assert phrase.lower() in text.lower(), phrase


def test_instructions_have_no_hero_answer_rules():
    text = fc.load_instructions()
    assert not re.search(r"\bCT\d{3}\b|CT8K2P|Alex Johnson|Economy Plus", text)


def test_agent_version_resolution_order(monkeypatch):
    settings = fc.Settings(agent_name="contoso-air-customer-care")
    state = {"agentName": "contoso-air-customer-care", "latestAgentVersion": "9", "activeAgentVersion": "7"}
    monkeypatch.setattr(fc, "read_state", lambda: state)
    assert fc.resolve_agent_version(settings) == ("7", ".foundry-state.json")
    assert fc.resolve_agent_version(settings, "5") == ("5", "command line")
    settings.agent_version = "6"
    assert fc.resolve_agent_version(settings) == ("6", "FOUNDRY_AGENT_VERSION")
    settings.agent_version = ""
    state["agentName"] = "another-agent"
    assert fc.resolve_agent_version(settings) == (None, "latest")
    monkeypatch.setattr(fc, "read_state", lambda: {})
    assert fc.resolve_agent_version(fc.Settings(agent_name="contoso-air-customer-care")) == (None, "latest")


@pytest.mark.parametrize("name,ok", [("contoso-air-customer-care", True), ("Contoso Air", False),
                                     ("-bad", False), ("a" * 64, False), ("agent1", True)])
def test_validate_agent_name(name, ok):
    if ok:
        fc.validate_agent_name(name)
    else:
        with pytest.raises(fc.ConfigError):
            fc.validate_agent_name(name)


def test_validate_tools_url_flags_localhost():
    assert fc.validate_tools_url("https://contoso-air-tools.example.azurecontainerapps.io") == []
    assert len(fc.validate_tools_url("http://localhost:8000")) == 2


def test_parse_output_items_maps_tools_and_outputs():
    items = [
        {"type": "openapi_call", "call_id": "c1", "name": "contoso_air_operations_get_customer_reservations",
         "arguments": '{"customerId": "CUST-1007"}', "status": "completed"},
        {"type": "openapi_call_output", "call_id": "c1", "name": "contoso_air_operations", "output": '{"reservationCount": 1}'},
        {"type": "file_search_call", "id": "fs1", "queries": ["change fee cancellation"], "status": "completed"},
        {"type": "openapi_call", "call_id": "c2", "name": "contoso_air_operations_search_alternative_flights",
         "arguments": {"passengerCount": 4}},
        {"type": "message", "content": [{"type": "output_text", "text": "Hi"}]},
    ]
    calls = fc.parse_output_items(items)
    assert [c.category for c in calls] == ["reservation", "knowledge", "flight_search"]
    assert calls[0].arguments == {"customerId": "CUST-1007"}
    assert calls[0].output == {"reservationCount": 1}
    assert calls[2].arguments["passengerCount"] == 4


class _FakeConversations:
    def __init__(self, reject_developer):
        self.reject_developer = reject_developer
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("items") and self.reject_developer:
            error = Exception("developer role not supported")
            error.status_code = 400
            raise error
        return type("Conversation", (), {"id": "conv_1"})()


class _FakeClient:
    def __init__(self, reject_developer=False):
        self.conversations = _FakeConversations(reject_developer)


def test_session_context_attached_to_conversation():
    client = _FakeClient()
    handle = fc.create_conversation(client, "CUST-1012")
    assert handle.context_in_conversation
    assert "CUST-1012" in client.conversations.calls[0]["items"][0]["content"]
    kwargs = fc.response_kwargs(handle, "Hello", "contoso-air-customer-care", "3")
    assert kwargs["input"] == "Hello"
    assert kwargs["extra_body"]["agent_reference"] == {"name": "contoso-air-customer-care",
                                                       "type": "agent_reference", "version": "3"}


def test_session_context_falls_back_to_first_turn():
    handle = fc.create_conversation(_FakeClient(reject_developer=True), "CUST-1012")
    assert not handle.context_in_conversation
    first = fc.turn_input(handle, "Hello")
    assert first[0]["role"] == "developer" and "CUST-1012" in first[0]["content"]
    handle.turns = 1
    assert fc.turn_input(handle, "Again") == "Again"


def test_clean_customer_text_strips_citation_markers():
    assert fc.clean_customer_text("No change fee applies.\u30104:0\u2020flight-disruption-policy.pdf\u3011") == \
        "No change fee applies."
    assert fc.clean_customer_text("No fee. \u30104:0\u2020policy.pdf\u3011 Gold gets priority.") == \
        "No fee. Gold gets priority."
    assert fc.clean_customer_text("No fee. \ue200filecite\ue202turn0file6\ue202turn1file3\ue201 Gold gets priority.") == \
        "No fee. Gold gets priority."


def test_response_text_returns_final_answer_without_commentary():
    response = {"output": [
        {"type": "message", "phase": "commentary", "content": [{"type": "output_text", "text": "Let me check."}]},
        {"type": "openapi_call", "name": "contoso_air_operations_get_flight_status"},
        {"type": "message", "phase": "final_answer", "content": [{"type": "output_text", "text": "It is on time."}]},
    ]}
    assert fc.response_text(response) == "It is on time."
    response["output"][2].pop("phase")
    assert fc.response_text(response) == "Let me check.\n\nIt is on time."


@pytest.mark.parametrize("reply, flagged", [
    ("I can't complete changes here, and no seats are held.", False),
    ("Your seats are held on the 9:20 AM flight.", True),
    ("I've rebooked all four of you.", True),
])
def test_completed_action_guard_ignores_negations(reply, flagged):
    from evaluation import run_evaluation as ev

    hits = [p for p in ev.GUARDS["no_completed_action_claim"] if re.search(p, reply, re.IGNORECASE)]
    assert bool(hits) is flagged
