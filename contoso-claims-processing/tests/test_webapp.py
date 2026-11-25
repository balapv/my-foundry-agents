"""Phase 3: Contoso Claims Review web application (backend, browser payloads and architecture boundaries).

The Foundry project client is replaced by a scripted fake, so these tests are offline and fast. The
fake records exactly what the application would send to the agent, which is what these tests check:
evidence verified and attached once, follow-ups in the same conversation, errors mapped to friendly
messages, nothing internal reaching the browser, and no claims reasoning in the application.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from conftest import HERO_EVIDENCE_DIR, ROOT, forbidden_keys_in
from webapp.backend import errors
from webapp.backend.app import create_app, static_files
from webapp.backend.config import Settings, common, load_settings
from webapp.backend.foundry import FoundryRuntime

WEBAPP = ROOT / "webapp"
HERO = "CLM-10482"
HERO_PROMPT = "Review this claim and tell me what I should do next."
FAKE_ENDPOINT = "https://contoso-demo.services.ai.azure.example/api/projects/claims-demo"
FAKE_GUID = "0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0"
CONVERSATION_ID = "conv_fake0123456789"


# ---------------------------------------------------------------------------
# Scripted Foundry fake
# ---------------------------------------------------------------------------


def item(kind: str, **fields):
    return {"type": kind, **fields}


def completed_response(answer: str, number: int, with_tools: bool = True):
    output = []
    if with_tools:
        output += [
            item("openapi_call", call_id="c1", name="get_claim", arguments=json.dumps({"claimId": HERO}), status="completed"),
            item("openapi_call_output", call_id="c1", output=json.dumps({"response": json.dumps({"claim": {}})})),
            item("file_search_call", queries=["estimate review"], status="completed",
                 results=[{"filename": "repair-estimate-review.pdf", "score": 0.91}]),
        ]
    output.append(item("message", phase="final_answer", content=[{"type": "output_text", "text": answer}]))
    return SimpleNamespace(id=f"resp_fake{number:04d}", output=output, output_text=answer,
                           usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})


def events_for(response, with_tools: bool = True):
    events = [SimpleNamespace(type="response.created")]
    if with_tools:
        events += [SimpleNamespace(type="response.output_item.added", item={"type": "openapi_call"}),
                   SimpleNamespace(type="response.output_item.added", item={"type": "file_search_call"})]
    events += [SimpleNamespace(type="response.output_item.added", item={"type": "message", "phase": "final_answer"}),
               SimpleNamespace(type="response.completed", response=response)]
    return events


class FakeStream:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def __iter__(self):
        return iter(self.events)

    def close(self):
        self.closed = True


class FakeOpenAI:
    """Records conversations and response requests; replays scripted turn outcomes."""

    def __init__(self, script):
        self.script = list(script)
        self.conversations_created = []
        self.requests = []
        self.streams = []
        self.conversations = SimpleNamespace(create=self._create_conversation)
        self.responses = SimpleNamespace(create=self._create_response)

    def _create_conversation(self, **kwargs):
        self.conversations_created.append(kwargs)
        return SimpleNamespace(id=CONVERSATION_ID if len(self.conversations_created) == 1
                               else f"{CONVERSATION_ID}_{len(self.conversations_created)}")

    def _create_response(self, **kwargs):
        self.requests.append(kwargs)
        step = self.script.pop(0) if self.script else "Answer."
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, list):
            stream = FakeStream(step)
        else:
            stream = FakeStream(events_for(completed_response(step, len(self.requests))))
        self.streams.append(stream)
        return stream


class FakeProject:
    def __init__(self, openai, latest_version="7"):
        self.openai = openai
        self.agents = SimpleNamespace(get=lambda agent_name: SimpleNamespace(
            versions={"latest": SimpleNamespace(version=latest_version)}))

    def get_openai_client(self):
        return self.openai


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(project_endpoint=FAKE_ENDPOINT, agent_name="contoso-claims-review-agent", agent_version="3",
                  claims_api_base_url=None, default_claim_id=HERO, turn_timeout_seconds=60.0,
                  image_detail="high", log_dir=tmp_path / "logs")
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(autouse=True)
def _close_log_handlers():
    yield
    logger = logging.getLogger(errors.LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger._claims_review_configured = None  # type: ignore[attr-defined]


class Harness:
    def __init__(self, tmp_path: Path, script=(), **settings):
        self.settings = make_settings(tmp_path, **settings)
        self.openai = FakeOpenAI(script)
        self.project = FakeProject(self.openai)
        self.runtime = FoundryRuntime(self.settings, project_factory=lambda s: self.project)
        self.client = TestClient(create_app(self.settings, runtime=self.runtime, run_in_thread=False))

    def start(self, claim_id: str = HERO) -> str:
        response = self.client.post("/api/reviews", json={"claimId": claim_id})
        assert response.status_code == 201, response.text
        return response.json()["sessionId"]

    def say(self, session_id: str, text: str):
        return self.client.post(f"/api/reviews/{session_id}/messages", json={"text": text})

    def log_records(self) -> list[dict]:
        for handler in logging.getLogger(errors.LOGGER_NAME).handlers:
            handler.flush()
        path = self.settings.log_dir / "claims-review.log"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def log_text(self) -> str:
        self.log_records()
        path = self.settings.log_dir / "claims-review.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""


@pytest.fixture
def harness(tmp_path):
    return lambda script=(), **settings: Harness(tmp_path, script, **settings)


@pytest.fixture
def evidence_copy(tmp_path, monkeypatch):
    """A private copy of the hero evidence package that a test may corrupt."""
    root = tmp_path / "evidence"
    shutil.copytree(HERO_EVIDENCE_DIR, root / HERO)
    monkeypatch.setattr(common, "EVIDENCE_DIR", root)
    return root / HERO


def parts_of(request) -> list[dict]:
    payload = request["input"]
    return payload[0]["content"] if isinstance(payload, list) else []


# ---------------------------------------------------------------------------
# Configuration and agent version resolution
# ---------------------------------------------------------------------------


def test_settings_come_from_the_environment(tmp_path):
    settings = load_settings({"FOUNDRY_PROJECT_ENDPOINT": f" {FAKE_ENDPOINT} ", "FOUNDRY_AGENT_NAME": "custom-agent",
                              "FOUNDRY_AGENT_VERSION": "4", "TOOLS_API_BASE_URL": "https://tools.example",
                              "CLAIMS_REVIEW_TURN_TIMEOUT_SECONDS": "2", "CLAIMS_REVIEW_LOG_DIR": str(tmp_path)})
    assert (settings.project_endpoint, settings.agent_name, settings.agent_version) == (FAKE_ENDPOINT, "custom-agent", "4")
    assert settings.claims_api_base_url == "https://tools.example"
    assert settings.turn_timeout_seconds == 10.0  # floor
    assert settings.image_detail == common.load_config()["imageDetail"] == "high"
    defaults = load_settings({})
    assert defaults.agent_name == "contoso-claims-review-agent"
    assert defaults.project_endpoint == "" and defaults.agent_version is None
    assert defaults.default_claim_id == HERO and defaults.turn_timeout_seconds == 180.0


def test_agent_version_resolution_order(tmp_path, monkeypatch):
    project = FakeProject(FakeOpenAI([]), latest_version="9")
    pinned = FoundryRuntime(make_settings(tmp_path, agent_version="3"), project_factory=lambda s: project)
    assert pinned.agent() == ("contoso-claims-review-agent", "3")

    monkeypatch.setattr(common, "load_state", lambda: {"agents": {"contoso-claims-review-agent": {"version": "5"}}})
    from_state = FoundryRuntime(make_settings(tmp_path, agent_version=None), project_factory=lambda s: project)
    assert from_state.configured_version() == "5"
    assert from_state.agent() == ("contoso-claims-review-agent", "5")

    def missing():
        raise OSError("no state file")

    monkeypatch.setattr(common, "load_state", missing)
    latest = FoundryRuntime(make_settings(tmp_path, agent_version=None), project_factory=lambda s: project)
    assert latest.configured_version() is None
    assert latest.agent() == ("contoso-claims-review-agent", "9")


# ---------------------------------------------------------------------------
# Claim workspace (display facts) and evidence catalog
# ---------------------------------------------------------------------------


def test_claim_workspace_shows_hero_display_facts(harness):
    workspace = harness().client.get(f"/api/claims/{HERO}").json()
    summary = workspace["summary"]
    assert summary == {**summary, "claimId": HERO, "policyholder": "Jordan Lee",
                       "vehicle": "2024 Contoso Trailstar Touring AWD", "lossDate": "2026-11-12",
                       "claimType": "Collision", "claimStatus": "In Review",
                       "repairFacility": "Harborline Auto Body & Paint", "estimateTotal": 7850.0,
                       "collisionDeductible": 1000.0, "policyId": "PAP-4471920"}
    assert workspace["recordsAvailable"] is True
    assert workspace["policy"]["policyStatus"] == "Active"


def test_evidence_catalog_comes_from_the_manifest(harness):
    manifest = json.loads((HERO_EVIDENCE_DIR / "evidence-manifest.json").read_text(encoding="utf-8"))
    evidence = harness().client.get(f"/api/claims/{HERO}").json()["evidence"]
    assert [e["documentId"] for e in evidence] == [d["documentId"] for d in manifest["documents"]]
    kinds = {e["documentId"]: e["kind"] for e in evidence}
    assert [k for k, v in kinds.items() if v == "pdf"] == ["DOC-10482-01", "DOC-10482-07", "DOC-10482-08"]
    assert [k for k, v in kinds.items() if v == "photo"] == [f"DOC-10482-0{n}" for n in range(2, 7)]
    assert {e["documentType"] for e in evidence if e["kind"] == "pdf"} == {"Claim form", "Police report", "Repair estimate"}
    for entry in evidence:
        assert set(entry) <= {"documentId", "documentType", "title", "source", "receivedAt", "kind", "url",
                              "pageCount", "widthPx", "heightPx"}


def test_frontend_workspace_fixture_matches_the_live_payload(harness):
    fixture = WEBAPP / "frontend" / "tests" / "fixtures" / "workspace-CLM-10482.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == harness().client.get(f"/api/claims/{HERO}").json()


def test_unknown_claim_is_not_found(harness):
    client = harness().client
    assert client.get("/api/claims/CLM-99999").status_code == 404
    assert client.get("/api/claims/not-a-claim").status_code == 404
    assert client.post("/api/reviews", json={"claimId": "CLM-99999"}).status_code == 404


def test_claim_without_evidence_package_shows_records_only(harness):
    workspace = harness().client.get("/api/claims/CLM-10208").json()
    assert workspace["evidence"] == []
    assert workspace["summary"]["claimId"] == "CLM-10208" and workspace["summary"]["policyholder"]


def test_evidence_files_are_served_after_verification(harness):
    client = harness().client
    for document_id, media_type in (("DOC-10482-08", "application/pdf"), ("DOC-10482-02", "image/jpeg")):
        response = client.get(f"/api/claims/{HERO}/evidence/{document_id}")
        assert response.status_code == 200
        assert response.headers["content-type"] == media_type
        assert response.headers["content-disposition"].startswith(f'inline; filename="{document_id}.')
    download = client.get(f"/api/claims/{HERO}/evidence/DOC-10482-01?download=true")
    assert download.headers["content-disposition"] == 'attachment; filename="DOC-10482-01.pdf"'
    guidance = client.get("/api/guidance/repair-estimate-review")
    assert guidance.status_code == 200 and guidance.content.startswith(b"%PDF")


def test_tampered_evidence_is_never_served(harness, evidence_copy):
    photo = evidence_copy / json.loads((evidence_copy / "evidence-manifest.json").read_text(encoding="utf-8"))["documents"][1]["fileName"]
    photo.write_bytes(photo.read_bytes() + b"tampered")
    h = harness()
    response = h.client.get(f"/api/claims/{HERO}/evidence/DOC-10482-02")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "evidence_validation" and re.fullmatch(r"CR-[0-9A-F]{6}", error["reference"])
    assert photo.name not in response.text
    record = next(r for r in h.log_records() if r["event"] == "evidence.integrity_failed")
    assert record["reference"] == error["reference"] and photo.name in record["detail"]


@pytest.mark.parametrize("path", [
    f"/api/claims/{HERO}/evidence/..%2Fevidence-manifest.json",
    f"/api/claims/{HERO}/evidence/evidence-manifest.json",
    f"/api/claims/{HERO}/evidence/DOC-10482-99",
    f"/api/claims/{HERO}/evidence/DOC-10471-01",
    "/api/claims/..%2F..%2Fdata/evidence/DOC-10482-01",
    "/api/claims/CLM-10482%2F..%2Fsource/evidence/DOC-10482-01",
    "/api/guidance/..%2Fsource%2Fclaims-handling-guidelines",
    "/api/guidance/instructions",
    "/ui/../backend/app.py",
    "/ui/..%2Fbackend%2Fapp.py",
    "/ui/tests/answer.test.mjs",
    "/ui/tests/fixtures/workspace-CLM-10482.json",
    "/ui/lib/../../backend/config.py",
])
def test_paths_outside_the_allowlists_are_not_found(harness, path):
    assert harness().client.get(path).status_code == 404


def test_manifest_file_names_cannot_escape_the_claim_folder(harness, evidence_copy):
    manifest_path = evidence_copy / "evidence-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["documents"][0]["fileName"] = "../../data/customers.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    h = harness(["Answer."])
    assert h.client.get(f"/api/claims/{HERO}/evidence/DOC-10482-01").status_code == 409
    turn = h.say(h.start(), HERO_PROMPT).json()
    assert turn["status"] == "failed" and turn["error"]["code"] == "evidence_validation"
    assert h.openai.requests == [] and h.openai.conversations_created == []


# ---------------------------------------------------------------------------
# Review sessions: evidence attached once, follow-ups in the same conversation
# ---------------------------------------------------------------------------


def test_first_turn_attaches_the_verified_evidence_package(harness):
    h = harness(["## Recommendation\nAgent answer one."])
    session_id = h.start()
    turn = h.say(session_id, HERO_PROMPT)
    assert turn.status_code == 202
    body = turn.json()
    assert body["status"] == "completed" and body["answer"] == "## Recommendation\nAgent answer one."
    assert body["evidenceAttached"] == {"documents": 3, "photos": 5}
    assert body["stagesSeen"] == ["verifying", "sending", "reviewing", "records", "guidance", "writing"]

    [request] = h.openai.requests
    assert request["conversation"] == CONVERSATION_ID
    assert request["extra_body"] == {"agent_reference": {"name": "contoso-claims-review-agent", "type": "agent_reference", "version": "3"}}
    assert request["stream"] is True and request["include"] == ["file_search_call.results"]
    parts = parts_of(request)
    manifest = json.loads((HERO_EVIDENCE_DIR / "evidence-manifest.json").read_text(encoding="utf-8"))
    expected_types = ["input_file" if d["mediaType"] == "application/pdf" else "input_image" for d in manifest["documents"]]
    assert [p["type"] for p in parts] == ["input_text"] + expected_types  # manifest order
    assert expected_types.count("input_file") == 3 and expected_types.count("input_image") == 5
    assert parts[0]["text"].startswith(f"Selected claim: {HERO}") and parts[0]["text"].endswith(f"Adjuster request: {HERO_PROMPT}")
    pdfs = [d["fileName"] for d in manifest["documents"] if d["mediaType"] == "application/pdf"]
    assert [p["filename"] for p in parts if p["type"] == "input_file"] == [Path(f).name for f in pdfs]
    assert all(p["file_data"].startswith("data:application/pdf;base64,") for p in parts if p["type"] == "input_file")
    assert all(p["image_url"].startswith("data:image/jpeg;base64,") and p["detail"] == "high"
               for p in parts if p["type"] == "input_image")
    sent = json.dumps(request["input"])
    for hidden in ("photos.json", "prompt.txt", "test_cases", "expected", "rubric", "IMPLEMENTATION-SPEC", "sha256"):
        assert hidden not in parts[0]["text"] and hidden not in sent.split("base64,")[0]
    assert h.openai.conversations_created == [{"metadata": {"claim": HERO, "demo": "contoso-claims-processing",
                                                            "channel": "claims-review-webapp"}}]
    assert h.openai.streams[0].closed


def test_follow_ups_reuse_the_conversation_without_resending_evidence(harness):
    h = harness(["First answer.", "Second answer.", "Third answer."])
    session_id = h.start()
    h.say(session_id, HERO_PROMPT)
    second = h.say(session_id, "Show me why you flagged the headlamp.").json()
    third = h.say(session_id, "Can you deny the claim based on this?").json()
    assert (second["answer"], third["answer"]) == ("Second answer.", "Third answer.")
    assert second["evidenceAttached"] is None and third["evidenceAttached"] is None
    assert len(h.openai.conversations_created) == 1
    assert [r["conversation"] for r in h.openai.requests] == [CONVERSATION_ID] * 3
    assert [r["input"] for r in h.openai.requests[1:]] == ["Show me why you flagged the headlamp.",
                                                          "Can you deny the claim based on this?"]
    assert "sending" in second["stagesSeen"] and "verifying" not in second["stagesSeen"]
    turn = h.client.get(f"/api/reviews/{session_id}/turns/t2").json()
    assert turn["answer"] == "Second answer." and turn["turnId"] == "t2"


def test_agent_answers_are_returned_exactly_as_written(harness):
    # Whatever the agent concludes, the application relays it unchanged; it never substitutes its own.
    answers = ["Approve the full estimate and pay the claim today.",
               "## Recommendation\nDeny the claim.\n\n## Why\nNo reason given.",
               "I could not retrieve the claim record."]
    h = harness(answers)
    session_id = h.start()
    returned = [h.say(session_id, f"question {n}").json()["answer"] for n in range(3)]
    assert returned == answers


def test_reset_starts_a_clean_conversation_and_changes_nothing_else(harness):
    manifest_before = (HERO_EVIDENCE_DIR / "evidence-manifest.json").read_bytes()
    h = harness(["First review.", "Clean review."])
    old = h.start()
    h.say(old, HERO_PROMPT)
    assert h.client.delete(f"/api/reviews/{old}").status_code == 204
    assert h.client.delete(f"/api/reviews/{old}").status_code == 204  # idempotent
    assert h.say(old, "Are you still there?").status_code == 404
    assert h.client.get(f"/api/reviews/{old}/turns/t1").status_code == 404
    new = h.start()
    assert new != old
    turn = h.say(new, HERO_PROMPT).json()
    assert turn["evidenceAttached"] == {"documents": 3, "photos": 5}
    assert [r["conversation"] for r in h.openai.requests] == [CONVERSATION_ID, f"{CONVERSATION_ID}_2"]
    assert (HERO_EVIDENCE_DIR / "evidence-manifest.json").read_bytes() == manifest_before
    assert h.client.get("/api/about").json()["agentVersion"] == "3"


def test_failed_first_turn_retries_with_evidence_in_a_new_conversation(harness):
    h = harness([RuntimeError("model overloaded"), "Recovered answer."])
    session_id = h.start()
    failed = h.say(session_id, HERO_PROMPT).json()
    assert failed["status"] == "failed" and failed["error"]["retry"] == "retry"
    retried = h.say(session_id, HERO_PROMPT).json()
    assert retried["status"] == "completed" and retried["evidenceAttached"] == {"documents": 3, "photos": 5}
    assert all(len(parts_of(r)) == 9 for r in h.openai.requests)
    assert len(h.openai.conversations_created) == 2


def test_message_validation_and_busy_sessions(harness):
    h = harness()
    session_id = h.start()
    assert h.say(session_id, "   ").status_code == 422
    assert h.say(session_id, "x" * 4001).status_code == 422
    assert h.say("no-such-session", "hello").status_code == 404
    session = h.client.app.state.reviews.get(session_id)
    session.running = "t9"
    assert h.say(session_id, "hello").status_code == 409


# ---------------------------------------------------------------------------
# Errors: friendly in the browser, specific (and scrubbed) in the server log
# ---------------------------------------------------------------------------


class ClientAuthenticationError(Exception):
    pass


class APITimeoutError(Exception):
    pass


class NotFoundError(Exception):
    status_code = 404


# Assembled at runtime so this file itself never contains token- or path-shaped strings.
FAKE_JWT = ".".join(["eyJ" + "hbGciOiJSUzI1NiJ9", "eyJ" + "zdWIiOiJkZW1vIn0", "c2lnbmF0dXJlc2ln"])
FAKE_WINDOWS_PATH = "C:" + "\\" + "Users" + "\\" + "someone" + "\\.azure\\token.json"
FAKE_UNIX_PATH = "/" + "home" + "/someone/x"
SECRET_DETAIL = (f"token {FAKE_JWT} Bearer abc.def-ghi "
                 f"at {FAKE_ENDPOINT} subscription {FAKE_GUID} file {FAKE_WINDOWS_PATH}")


@pytest.mark.parametrize(("failure", "code", "retry"), [
    (ClientAuthenticationError(SECRET_DETAIL), "configuration", "none"),
    (NotFoundError(f"agent version not found {SECRET_DETAIL}"), "configuration", "none"),
    (APITimeoutError(SECRET_DETAIL), "timeout", "new_review"),
    (RuntimeError(SECRET_DETAIL), "agent_error", "retry"),
    ([SimpleNamespace(type="response.created"),
      SimpleNamespace(type="response.failed", response={"error": {"code": "server_error", "message": SECRET_DETAIL}})],
     "agent_error", "retry"),
    ([SimpleNamespace(type="response.created")], "agent_error", "retry"),
    (events_for(completed_response("   ", 1, with_tools=False), with_tools=False), "empty_response", "retry"),
])
def test_turn_failures_map_to_friendly_errors(harness, failure, code, retry):
    h = harness([failure])
    turn = h.say(h.start(), HERO_PROMPT).json()
    assert turn["status"] == "failed" and turn["answer"] is None
    error = turn["error"]
    assert (error["code"], error["retry"]) == (code, retry)
    assert error["message"] == errors.MESSAGES[code]
    assert re.fullmatch(r"CR-[0-9A-F]{6}", error["reference"])
    payload = json.dumps(turn)
    for leaked in ("eyJ", "Bearer", "example", FAKE_GUID, "Users", "conv_", "resp_", "Error"):
        assert leaked not in payload
    log = h.log_text()
    record = next(r for r in h.log_records() if r["event"] == "review.turn_failed")
    assert record["reference"] == error["reference"] and record["errorCode"] == code
    for leaked in ("eyJhbGci", "abc.def-ghi", FAKE_ENDPOINT, FAKE_GUID, "Users", "someone"):
        assert leaked not in log


def test_missing_foundry_configuration_is_reported_without_calling_foundry(harness):
    h = harness(project_endpoint="")
    turn = h.say(h.start(), HERO_PROMPT).json()
    assert turn["error"]["code"] == "configuration" and turn["error"]["retry"] == "none"
    assert h.openai.requests == []
    # The claim workspace and evidence still work without cloud configuration.
    assert h.client.get(f"/api/claims/{HERO}").status_code == 200


def test_evidence_hash_mismatch_sends_nothing(harness, evidence_copy):
    estimate = evidence_copy / next(d["fileName"] for d in json.loads(
        (evidence_copy / "evidence-manifest.json").read_text(encoding="utf-8"))["documents"] if d["documentId"] == "DOC-10482-08")
    estimate.write_bytes(estimate.read_bytes().replace(b"%PDF", b"%PDX", 1))
    h = harness(["Should never be used."])
    turn = h.say(h.start(), HERO_PROMPT).json()
    assert turn["status"] == "failed" and turn["error"]["code"] == "evidence_validation"
    assert turn["stagesSeen"] == ["verifying"]
    assert h.openai.requests == [] and h.openai.conversations_created == []
    assert estimate.name not in json.dumps(turn)
    record = next(r for r in h.log_records() if r["event"] == "review.turn_failed")
    assert estimate.name in record["detail"] and "manifest hash" in record["detail"]


def test_timeouts_during_streaming_are_reported(harness, monkeypatch):
    from webapp.backend import foundry

    clock = iter([0.0, 0.0, 1000.0, 1000.0, 1000.0])
    monkeypatch.setattr(foundry.time, "monotonic", lambda: next(clock, 1000.0))
    h = harness()
    stream = FakeStream(events_for(completed_response("late", 1)))
    with pytest.raises(errors.ReviewError) as raised:
        h.openai.responses.create = lambda **kw: stream
        h.runtime.run_turn(CONVERSATION_ID, "q", lambda stage: None, timeout=60)
    assert raised.value.code == "timeout" and stream.closed


def test_successful_turns_log_what_a_presenter_needs_to_find_the_run(harness):
    h = harness(["Answer."])
    h.say(h.start(), HERO_PROMPT)
    record = next(r for r in h.log_records() if r["event"] == "review.turn_completed")
    assert record["conversationId"] == CONVERSATION_ID and record["responseId"] == "resp_fake0001"
    assert record["agent"] == "contoso-claims-review-agent" and record["agentVersion"] == "3"
    assert record["apiCalls"] == [{"operation": "get_claim", "errorCode": None}]
    assert record["fileSearchFiles"] == ["repair-estimate-review.pdf"]
    assert record["attachments"] == {"documents": 3, "photos": 5}
    log = h.log_text()
    assert "base64" not in log and HERO_PROMPT not in log and "Answer." not in log
    assert re.fullmatch(r"[0-9a-f]{10}", record["session"])


def test_scrub_removes_secrets_endpoints_and_paths():
    scrubbed = errors.scrub(SECRET_DETAIL + " api_key=abc123 data:image/jpeg;base64," + "A" * 40 + " " + FAKE_UNIX_PATH)
    for leaked in ("eyJhbGci", "abc.def-ghi", "abc123", FAKE_ENDPOINT, FAKE_GUID, "someone", "AAAAAAAAAAAAAAAA"):
        assert leaked not in scrubbed
    assert {"<token>", "<url>", "<guid>", "<path>", "<data>"} <= set(re.findall(r"<\w+>", scrubbed))


# ---------------------------------------------------------------------------
# Browser exposure
# ---------------------------------------------------------------------------


def test_browser_payloads_expose_no_internal_details(harness):
    h = harness(["Answer one.", "Answer two."])
    session_id = h.start()
    payloads = [h.client.get("/api/about").json(), h.client.get(f"/api/claims/{HERO}").json(),
                h.client.get("/api/claims/CLM-10208").json(), h.client.get("/api/claims/CLM-10471").json(),
                h.say(session_id, HERO_PROMPT).json(), h.say(session_id, "Follow-up").json(),
                h.client.get(f"/api/reviews/{session_id}/turns/t2").json()]
    text = json.dumps(payloads)
    for pattern in (r"sha256|\"hash\"", r"conv_|resp_|conversationId|responseId", r"[A-Za-z]:\\\\|/Users/|/home/",
                    r"services\.ai\.azure|https?://", r"get_claim|get_policy|get_vehicle|get_customer_claim_history",
                    r"openapi|file_search|vector", r"photos\.json|imagePrompt|generation|rubric|expected|fileName",
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"):
        assert not re.search(pattern, text.replace(HERO_PROMPT, ""), re.I), pattern
    assert forbidden_keys_in(payloads) == []
    # The only prompt in any payload is the adjuster's own message.
    assert [k for k in re.findall(r'"(\w*)":', text) if "prompt" in k.lower()] == ["prompt", "prompt", "prompt"]
    assert set(payloads[4]) == {"turnId", "prompt", "status", "stage", "stagesSeen", "elapsedSeconds", "answer",
                                "evidenceAttached", "error"}


def test_security_headers_and_pdf_viewer_exception(harness):
    client = harness().client
    page = client.get("/")
    assert page.status_code == 200 and "Contoso Claims Review" in page.text
    assert "default-src 'self'" in page.headers["content-security-policy"]
    for response in (page, client.get(f"/api/claims/{HERO}"), client.get(f"/api/claims/{HERO}/evidence/DOC-10482-02")):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "SAMEORIGIN"
        assert "content-security-policy" in response.headers
    assert client.get(f"/api/claims/{HERO}").headers["cache-control"] == "no-store"
    # A document CSP blanks the browser's built-in PDF viewer, so PDFs omit only that header.
    for pdf in (client.get(f"/api/claims/{HERO}/evidence/DOC-10482-07"), client.get("/api/guidance/claims-handling-guidelines")):
        assert pdf.headers["content-type"] == "application/pdf"
        assert "content-security-policy" not in pdf.headers
        assert pdf.headers["x-content-type-options"] == "nosniff" and pdf.headers["x-frame-options"] == "SAMEORIGIN"


def test_only_allowlisted_frontend_assets_are_served(harness):
    client = harness().client
    for asset in ("app.js", "styles.css", "icon.svg", "lib/markdown.js", "lib/sources.js", "lib/views.js", "lib/review.js"):
        assert client.get(f"/ui/{asset}").status_code == 200, asset
    served = set(static_files())
    assert {"index.html", "app.js", "lib/views.js"} <= served
    assert not any(name.startswith("tests/") for name in served)


# ---------------------------------------------------------------------------
# Architecture boundaries: the application presents facts and relays the agent; it does not reason
# ---------------------------------------------------------------------------


def application_sources() -> dict[str, str]:
    files = [p for p in WEBAPP.rglob("*") if p.is_file() and p.suffix in {".py", ".js", ".mjs", ".html", ".css"}
             and "tests" not in p.relative_to(WEBAPP).parts and ".logs" not in p.parts]
    assert {"backend/app.py", "backend/sessions.py", "frontend/app.js", "frontend/lib/views.js"} <= {
        p.relative_to(WEBAPP).as_posix() for p in files}
    return {p.relative_to(WEBAPP).as_posix(): p.read_text(encoding="utf-8") for p in files}


# Identifiers that would mean the application itself decides something about the claim.
DECISION_IDENTIFIERS = re.compile(
    r"manual_?review_?required|unsupported_?(headlamp|item|line)|fraud_?(score|risk)|risk_?score|"
    r"recommended_?decision|evidence_?mismatch|is_?suspicious|anomaly|auto_?(approve|deny)|"
    r"(approve|deny|authorize|reject)_?(claim|repair|estimate|payment)|select_?recommendation|"
    r"coverage_?(applies|decision)|deductible_?applies|needs_?manual",
    re.I)
# Claim-specific conclusions and evidence facts the agent must reach itself.
HERO_CONCLUSIONS = re.compile(
    r"headlamp|head-lamp|1,?240|front[- ]left|right[- ]rear|manual review before|not established|"
    r"does not establish|\bSIU\b|special investigation|fraud|suspicious", re.I)


def test_application_contains_no_claim_decision_logic():
    for name, text in application_sources().items():
        assert not DECISION_IDENTIFIERS.search(text), f"{name}: {DECISION_IDENTIFIERS.search(text).group(0)}"


def test_application_contains_no_hero_conclusions():
    for name, text in application_sources().items():
        assert not HERO_CONCLUSIONS.search(text), f"{name}: {HERO_CONCLUSIONS.search(text).group(0)}"


def test_application_never_inspects_answer_content():
    # The answer is only rendered (frontend) or relayed (backend). Section headings are used for card
    # styling alone; no code compares the answer against a conclusion.
    sources = application_sources()
    backend = "\n".join(t for n, t in sources.items() if n.startswith("backend/"))
    answer_lines = [line.strip() for line in re.findall(r"[^\n]*\banswer\b[^\n]*", backend)]
    assert "answer = common.final_text(response).strip()" in answer_lines and "turn.answer = answer" in answer_lines
    for line in answer_lines:
        assert not re.search(r"answer\s*(\.|\[)\s*(lower|find|index|count|startswith|endswith|split)|"
                             r"\bin\s+answer\b|re\.\w+\([^)]*answer", line), line
    frontend = "\n".join(t for n, t in sources.items() if n.startswith("frontend/"))
    assert not re.search(r"\b(answer|markdown|text)\s*\.\s*(includes|indexOf|search|match)\s*\(\s*[\"'`/]", frontend)
    # Heading names select a card's CSS class and nothing else.
    section_class = re.search(r"function sectionClass\(heading\) \{(.*?)\n\}", sources["frontend/lib/views.js"], re.S).group(1)
    assert "recommendation" in section_class
    assert re.search(r"return match \? ` section-\$\{[^}]*\}` : \"\";", section_class)
    assert sources["frontend/lib/views.js"].count("sectionClass(") == 2


def test_decision_identifier_guard_is_meaningful():
    # The guards must catch real decision logic while allowing ordinary display copy.
    assert DECISION_IDENTIFIERS.search("if (answer.manual_review_required) {")
    assert DECISION_IDENTIFIERS.search("const fraudScore = 0.2")
    assert DECISION_IDENTIFIERS.search("def approve_claim(claim):")
    assert HERO_CONCLUSIONS.search("needsReview = line.description.includes('headlamp')")
    assert not DECISION_IDENTIFIERS.search("Recommendations support your decision; you make the decision.")
    assert not HERO_CONCLUSIONS.search("Reviews this claim's records, documents, photographs and company guidance.")
