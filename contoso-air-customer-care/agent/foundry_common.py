"""Shared helpers for every component that talks to the Contoso Air Foundry agent.

Used by agent/create_agent.py, the web app backend, the evaluation runner and the scripts,
so they configure and invoke the agent the same way. Nothing in here makes
customer-service decisions; that reasoning belongs to the Foundry agent.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO_ROOT / "agent"
STATE_FILE = REPO_ROOT / ".foundry-state.json"
OPENAPI_SERVER_PLACEHOLDER = "https://YOUR-TOOLS-API-HOST"
SESSION_CONTEXT_LABEL = "Authenticated session context"
DEFAULT_CUSTOMER_ID = "CUST-1007"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


# --------------------------------------------------------------------------- settings


def load_env() -> None:
    """Load REPO_ROOT/.env into the process environment, without overriding real env vars."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv is in requirements.txt, but stay usable without it
        return
    load_dotenv(REPO_ROOT / ".env", override=False)


def configure_console() -> None:
    """Print UTF-8 (em dashes, curly quotes) correctly in Windows consoles."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


@dataclass
class Settings:
    project_endpoint: str = ""
    model_deployment: str = ""
    agent_name: str = ""
    tools_api_base_url: str = ""
    judge_deployment: str = ""
    demo_customer_id: str = DEFAULT_CUSTOMER_ID
    agent_version: str = ""

    def require(self, *names: str) -> None:
        env_names = {
            "project_endpoint": "FOUNDRY_PROJECT_ENDPOINT",
            "model_deployment": "FOUNDRY_MODEL_DEPLOYMENT_NAME",
            "agent_name": "FOUNDRY_AGENT_NAME",
            "tools_api_base_url": "TOOLS_API_BASE_URL",
        }
        missing = [env_names.get(n, n) for n in names if not getattr(self, n)]
        if missing:
            raise ConfigError(
                f"Missing configuration: {', '.join(missing)}. Copy .env.example to .env and set "
                "these values (see README 'Option B - Build with code')."
            )


def load_config() -> dict[str, Any]:
    """Behavioral agent config: agent/config.json if present, else agent/config.example.json."""
    path = AGENT_DIR / "config.json"
    if not path.exists():
        path = AGENT_DIR / "config.example.json"
    return json.loads(path.read_text(encoding="utf-8"))


def get_settings(config: dict[str, Any] | None = None) -> Settings:
    load_env()
    config = config or load_config()
    return Settings(
        project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip(),
        model_deployment=os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "").strip(),
        agent_name=(os.getenv("FOUNDRY_AGENT_NAME") or config.get("agentName", "")).strip(),
        tools_api_base_url=os.getenv("TOOLS_API_BASE_URL", "").strip().rstrip("/"),
        judge_deployment=(os.getenv("FOUNDRY_JUDGE_DEPLOYMENT_NAME") or os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "")).strip(),
        demo_customer_id=(os.getenv("DEMO_CUSTOMER_ID") or DEFAULT_CUSTOMER_ID).strip(),
        agent_version=os.getenv("FOUNDRY_AGENT_VERSION", "").strip(),
    )


def resolve_agent_version(settings: Settings, override: str | None = None) -> tuple[str | None, str]:
    """Return (version, source) for the agent version that clients should invoke.

    Precedence: an explicit override (for example --agent-version), then FOUNDRY_AGENT_VERSION,
    then the activeAgentVersion recorded in .foundry-state.json by create_agent.py. When none is set,
    the version is None and Foundry uses the agent's latest version. The version is never hard-coded.
    """
    if override:
        return str(override), "command line"
    if settings.agent_version:
        return settings.agent_version, "FOUNDRY_AGENT_VERSION"
    state = read_state()
    if state.get("agentName") == settings.agent_name and state.get("activeAgentVersion"):
        return str(state["activeAgentVersion"]), ".foundry-state.json"
    return None, "latest"


def validate_agent_name(name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", name or ""):
        raise ConfigError(
            f"Invalid agent name {name!r}: use letters, numbers and hyphens, start and end with a "
            "letter or number, at most 63 characters (for example contoso-air-customer-care)."
        )


def validate_tools_url(url: str) -> list[str]:
    """Return warnings about a tools API base URL that Foundry may not be able to reach."""
    warnings = []
    if not url.startswith("https://"):
        warnings.append("TOOLS_API_BASE_URL should be an https:// URL; Foundry calls the tools from the cloud.")
    if re.search(r"//(localhost|127\.0\.0\.1|0\.0\.0\.0)\b", url):
        warnings.append("TOOLS_API_BASE_URL points to localhost; Foundry cannot reach it. Deploy with scripts/deploy_tools.py or use a dev tunnel.")
    return warnings


# --------------------------------------------------------------------------- state


def read_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def write_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- agent definition


def load_instructions(config: dict[str, Any] | None = None) -> str:
    config = config or load_config()
    return (AGENT_DIR / config.get("instructionsFile", "instructions.md")).read_text(encoding="utf-8").strip()


def load_tool_spec(spec_file: str, server_url: str) -> dict[str, Any]:
    """Load a committed OpenAPI spec and point its server at the deployed tools API."""
    spec = json.loads((REPO_ROOT / spec_file).read_text(encoding="utf-8"))
    spec["servers"] = [{"url": server_url.rstrip("/")}]
    return spec


def build_tools(config: dict[str, Any], tools_api_base_url: str, vector_store_id: str) -> list[Any]:
    """The agent's tool list: File Search over the policy PDFs plus the Operations API OpenAPI tool(s) in config."""
    from azure.ai.projects.models import (
        FileSearchTool,
        OpenApiAnonymousAuthDetails,
        OpenApiFunctionDefinition,
        OpenApiTool,
    )

    tools: list[Any] = [
        FileSearchTool(
            vector_store_ids=[vector_store_id],
            max_num_results=int(config.get("knowledge", {}).get("maxNumResults", 8)),
        )
    ]
    for tool in config["tools"]:
        tools.append(
            OpenApiTool(
                openapi=OpenApiFunctionDefinition(
                    name=tool["name"],
                    description=tool["description"],
                    spec=load_tool_spec(tool["specFile"], tools_api_base_url),
                    auth=OpenApiAnonymousAuthDetails(),
                )
            )
        )
    return tools


def build_agent_definition(config: dict[str, Any], model: str, tools_api_base_url: str, vector_store_id: str):
    from azure.ai.projects.models import PromptAgentDefinition

    return PromptAgentDefinition(
        model=model,
        instructions=load_instructions(config),
        tools=build_tools(config, tools_api_base_url, vector_store_id),
    )


def agent_metadata(config: dict[str, Any]) -> dict[str, str]:
    return {"displayName": config.get("displayName", ""), "sample": "contoso-air-customer-care"}


def project_client(settings: Settings):
    """AIProjectClient for the Foundry project, authenticated with Microsoft Entra ID."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    settings.require("project_endpoint")
    return AIProjectClient(endpoint=settings.project_endpoint, credential=DefaultAzureCredential())


# --------------------------------------------------------------------------- invoking the agent


def agent_reference(name: str, version: str | None = None) -> dict[str, str]:
    ref = {"name": name, "type": "agent_reference"}
    if version:
        ref["version"] = str(version)
    return ref


def session_context_text(customer_id: str) -> str:
    return (
        f"{SESSION_CONTEXT_LABEL} (provided by the Contoso Air application, not typed by the customer): "
        f"the signed-in customer ID is {customer_id}."
    )


@dataclass
class ConversationHandle:
    """A Foundry conversation plus how the signed-in customer context was attached to it."""

    id: str
    customer_id: str
    context_in_conversation: bool
    turns: int = 0


def create_conversation(openai_client: Any, customer_id: str) -> ConversationHandle:
    """Create a conversation that carries the authenticated customer context as a developer message.

    If the service rejects a developer-role item, fall back to prefixing the first user turn.
    """
    try:
        conversation = openai_client.conversations.create(
            items=[{"type": "message", "role": "developer", "content": session_context_text(customer_id)}]
        )
        return ConversationHandle(conversation.id, customer_id, context_in_conversation=True)
    except Exception as exc:  # noqa: BLE001 - only BadRequest is expected; anything else re-raises below
        if getattr(exc, "status_code", None) != 400:
            raise
        conversation = openai_client.conversations.create()
        return ConversationHandle(conversation.id, customer_id, context_in_conversation=False)


def turn_input(handle: ConversationHandle, user_text: str) -> str | list[dict[str, Any]]:
    if handle.context_in_conversation or handle.turns > 0:
        return user_text
    return [
        {"type": "message", "role": "developer", "content": session_context_text(handle.customer_id)},
        {"type": "message", "role": "user", "content": user_text},
    ]


def response_kwargs(handle: ConversationHandle, user_text: str, agent_name: str, agent_version: str | None = None) -> dict[str, Any]:
    """Arguments for openai_client.responses.create(...) that invoke the Foundry agent."""
    return {
        "conversation": handle.id,
        "input": turn_input(handle, user_text),
        "extra_body": {"agent_reference": agent_reference(agent_name, agent_version)},
    }


# --------------------------------------------------------------------------- parsing responses

TOOL_CATEGORIES = {
    "reservation": ("reservation", "get_customer_reservations"),
    "flight_status": ("flight_status", "get_flight_status"),
    "flight_search": ("flight_search", "search_alternative_flights", "alternatives"),
}

# Customer-facing progress messages for channels (the web app). They describe what the agent is doing
# in plain language and never expose tool names, arguments or results.
STATUS_MESSAGES = {
    "reservation": "Checking your trip…",
    "flight_status": "Checking flight status…",
    "flight_search": "Finding alternative flights…",
    "knowledge": "Checking Contoso Air policies…",
    "reviewing": "Reviewing your options…",
}


def tool_category(name: str | None) -> str | None:
    lowered = (name or "").lower()
    for category, needles in TOOL_CATEGORIES.items():
        if any(needle in lowered for needle in needles):
            return category
    return None


def as_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    for method in ("model_dump", "as_dict", "to_dict"):
        if hasattr(item, method):
            try:
                return getattr(item, method)()
            except TypeError:
                continue
    return dict(getattr(item, "__dict__", {}))


@dataclass
class ToolCall:
    type: str
    name: str = ""
    category: str | None = None
    arguments: Any = None
    output: Any = None
    status: str = ""
    call_id: str = ""


@dataclass
class TurnResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    response_id: str = ""

    @property
    def categories(self) -> list[str]:
        return [c.category for c in self.tool_calls if c.category]

    def calls(self, category: str) -> list[ToolCall]:
        return [c for c in self.tool_calls if c.category == category]


def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def parse_output_items(items: Iterable[Any]) -> list[ToolCall]:
    """Collect tool activity from Responses output items (openapi_call, file_search_call, ...)."""
    calls: list[ToolCall] = []
    by_call_id: dict[str, ToolCall] = {}
    for raw in items:
        item = as_dict(raw)
        kind = item.get("type", "")
        if kind == "file_search_call":
            calls.append(ToolCall(type=kind, name="file_search", category="knowledge",
                                  arguments={"queries": item.get("queries")}, output=item.get("results"),
                                  status=item.get("status", ""), call_id=item.get("id", "")))
        elif kind.endswith("_call") and kind != "message":
            name = item.get("name") or item.get("operation_id") or ""
            call = ToolCall(type=kind, name=name, category=tool_category(name) or tool_category(json.dumps(item, default=str)),
                            arguments=_parse_json(item.get("arguments")), status=item.get("status", ""),
                            call_id=item.get("call_id") or item.get("id", ""))
            if item.get("output") is not None:
                call.output = _parse_json(item["output"])
            calls.append(call)
            if call.call_id:
                by_call_id[call.call_id] = call
        elif kind.endswith("_call_output"):
            target = by_call_id.get(item.get("call_id", ""))
            if target is not None:
                target.output = _parse_json(item.get("output"))
            else:
                name = item.get("name", "")
                calls.append(ToolCall(type=kind, name=name, category=tool_category(name),
                                      output=_parse_json(item.get("output")), call_id=item.get("call_id", "")))
    return calls


def _message_text(item: dict[str, Any]) -> str:
    parts = []
    for content in item.get("content") or []:
        content = as_dict(content)
        if content.get("type") == "output_text":
            parts.append(content.get("text", ""))
    return "".join(parts)


def response_text(response: Any) -> str:
    """Return the agent's reply. Models that emit progress ('commentary' phase) messages before calling
    tools also mark the reply itself as 'final_answer'; only the final answer is returned in that case."""
    output = getattr(response, "output", None)
    if output is None:
        output = as_dict(response).get("output", [])
    messages = [as_dict(raw) for raw in output or []]
    messages = [m for m in messages if m.get("type") == "message"]
    final = [m for m in messages if m.get("phase") == "final_answer"]
    if final:
        return "\n\n".join(_message_text(m) for m in final)
    if messages:
        return "\n\n".join(_message_text(m) for m in messages)
    return getattr(response, "output_text", None) or ""


def summarize_response(response: Any) -> TurnResult:
    output = getattr(response, "output", None)
    if output is None:
        output = as_dict(response).get("output", [])
    return TurnResult(text=response_text(response), tool_calls=parse_output_items(output),
                      response_id=getattr(response, "id", "") or as_dict(response).get("id", ""))


CITATION_MARKER = re.compile(
    r"[ \t]*(?:\u3010[^\u3011]*\u3011|\ue200?filecite(?:\ue202?turn\d+[a-z]+\d+)+\ue201?)")


def clean_customer_text(text: str) -> str:
    """Remove raw retrieval citation markers before showing text to a customer."""
    return CITATION_MARKER.sub("", text).strip()


def ask_agent(openai_client: Any, handle: ConversationHandle, user_text: str, agent_name: str,
              agent_version: str | None = None, include_search_results: bool = False) -> TurnResult:
    """Send one customer message to the Foundry agent and return its reply plus tool activity.

    With include_search_results, File Search calls also return the retrieved policy chunks (for transcripts)."""
    kwargs = response_kwargs(handle, user_text, agent_name, agent_version)
    if include_search_results:
        kwargs["include"] = ["file_search_call.results"]
    response = openai_client.responses.create(**kwargs)
    handle.turns += 1
    return summarize_response(response)
