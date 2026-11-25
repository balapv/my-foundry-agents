"""Offline tests for the Demo 1B voice agent (no Azure calls).

Run from contoso-air-customer-care:  python -m pytest voice/tests
"""

import copy
import json
import re
import sys
from pathlib import Path

import pytest

VOICE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = VOICE_DIR.parent
sys.path.insert(0, str(VOICE_DIR / "agent"))

import run_session as rs  # noqa: E402
import live_mic  # noqa: E402
import voice_common as vc  # noqa: E402
from evaluation.run_evaluation import GUARDS  # noqa: E402

KNOWN_TOOLS = {"get_customer_reservations", "get_flight_status", "search_alternative_flights",
               "contoso_air_policies"}


@pytest.fixture(scope="module")
def config():
    return json.loads((VOICE_DIR / "agent" / "config.example.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def shared_spec():
    return json.loads((REPO_ROOT / "tools" / "openapi.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def scenarios():
    return rs.load_scenarios()


def _patterns(scenario, key):
    blocks = [t.get("expect", {}) for t in scenario["turns"]] + [scenario.get("sessionExpect", {})]
    return [rule for block in blocks for rule in block.get(key, [])]


def _find_rule(scenarios, why_prefix):
    for scenario in scenarios:
        for key in ("replyMustMatch", "replyMustNotMatch"):
            for rule in _patterns(scenario, key):
                if rule.get("why", "").startswith(why_prefix):
                    return rule["pattern"]
    raise AssertionError(f"no rule whose why starts with {why_prefix!r}")


# --------------------------------------------------------------------------- definition


def test_definition_uses_one_toolbox_and_declares_identity_input(config):
    definition = vc.build_voice_definition(config, "gpt-realtime-2.1", "managed", "tb", "7")
    assert len(definition.tools) == 1
    assert definition.tools[0].toolbox_name == "tb"
    assert definition.tools[0].toolbox_version == "7"
    assert set(definition.structured_inputs) == {"customer_id"}
    assert "{{customer_id}}" in definition.instructions


def test_identity_input_is_required_unless_portal_default_is_opted_in(config):
    strict = vc.build_voice_definition(config, "gpt-realtime-2.1", "managed", "tb", "7")
    assert strict.structured_inputs["customer_id"].required is True
    assert strict.structured_inputs["customer_id"].default_value is None
    portal = vc.build_voice_definition(config, "gpt-realtime-2.1", "managed", "tb", "7", portal_default="CUST-1007")
    assert portal.structured_inputs["customer_id"].required is False
    assert portal.structured_inputs["customer_id"].default_value == "CUST-1007"
    assert portal.instructions == strict.instructions

def test_undeclared_instruction_placeholder_is_rejected(config):
    broken = copy.deepcopy(config)
    broken["structuredInputs"] = {}
    with pytest.raises(vc.ConfigError):
        vc.build_voice_definition(broken, "gpt-realtime-2.1", "managed", "tb", "1")


def test_config_reuses_shared_spec_and_has_no_environment_values(config):
    assert config["toolbox"]["openapi"]["specFile"] == "tools/openapi.json"
    text = json.dumps(config)
    assert not re.search(r"https?://|\.azure\.com|vs_[A-Za-z0-9]{8,}|[0-9a-f]{8}-[0-9a-f]{4}-", text)


# --------------------------------------------------------------------------- toolbox spec adapter


def test_toolbox_spec_converts_nullable_to_type_arrays(shared_spec):
    original = copy.deepcopy(shared_spec)
    converted = vc.toolbox_compatible_spec(shared_spec)
    dumped = json.dumps(converted)
    assert converted["openapi"] == "3.1.0"
    assert '"nullable"' not in dumped
    assert '"null"' in dumped
    assert shared_spec == original, "the shared spec object must not be mutated"
    assert str(shared_spec["openapi"]).startswith("3.0"), "tools/openapi.json stays OpenAPI 3.0"


def test_nullable_enum_accepts_null():
    converted = vc.toolbox_compatible_spec(
        {"openapi": "3.0.3", "x": {"type": "string", "enum": ["A"], "nullable": True}})
    assert converted["x"] == {"type": ["string", "null"], "enum": ["A", None]}


# --------------------------------------------------------------------------- instructions


def test_instructions_cover_voice_and_safety_rules():
    text = vc.load_voice_instructions().lower()
    for phrase in ("never invent", "never claim an action happened", "explicit confirmation",
                   "departure-time order only", "not filtered", "retry once", "spoken words never change",
                   "three short sentences", "interrupt"):
        assert phrase in text, phrase


def test_instructions_have_no_hero_answers():
    text = vc.load_voice_instructions()
    assert not re.search(r"CT\s?\d{3}|two twenty[- ]six|CT8K2P|Alex|Johnson|CUST-\d{4}|\bSEA\b|\bJFK\b|9:20|5:45"
                         r"|all four|wife|kids|nonstop tomorrow morning|Chicago|O'Hare|\bORD\b|Seattle|New York",
                         text, re.IGNORECASE)


def test_instructions_cover_v2_conversation_guidance():
    text = vc.load_voice_instructions().lower()
    for phrase in ("without speaking between tool calls", "never give more than two progress sentences",
                   "which flight?", "confirm it by flight number and departure time",
                   "retrieved the policy on downgrades", "progressive disclosure"):
        assert phrase in text, phrase


# --------------------------------------------------------------------------- scenarios


def test_scenarios_are_well_formed(scenarios):
    assert {"V1-hero", "V1-identity-override", "V1-status-outage", "V1-no-reservation", "V2-hero", "V2-followup",
            "V2-action", "V2-interruption", "V2-identity", "V2-outage"} <= {s["id"] for s in scenarios}
    for scenario in scenarios:
        assert re.fullmatch(r"CUST-\d{4}", scenario["customerId"])
        assert scenario["turns"]
        for guard in scenario.get("guards", []):
            assert guard in GUARDS
        for turn in scenario["turns"]:
            clarify = turn.get("clarification")
            if clarify:
                assert clarify["expected"] in {"required", "forbidden", "allowed"}
                assert clarify["expected"] != "required" or clarify.get("reply")
                re.compile(clarify.get("pattern") or rs.CLARIFICATION_PATTERN)
            if turn.get("recommendationPattern"):
                re.compile(turn["recommendationPattern"])
        blocks = [t.get("expect", {}) for t in scenario["turns"]] + [scenario.get("sessionExpect", {})]
        for block in blocks:
            for key in ("toolsCalled", "toolsNotCalled"):
                assert set(block.get(key, [])) <= KNOWN_TOOLS
            for key in ("toolArguments", "forbiddenToolArguments"):
                assert {spec["tool"] for spec in block.get(key, [])} <= KNOWN_TOOLS
            for key in ("replyMustMatch", "replyMustNotMatch"):
                for rule in block.get(key, []):
                    re.compile(rule["pattern"])
                    assert rule.get("why")


@pytest.mark.parametrize("sentence, flagged", [
    ("Gold priority doesn't guarantee seats.", False),
    ("It's not a guaranteed seat, but you're processed first.", False),
    ("As a Gold member you're guaranteed a seat on that flight.", True),
])
def test_guarantee_rule_ignores_negated_sentences(scenarios, sentence, flagged):
    pattern = _find_rule(scenarios, "Gold priority is not a seat guarantee")
    assert bool(re.search(pattern, sentence, re.IGNORECASE)) is flagged


@pytest.mark.parametrize("sentence, flagged", [
    ("Since I don't want to guess, I can't say it's on schedule.", False),
    ("Good news, it's on schedule.", True),
    ("Your flight is delayed by about twenty minutes.", True),
])
def test_status_rule_ignores_negated_sentences(scenarios, sentence, flagged):
    pattern = _find_rule(scenarios, "Must not infer a status")
    assert bool(re.search(pattern, sentence, re.IGNORECASE)) is flagged


@pytest.mark.parametrize("sentence, flagged", [
    ("Please call Customer Care at 1-800-555-0142.", False),
    ("You can reach the Gold line at 1 800 555 0157.", False),
    ("Call us at 1-800-555-0199.", True),
])
def test_outage_contact_rule_allows_only_published_numbers(scenarios, sentence, flagged):
    pattern = _find_rule(scenarios, "Any phone number must be one of the policy's published contacts")
    assert bool(re.search(pattern, sentence, re.IGNORECASE)) is flagged


# --------------------------------------------------------------------------- V2 conversation checks and metrics


@pytest.mark.parametrize("text, asked", [
    ("Do you mean the nonstop at 2:15, or the connection through Denver?", True),
    ("Sure. Which flight are you asking about?", True),
    ("It leaves at 2:15. Would you like the details?", False),
    ("Just to confirm, I can't change bookings in this call.", False),
    ("", False),
])
def test_is_clarification_only_counts_questions_about_which_thing(text, asked):
    assert rs.is_clarification(text) is asked


def test_transcription_similarity_ignores_case_punctuation_and_spelling():
    assert rs.transcription_similarity("My flight was canceled.", "my flight was cancelled") == 1.0
    assert rs.transcription_similarity("Book that one.", "Look at the sun.") < 0.5
    assert rs.transcription_similarity("anything", None) is None


def _metrics_turn():
    turn = rs.TurnRecord(index=1, user_text="help", input_mode="audio", caller_audio_ms=3000,
                         user_transcription="help")
    turn.timings_ms["firstAgentAudio"] = 1000
    turn.tool_calls.append({"tool": "get_customer_reservations", "arguments": {}, "ok": True,
                            "startedMs": 1500, "completedMs": 2000})
    turn.audio_items = [{"itemId": "a", "firstAudioMs": 1000, "audioMs": 2000},
                        {"itemId": "b", "firstAudioMs": 2500, "audioMs": 1000},
                        {"itemId": "c", "firstAudioMs": 9000, "audioMs": 6000}]
    turn.agent_segments = [{"itemId": "a", "atMs": 1000, "text": "Let me check your trip."},
                           {"itemId": "b", "atMs": 2500, "text": "I found your booking."},
                           {"itemId": "c", "atMs": 9000, "text": "There's a nonstop at 2:15 that fits everyone."}]
    return turn


def test_turn_metrics_model_sequential_playback():
    turn = _metrics_turn()
    metrics = rs.compute_turn_metrics(turn, r"2:15")
    assert metrics["firstAudioMs"] == 1000
    # Item b arrives at 2500 but can't be heard until item a finishes playing at 3000.
    assert (turn.agent_segments[1]["heardStartMs"], turn.agent_segments[1]["heardEndMs"]) == (3000, 4000)
    assert metrics["firstMeaningfulMs"] == 2500 and metrics["firstMeaningfulHeardMs"] == 3000
    assert metrics["progressUtterances"] == 2 and metrics["segmentsAfterAnswer"] == 0
    assert metrics["recommendationMs"] == 9000 and metrics["recommendationHeardMs"] == 9000
    assert metrics["agentAudioMs"] == 9000 and metrics["agentSpeechEndHeardMs"] == 15000
    assert metrics["transcriptionSimilarity"] == 1.0 and metrics["toolFailures"] == 0
    assert rs.progress_checks(metrics, {"maxProgressUtterances": 1})[0]["passed"] is False
    assert rs.progress_checks(metrics, {"maxProgressUtterances": 2})[0]["passed"] is True
    assert rs.progress_checks(metrics, {}) == []
    # A restated answer after the recommendation is counted and checked.
    metrics = rs.compute_turn_metrics(turn, r"I found")
    assert metrics["segmentsAfterAnswer"] == 1
    assert rs.progress_checks(metrics, {"maxSegmentsAfterAnswer": 0})[0]["passed"] is False


@pytest.mark.parametrize("sentence, flagged", [
    ("Would you like the flight number, arrival time and the main tradeoff?", False),
    ("It leaves at 2:15 and arrives at 10:40.", True),
    ("You'd land around five forty-five.", True),
])
def test_first_answer_arrival_rule_flags_only_actual_arrival_times(scenarios, sentence, flagged):
    pattern = _find_rule(scenarios, "Progressive disclosure: the arrival time")
    assert bool(re.search(pattern, sentence, re.IGNORECASE)) is flagged


def test_exchange_checks_combine_clarification_sub_turn():
    asked = rs.TurnRecord(index=4, user_text="What time does it leave again?", input_mode="text")
    asked.agent_segments.append({"text": "Do you mean the nonstop or the connection?"})
    answer = rs.TurnRecord(index=4, label="4b", user_text="The nonstop.", input_mode="text")
    answer.agent_segments.append({"text": "The nonstop leaves at 2:15."})
    answer.tool_calls.append({"tool": "get_flight_status", "arguments": {}, "ok": True})
    spec = {"clarification": {"expected": "required", "reply": "The nonstop."},
            "expect": {"toolsNotCalled": ["search_alternative_flights"], "toolsCalled": ["get_flight_status"],
                       "replyMustMatch": [{"pattern": "2:15"}]}}
    checks = rs.check_exchange(asked, answer, spec, ["no_completed_action_claim"], True)
    assert all(c["passed"] for c in checks), checks
    assert answer.name == "4b" and asked.name == "4"
    forbidden = rs.check_exchange(asked, answer, {**spec, "clarification": {"expected": "forbidden"}}, [], True)
    assert not all(c["passed"] for c in forbidden)


def test_exchange_guards_cover_the_clarification_turn():
    asked = rs.TurnRecord(index=6, user_text="Book that one.", input_mode="text")
    asked.agent_segments.append({"text": "Done, I've rebooked you. Which flight did you want, by the way?"})
    answer = rs.TurnRecord(index=6, label="6b", user_text="The nonstop.", input_mode="text")
    answer.agent_segments.append({"text": "I can't change bookings, but Customer Care can."})
    checks = rs.check_exchange(asked, answer, {"expect": {}}, ["no_completed_action_claim"], True)
    assert checks[0]["check"] == "guard no_completed_action_claim" and checks[0]["passed"] is False


def test_summarize_results_reports_every_run_including_failures(tmp_path):
    def write(name, version, passed, first_audio):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "summary.json").write_text(json.dumps({
            "scenario": "V2-hero", "agentVersion": version, "passed": passed, "checksPassed": 9 if passed else 7,
            "checksTotal": 9, "failedChecks": [] if passed else ["says /9:20/"],
            "metrics": {"turn1": {"firstAudioMs": first_audio, "progressUtterances": 1}}}), encoding="utf-8")

    write("20261126-010000-V2-hero-r1", "7", True, 1500)
    write("20261126-010500-V2-hero-r2", "7", False, 2100)
    write("20261126-011000-V2-hero-r1", "8", True, 1300)
    report = rs.summarize_results(version="7", results_dir=tmp_path)
    assert "## V2-hero: 1/2 passed" in report
    assert "says /9:20/" in report
    assert "min 1500 / median 1800 / max 2100 (n=2)" in report
    assert "011000" not in report
    assert "## V2-hero: 1/1 passed" in rs.summarize_results(since="20261126-0110", results_dir=tmp_path)


# --------------------------------------------------------------------------- isolation


def test_live_mic_barge_in_truncates_at_the_audio_actually_heard():
    buf = live_mic.PlaybackBuffer()
    second = 1000 * rs.BYTES_PER_MS
    buf.add("item-a", b"\x01" * second)
    buf.add("item-a", b"\x01" * second)
    played = buf.read(600 * rs.BYTES_PER_MS)
    assert played == b"\x01" * (600 * rs.BYTES_PER_MS)
    cut = buf.clear()
    assert cut == {"itemId": "item-a", "heardMs": 600, "discardedMs": 1400}
    # After the cut, the speaker gets silence and nothing remains to truncate.
    assert buf.read(10) == b"\x00" * 10 and buf.pending_ms == 0 and buf.clear() is None


def test_live_mic_playback_moves_across_items_in_order():
    buf = live_mic.PlaybackBuffer()
    buf.add("a", b"\x01" * 4)
    buf.add("b", b"\x02" * 4)
    assert buf.read(6) == b"\x01" * 4 + b"\x02" * 2
    assert buf.played_bytes == {"a": 4, "b": 2} and buf.current_item == "b"


def test_voice_state_and_results_stay_in_voice_folder_and_are_ignored():
    assert vc.VOICE_STATE_FILE.parent == VOICE_DIR
    assert rs.RESULTS_DIR.parent == VOICE_DIR
    ignored = {line.strip() for line in (VOICE_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert {".voice-state.json", "agent/config.json", "results/", "openapi.toolbox.json"} <= ignored


# --------------------------------------------------------------------------- evaluation


def test_short_tool_name():
    assert rs.short_tool_name("contoso_air_operations___get_flight_status") == "get_flight_status"
    assert rs.short_tool_name("contoso_air_policies") == "contoso_air_policies"


def test_evaluate_expectations_normalizes_curly_apostrophes_and_checks_arguments():
    calls = [{"tool": "get_customer_reservations", "arguments": {"customerId": "cust-1007"}}]
    checks = rs.evaluate_expectations(
        calls, "I can\u2019t find that reservation.", {},
        {"toolsCalled": ["get_customer_reservations"], "toolsNotCalled": ["get_flight_status"],
         "toolArguments": [{"tool": "get_customer_reservations", "arguments": {"customerId": "CUST-1007"}}],
         "forbiddenToolArguments": [{"tool": "get_customer_reservations",
                                     "arguments": {"customerId": "CUST-1002"}}],
         "replyMustMatch": [{"pattern": "can't find"}]},
        guards=["no_completed_action_claim"])
    assert all(c["passed"] for c in checks), checks


def test_completed_action_guard_flags_booking_claim():
    checks = rs.evaluate_expectations([], "Done, I've rebooked all four of you on that flight.", {}, {},
                                      guards=["no_completed_action_claim"])
    assert checks[0]["passed"] is False


def test_evaluate_session_uses_every_turn():
    first = rs.TurnRecord(index=1, user_text="a", input_mode="text")
    first.tool_calls.append({"tool": "get_flight_status", "arguments": {}})
    second = rs.TurnRecord(index=2, user_text="b", input_mode="text")
    second.agent_segments.append({"text": "It's nonstop."})
    checks = rs.evaluate_session([first, second], {"toolsCalled": ["get_flight_status"],
                                                   "replyMustMatch": [{"pattern": "nonstop"}]})
    assert [c["passed"] for c in checks] == [True, True]
    assert all(c["check"].startswith("session: ") for c in checks)


def test_voice_state_resolution_prefers_override_then_env(monkeypatch):
    settings = {"agent_name": "contoso-air-customer-care-voice", "agent_version": "9"}
    assert vc.resolve_voice_agent_version(settings, "4") == ("4", "command line")
    assert vc.resolve_voice_agent_version(settings) == ("9", "FOUNDRY_VOICE_AGENT_VERSION")
    monkeypatch.setattr(vc, "read_voice_state", lambda: {})
    assert vc.resolve_voice_agent_version({"agent_name": "x", "agent_version": ""}) == (None, "latest")

def test_export_openapi_writes_toolbox_spec_without_azure(tmp_path, monkeypatch, shared_spec):
    import create_agent

    out = tmp_path / "openapi.toolbox.json"
    monkeypatch.setenv("TOOLS_API_BASE_URL", "https://tools.example.test")
    monkeypatch.setattr(sys, "argv", ["create_agent.py", "--export-openapi", str(out)])
    assert create_agent.main() == 0
    exported = json.loads(out.read_text(encoding="utf-8"))
    assert exported["openapi"] == "3.1.0"
    assert exported["servers"] == [{"url": "https://tools.example.test"}]
    assert "nullable" not in out.read_text(encoding="utf-8")
    assert {op["get"]["operationId"] for op in exported["paths"].values()} == {
        op["get"]["operationId"] for op in shared_spec["paths"].values()}


# --------------------------------------------------------------------------- readiness validator (Phase V3)

sys.path.insert(0, str(VOICE_DIR / "scripts"))
import validate_voice_demo as vvd  # noqa: E402


def _validated_definition():
    return {"kind": "voice", "model": "gpt-realtime-2.1",
            "audio": {"input": {"turn_detection": {"type": "azure_semantic_vad", "interrupt_response": True}},
                      "output": {"voice": "en-US-AvaNeural"}}}


def test_validator_accepts_committed_voice_configuration(config):
    settings = {"model": config["model"]["model"]}
    assert vvd.config_mismatches(config, settings) == []


def test_validator_flags_configuration_drift(config):
    changed = copy.deepcopy(config)
    changed["voice"]["name"] = "en-US-JennyNeural"
    changed["turnDetection"]["interruptResponse"] = False
    problems = vvd.config_mismatches(changed, {"model": "gpt-realtime-mini"})
    assert len(problems) == 3
    assert any("barge in" in p for p in problems)


def test_validator_flags_deployed_definition_drift():
    assert vvd.definition_drift(_validated_definition()) == []
    drifted = _validated_definition()
    drifted["audio"]["input"]["turn_detection"]["interrupt_response"] = False
    drifted["audio"]["output"]["voice"] = "alloy"
    assert len(vvd.definition_drift(drifted)) == 2


def test_validator_parses_harness_verdict():
    passed, detail = vvd.parse_live_verdict(
        "  => PASS: 24/24 checks, 0 errors, 106.7 s. Results: voice/results/x/\n")
    assert passed and detail == "PASS 24/24 checks, 0 errors, 106.7 s"
    assert vvd.parse_live_verdict("  => FAIL: 22/24 checks, 0 errors, 99 s.")[0] is False
    assert vvd.parse_live_verdict("  => ERROR: TimeoutError: no response")[0] is False
    assert vvd.parse_live_verdict("nothing here") == (False, "no result line from the voice harness")


def test_voice_and_fallback_demo_files_are_present():
    assert vvd.missing_files(vvd.VOICE_DEMO_FILES) == []
    assert vvd.missing_files(vvd.FALLBACK_FILES) == []
