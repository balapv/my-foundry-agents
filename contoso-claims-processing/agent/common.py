"""Shared plumbing for creating and running the Contoso Claims Review prompt agent.

Everything here is deliberately thin: the agent's behavior lives in instructions.md, the company
guidance lives in knowledge/, and the business facts come from the Claims Operations API. This
module only assembles those pieces into Foundry objects and requests.

Local configuration (never committed):
  .env                 FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_DEPLOYMENT_NAME, TOOLS_API_BASE_URL
  agent/config.json    optional overrides of agent/config.example.json
  .foundry-state.json  IDs of the vector store and agent versions this project created
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "agent"
EVIDENCE_DIR = ROOT / "evidence"
KNOWLEDGE_DIR = ROOT / "knowledge"
STATE_FILE = ROOT / ".foundry-state.json"
INSTRUCTIONS_FILE = AGENT_DIR / "instructions.md"
OPENAPI_FILE = ROOT / "tools" / "openapi.json"

# The reusable company guidance uploaded to File Search. Nothing else is ever uploaded.
KNOWLEDGE_FILES = (
    "claims-handling-guidelines.pdf",
    "auto-coverage-guidance.pdf",
    "repair-estimate-review.pdf",
    "claims-escalation-guidance.pdf",
)
EVIDENCE_MEDIA_TYPES = {"application/pdf", "image/jpeg", "image/png"}
HERO_PROMPT = "Review this claim and tell me what I should do next."


class ConfigurationError(RuntimeError):
    """Missing or invalid local configuration."""


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    config = json.loads((AGENT_DIR / "config.example.json").read_text(encoding="utf-8"))
    local = AGENT_DIR / "config.json"
    if local.exists():
        config.update(json.loads(local.read_text(encoding="utf-8")))
    return config


def load_settings(require_tools_url: bool = True) -> dict[str, str]:
    """Read the Foundry and Claims Operations API settings from the environment (.env)."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is in requirements.txt
        load_dotenv = None
    if load_dotenv:
        load_dotenv(ROOT / ".env")
    required = ["FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL_DEPLOYMENT_NAME"]
    if require_tools_url:
        required.append("TOOLS_API_BASE_URL")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ConfigurationError(f"Set {', '.join(missing)} in .env (see .env.example).")
    settings = {name: os.environ.get(name, "") for name in required}
    if require_tools_url and not settings["TOOLS_API_BASE_URL"].startswith("https://"):
        raise ConfigurationError("TOOLS_API_BASE_URL must be a public https:// URL; Foundry calls the API from the cloud.")
    return settings


def read_instructions() -> str:
    return INSTRUCTIONS_FILE.read_text(encoding="utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def knowledge_paths() -> list[Path]:
    paths = [KNOWLEDGE_DIR / name for name in KNOWLEDGE_FILES]
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        raise ConfigurationError(f"Knowledge PDFs missing: {missing}. Run python knowledge/build_pdfs.py.")
    return paths


def openapi_spec(base_url: str) -> dict[str, Any]:
    """The committed Claims Operations OpenAPI document, pointed at the deployed API."""
    spec = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))
    spec = copy.deepcopy(spec)
    spec["servers"] = [{"url": base_url.rstrip("/"), "description": "Claims Operations API"}]
    return spec


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------


def agent_definition(model: str, vector_store_id: str, tools_base_url: str, config: dict[str, Any],
                     instructions: str | None = None):
    """Build the PromptAgentDefinition: instructions + File Search (guidance) + one OpenAPI tool."""
    from azure.ai.projects.models import (
        FileSearchTool,
        OpenApiAnonymousAuthDetails,
        OpenApiFunctionDefinition,
        OpenApiTool,
        PromptAgentDefinition,
    )

    return PromptAgentDefinition(
        model=model,
        instructions=instructions if instructions is not None else read_instructions(),
        tools=[
            FileSearchTool(vector_store_ids=[vector_store_id], max_num_results=config["fileSearchMaxResults"]),
            OpenApiTool(
                openapi=OpenApiFunctionDefinition(
                    name=config["openApiToolName"],
                    description=config["openApiToolDescription"],
                    spec=openapi_spec(tools_base_url),
                    auth=OpenApiAnonymousAuthDetails(),
                )
            ),
        ],
    )


def project_client(settings: dict[str, str]):
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    return AIProjectClient(endpoint=settings["FOUNDRY_PROJECT_ENDPOINT"], credential=DefaultAzureCredential())


# ---------------------------------------------------------------------------
# Local state
# ---------------------------------------------------------------------------


def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"vectorStores": {}, "agents": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Claim evidence
# ---------------------------------------------------------------------------


def claim_evidence(claim_id: str) -> tuple[dict[str, Any], list[tuple[dict[str, Any], bytes]]]:
    """Load a claim's manifest and the bytes of every listed evidence file, verified against it.

    Only files listed in evidence/<claim>/evidence-manifest.json are ever read. Build provenance
    (evidence/source/**, including photo-generation records) is outside the claim folder and is
    never sent to the agent.
    """
    folder = (EVIDENCE_DIR / claim_id).resolve()
    manifest_path = folder / "evidence-manifest.json"
    if not manifest_path.is_file():
        raise ConfigurationError(f"No evidence package for {claim_id} (expected {manifest_path.relative_to(ROOT)}).")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("claimId") != claim_id:
        raise ConfigurationError(f"{manifest_path.name} belongs to {manifest.get('claimId')}, not {claim_id}.")
    items = []
    for entry in manifest["documents"]:
        path = (folder / entry["fileName"]).resolve()
        if folder not in path.parents:
            raise ConfigurationError(f"{entry['fileName']} is outside the claim evidence folder.")
        if entry["mediaType"] not in EVIDENCE_MEDIA_TYPES:
            raise ConfigurationError(f"{entry['fileName']} has unsupported media type {entry['mediaType']}.")
        content = path.read_bytes()
        if sha256(content) != entry["sha256"]:
            raise ConfigurationError(f"{entry['fileName']} does not match its manifest hash; rebuild the evidence.")
        items.append((entry, content))
    return manifest, items


def evidence_index(claim_id: str, entries: list[dict[str, Any]]) -> str:
    lines = [f"Selected claim: {claim_id}", "", "Claim evidence index (items are attached in this order):"]
    for number, entry in enumerate(entries, start=1):
        lines.append(
            f"{number}. {entry['documentId']} | {entry['documentType']} | {entry['title']} | "
            f"received {entry['receivedAt'][:10]} | {Path(entry['fileName']).name}"
        )
    if not entries:
        lines.append("(no claim evidence items are attached to this conversation)")
    return "\n".join(lines)


def evidence_message(claim_id: str, prompt: str, image_detail: str = "high", include_evidence: bool = True) -> dict[str, Any]:
    """The first user message of a claim conversation: evidence index, adjuster request, PDFs, photos."""
    _, items = claim_evidence(claim_id) if include_evidence else ({}, [])
    text = evidence_index(claim_id, [entry for entry, _ in items]) + f"\n\nAdjuster request: {prompt}"
    content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
    for entry, data in items:
        encoded = base64.b64encode(data).decode("ascii")
        if entry["mediaType"] == "application/pdf":
            content.append({"type": "input_file", "filename": Path(entry["fileName"]).name,
                            "file_data": f"data:application/pdf;base64,{encoded}"})
        else:
            content.append({"type": "input_image", "image_url": f"data:{entry['mediaType']};base64,{encoded}",
                            "detail": image_detail})
    return {"type": "message", "role": "user", "content": content}


def describe_message(message: dict[str, Any]) -> dict[str, Any]:
    """A loggable summary of a user message (no base64 payloads)."""
    parts = []
    for part in message["content"] if isinstance(message, dict) else []:
        if part["type"] == "input_text":
            parts.append({"type": "input_text", "text": part["text"]})
        elif part["type"] == "input_file":
            parts.append({"type": "input_file", "filename": part["filename"], "bytes": len(part["file_data"]) * 3 // 4})
        else:
            parts.append({"type": "input_image", "detail": part.get("detail"), "bytes": len(part["image_url"]) * 3 // 4})
    return {"role": "user", "content": parts} if parts else {"role": "user", "content": message}


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


def _dump(item: Any) -> dict[str, Any]:
    return item.model_dump() if hasattr(item, "model_dump") else dict(item)


CITATION_MARKER = re.compile(r"\s?\ue200[^\ue201]*\ue201")


def clean_text(text: str) -> str:
    """Remove the model's inline file-citation markers (private-use characters); annotations carry them."""
    return CITATION_MARKER.sub("", text or "")


def final_text(response: Any) -> str:
    """The agent's final answer: the final_answer message when present, otherwise output_text."""
    for item in map(_dump, response.output):
        if item.get("type") == "message" and item.get("phase") == "final_answer":
            return clean_text("".join(part.get("text", "") for part in item.get("content") or []
                                      if part.get("type") == "output_text"))
    return clean_text(response.output_text)


def tool_error_code(output: str | None) -> str | None:
    """Extract error.code from an OpenAPI tool output, which wraps the API body in {"response": "<json>"}."""
    if not output:
        return None
    try:
        body = json.loads(output)
        if isinstance(body, dict) and isinstance(body.get("response"), str):
            body = json.loads(body["response"])
    except (json.JSONDecodeError, TypeError):
        return None
    error = body.get("error") if isinstance(body, dict) else None
    return error.get("code") if isinstance(error, dict) else None


def trace(response: Any) -> dict[str, Any]:
    """Summarize tool activity in one response: API calls, File Search queries/results, errors."""
    items = list(map(_dump, response.output))
    outputs = {i.get("call_id"): i for i in items if i.get("type") == "openapi_call_output"}
    api_calls, searches = [], []
    for item in items:
        if item.get("type") == "openapi_call":
            output = outputs.get(item.get("call_id"), {}).get("output")
            api_calls.append({"operation": item.get("name"), "arguments": json.loads(item.get("arguments") or "{}"),
                              "errorCode": tool_error_code(output), "status": item.get("status")})
        elif item.get("type") == "file_search_call":
            searches.append({
                "queries": item.get("queries") or [],
                "results": [{"file": r.get("filename"), "score": round(r.get("score") or 0, 4)} for r in item.get("results") or []],
                "status": item.get("status"),
            })
    signatures = [(c["operation"], json.dumps(c["arguments"], sort_keys=True)) for c in api_calls]
    usage = _dump(response.usage) if getattr(response, "usage", None) else None
    return {
        "responseId": response.id,
        "apiCalls": api_calls,
        "repeatedApiCalls": len(signatures) - len(set(signatures)),
        "fileSearches": searches,
        "itemTypes": [i.get("type") for i in items],
        "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")} if usage else None,
    }


def agent_reference(name: str, version: str) -> dict[str, Any]:
    return {"agent_reference": {"name": name, "type": "agent_reference", "version": str(version)}}
