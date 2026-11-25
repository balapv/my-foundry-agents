"""Agent configuration tests (offline): hero-answer leakage, the two-tool definition, the evidence
allowlist and response/trace parsing. No Azure calls are made."""

from __future__ import annotations

import base64
import json
import re
import sys
from types import SimpleNamespace

import pytest

from conftest import DATA_DIR, EVIDENCE_DIR, FORBIDDEN_KEYS, HERO_EVIDENCE_DIR, ROOT, load_json

sys.path.insert(0, str(ROOT / "agent"))

import common  # noqa: E402
import create_agent  # noqa: E402

AGENT_DIR = ROOT / "agent"
HERO_CLAIM = "CLM-10482"


def dry_run_output(capsys) -> dict:
    assert create_agent.main(["--dry-run"]) == 0
    return json.loads(capsys.readouterr().out)


def instruction_texts() -> dict[str, str]:
    """Author-written agent configuration: generic, with no claim data of any kind."""
    return {
        "instructions.md": common.read_instructions(),
        "config.example.json": (AGENT_DIR / "config.example.json").read_text(encoding="utf-8"),
    }


@pytest.fixture
def agent_texts(capsys) -> dict[str, str]:
    """Everything that becomes part of the agent, including the exact definition create_agent submits."""
    return {**instruction_texts(), "agent definition": json.dumps(dry_run_output(capsys), ensure_ascii=False)}


def synthetic_identity_terms() -> list[str]:
    """Names, record IDs, models and facilities from the synthetic universe."""
    customers = load_json(DATA_DIR / "customers.json")["customers"]
    vehicles = load_json(DATA_DIR / "vehicles.json")["vehicles"]
    facilities = load_json(DATA_DIR / "repair-facilities.json")["repairFacilities"]
    claims = load_json(DATA_DIR / "claims.json")["claims"]
    policies = load_json(DATA_DIR / "policies.json")["policies"]
    terms = {f"{c['firstName']} {c['lastName']}" for c in customers} | {c["customerId"] for c in customers}
    terms |= {v["model"] for v in vehicles} | {v["vehicleId"] for v in vehicles}
    terms |= {f["name"] for f in facilities}
    terms |= {c["claimId"] for c in claims} | {p["policyId"] for p in policies}
    return sorted(terms)


def test_instructions_contain_no_record_identifiers():
    for source, text in instruction_texts().items():
        hits = sorted(set(re.findall(r"\b(?:CLM|CUST|PAP|VEH|EST|DOC|MHPD|AC)-\d[\d-]*", text)))
        assert not hits, f"{source} contains record identifiers: {hits}"


# Hero-specific content (case-insensitive). Generic claims vocabulary ("manual review", "deductible",
# "police report", "supporting evidence") is deliberately allowed: it is ordinary claims practice.
HERO_LEAKAGE = {
    "dollar amounts": r"\$\s?\d",
    "hero line amount": r"\b1,?240\b",
    "hero estimate total": r"\b7,?850\b",
    "lamp/headlamp": r"head\s?lamp|headlight|\bLED\b",
    "front-left": r"front[- ]left|left[- ]front|\bLT\s+(?:front|frt|head|LED|lamp)",
    "right-rear": r"right[- ]rear|rear[- ]right",
    "Contoso Air demo artifacts": r"CT\s?226|contoso[- ]air|airline|flight",
    "spec expected-answer phrasing": r"does not establish corresponding|front-left impact damage|"
                                     r"Manual review before repair authorization",
}


@pytest.mark.parametrize("label,pattern", HERO_LEAKAGE.items(), ids=list(HERO_LEAKAGE))
def test_agent_configuration_has_no_hero_leakage(agent_texts, label, pattern):
    for source, text in agent_texts.items():
        hits = sorted({m.group(0) for m in re.finditer(pattern, text, re.IGNORECASE)})
        assert not hits, f"{source} contains {label}: {hits}"


def test_agent_configuration_names_no_synthetic_entity(agent_texts):
    terms = synthetic_identity_terms()
    for source, text in agent_texts.items():
        hits = [term for term in terms if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE)]
        assert not hits, f"{source} names synthetic entities: {hits}"


def test_agent_configuration_has_no_conclusion_fields(agent_texts):
    for source, text in agent_texts.items():
        for key in FORBIDDEN_KEYS:
            assert key not in text, f"{source} contains the conclusion field {key!r}"


def test_manual_review_is_generic_not_tied_to_a_specific_item():
    """'Manual review' is valid generic guidance, but must never be bound to a particular component or line."""
    instructions = common.read_instructions()
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", instructions):
        if re.search(r"manual review", sentence, re.IGNORECASE):
            assert not re.search(r"lamp|light|bumper|fender|door|wheel|panel|line \d|\$\d", sentence, re.IGNORECASE), sentence


def test_instructions_cover_required_behaviors():
    text = re.sub(r"\s+", " ", common.read_instructions()).lower()
    for phrase in ("claims_operations", "file search", "photograph", "does not establish",
                   "do not approve", "fraud", "authorized claims staff", "needs review", "next step"):
        assert phrase in text, f"instructions do not cover {phrase!r}"


def test_expected_answer_is_not_encoded_in_api_data():
    """The hero conclusion must be reached from evidence: no structured source states it."""
    conclusion = re.compile(r"not established|unsupported|does not (?:establish|support)|manual review|"
                            r"discrepan|inconsisten|needs review", re.IGNORECASE)
    sources = [*DATA_DIR.glob("*.json"), ROOT / "tools" / "openapi.json",
               *(EVIDENCE_DIR.glob("CLM-*/evidence-manifest.json"))]
    for path in sources:
        hits = sorted({m.group(0) for m in conclusion.finditer(path.read_text(encoding="utf-8"))})
        assert not hits, f"{path.relative_to(ROOT)} encodes a conclusion: {hits}"


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------


def test_dry_run_definition_has_exactly_file_search_and_claims_api(capsys):
    printed = dry_run_output(capsys)
    assert printed["name"] == "contoso-claims-review-agent"
    assert printed["knowledgeFiles"] == list(common.KNOWLEDGE_FILES)
    definition = printed["definition"]
    assert definition["kind"] == "prompt"
    assert definition["instructions"] == common.read_instructions()
    tools = definition["tools"]
    assert [t["type"] for t in tools] == ["file_search", "openapi"]
    assert tools[0]["vector_store_ids"] == ["<vector-store-id>"]
    openapi = tools[1]["openapi"]
    assert openapi["name"] == "claims_operations"
    assert openapi["auth"]["type"] == "anonymous"
    operations = {op["operationId"] for path in openapi["spec"]["paths"].values() for op in path.values()}
    assert operations == {"get_claim", "get_policy", "get_customer_claim_history", "get_vehicle"}
    assert [s["url"] for s in openapi["spec"]["servers"]] == ["https://<claims-operations-api>"]
    committed = load_json(ROOT / "tools" / "openapi.json")
    assert {k: v for k, v in openapi["spec"].items() if k != "servers"} == \
        {k: v for k, v in committed.items() if k != "servers"}


def test_empty_knowledge_variant_differs_only_in_knowledge(capsys):
    assert create_agent.main(["--dry-run", "--empty-knowledge", "--name", "eval-noknowledge"]) == 0
    variant = json.loads(capsys.readouterr().out)
    normal = dry_run_output(capsys)
    assert variant["knowledgeFiles"] == []
    assert variant["definition"] == normal["definition"]


def test_knowledge_is_only_the_four_guidance_pdfs():
    names = [p.name for p in common.knowledge_paths()]
    assert names == ["claims-handling-guidelines.pdf", "auto-coverage-guidance.pdf",
                     "repair-estimate-review.pdf", "claims-escalation-guidance.pdf"]
    assert all(p.parent == ROOT / "knowledge" for p in common.knowledge_paths())


def test_tools_url_must_be_public_https(monkeypatch):
    # load_dotenv never overrides variables already set, so these take precedence over a local .env.
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.test/api/projects/p")
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "model")
    monkeypatch.setenv("TOOLS_API_BASE_URL", "http://localhost:8000")
    with pytest.raises(common.ConfigurationError):
        common.load_settings()


# ---------------------------------------------------------------------------
# Claim evidence sent to the agent
# ---------------------------------------------------------------------------


def test_hero_message_attaches_exactly_the_manifest_evidence_in_order():
    manifest = load_json(HERO_EVIDENCE_DIR / "evidence-manifest.json")
    message = common.evidence_message(HERO_CLAIM, common.HERO_PROMPT)
    text, *attachments = message["content"]
    assert text["type"] == "input_text"
    assert text["text"].startswith(f"Selected claim: {HERO_CLAIM}")
    assert text["text"].endswith(f"Adjuster request: {common.HERO_PROMPT}")
    assert len(attachments) == len(manifest["documents"]) == 8
    for entry, part in zip(manifest["documents"], attachments):
        assert entry["documentId"] in text["text"]
        payload = part.get("file_data") or part.get("image_url")
        data = base64.b64decode(payload.split(",", 1)[1])
        assert common.sha256(data) == entry["sha256"]
        expected_type = "input_file" if entry["mediaType"] == "application/pdf" else "input_image"
        assert part["type"] == expected_type
    assert sum(p["type"] == "input_image" for p in attachments) == 5
    assert all(p["detail"] == "high" for p in attachments if p["type"] == "input_image")


def test_evidence_message_contains_no_build_provenance_or_expectations():
    message = common.evidence_message(HERO_CLAIM, common.HERO_PROMPT)
    index = message["content"][0]["text"].split("Adjuster request:")[0].lower()
    for forbidden in ("photos.json", "prompt", "source", "expected", "headlamp", "anomal", "evaluation", "review"):
        assert forbidden not in index, forbidden
    names = [p.get("filename") for p in message["content"] if p.get("filename")]
    assert all(name.endswith(".pdf") for name in names)


def test_every_evidence_package_builds_a_message():
    for manifest_path in sorted(EVIDENCE_DIR.glob("CLM-*/evidence-manifest.json")):
        claim = manifest_path.parent.name
        message = common.evidence_message(claim, "Review this claim.")
        assert len(message["content"]) == 1 + len(load_json(manifest_path)["documents"])


def test_claim_without_package_requires_explicit_no_evidence():
    with pytest.raises(common.ConfigurationError):
        common.claim_evidence("CLM-10419")
    message = common.evidence_message("CLM-10419", "Review this claim.", include_evidence=False)
    assert len(message["content"]) == 1
    assert "no claim evidence items are attached" in message["content"][0]["text"]


def test_tampered_evidence_is_rejected(tmp_path, monkeypatch):
    folder = tmp_path / HERO_CLAIM
    folder.mkdir()
    manifest = load_json(HERO_EVIDENCE_DIR / "evidence-manifest.json")
    entry = dict(manifest["documents"][0])
    (folder / "claim-form.pdf").write_bytes(b"%PDF-1.4 tampered")
    entry["fileName"] = "claim-form.pdf"
    (folder / "evidence-manifest.json").write_text(json.dumps({"claimId": HERO_CLAIM, "documents": [entry]}), encoding="utf-8")
    monkeypatch.setattr(common, "EVIDENCE_DIR", tmp_path)
    with pytest.raises(common.ConfigurationError, match="hash"):
        common.claim_evidence(HERO_CLAIM)


def test_evidence_outside_the_claim_folder_is_rejected(tmp_path, monkeypatch):
    folder = tmp_path / HERO_CLAIM
    folder.mkdir()
    entry = {"documentId": "DOC-1", "fileName": "../source/photos.json", "mediaType": "application/pdf", "sha256": "0"}
    (folder / "evidence-manifest.json").write_text(json.dumps({"claimId": HERO_CLAIM, "documents": [entry]}), encoding="utf-8")
    monkeypatch.setattr(common, "EVIDENCE_DIR", tmp_path)
    with pytest.raises(common.ConfigurationError, match="outside"):
        common.claim_evidence(HERO_CLAIM)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def test_clean_text_removes_citation_markers_only():
    raw = "Line 1 needs review.\ue200filecite\ue202turn0file5\ue201 Next step: ask the shop."
    assert common.clean_text(raw) == "Line 1 needs review. Next step: ask the shop."
    assert common.clean_text("No markers here.") == "No markers here."


def fake_response():
    claim_body = json.dumps({"error": {"code": "SERVICE_UNAVAILABLE", "message": "down"}})
    output = [
        {"type": "openapi_call", "call_id": "c1", "name": "claims_operations_get_claim",
         "arguments": json.dumps({"claimId": "CLM-1"}), "status": "completed"},
        {"type": "openapi_call_output", "call_id": "c1", "output": json.dumps({"response": claim_body})},
        {"type": "openapi_call", "call_id": "c2", "name": "claims_operations_get_claim",
         "arguments": json.dumps({"claimId": "CLM-1"}), "status": "completed"},
        {"type": "openapi_call_output", "call_id": "c2", "output": json.dumps({"response": "{\"claimId\": \"CLM-1\"}"})},
        {"type": "file_search_call", "queries": ["deductible"], "status": "completed",
         "results": [{"filename": "auto-coverage-guidance.pdf", "score": 0.912345}]},
        {"type": "message", "phase": "commentary", "content": [{"type": "output_text", "text": "Checking."}]},
        {"type": "message", "phase": "final_answer",
         "content": [{"type": "output_text", "text": "Answer.\ue200filecite\ue202x\ue201"}]},
    ]
    return SimpleNamespace(id="resp_1", output=output, output_text="Checking.Answer.",
                           usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})


def test_trace_records_calls_errors_repeats_and_searches():
    t = common.trace(fake_response())
    assert [c["operation"] for c in t["apiCalls"]] == ["claims_operations_get_claim"] * 2
    assert [c["errorCode"] for c in t["apiCalls"]] == ["SERVICE_UNAVAILABLE", None]
    assert t["repeatedApiCalls"] == 1
    assert t["fileSearches"] == [{"queries": ["deductible"], "status": "completed",
                                  "results": [{"file": "auto-coverage-guidance.pdf", "score": 0.9123}]}]
    assert t["usage"] == {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}


def test_final_text_prefers_final_answer_phase():
    assert common.final_text(fake_response()) == "Answer."
