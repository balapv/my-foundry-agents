"""Shared helpers for the Demo 1B voice agent (contoso-air-customer-care-voice).

Used by voice/agent/create_agent.py, voice/agent/run_session.py and voice/tests so they build and
invoke the voice agent the same way. Reuses Demo 1A's settings, Foundry client and OpenAPI loader
from agent/foundry_common.py without modifying them. Nothing here makes customer-service decisions;
that reasoning belongs to the Foundry voice agent.

Voice state (toolbox and agent versions) is recorded in voice/.voice-state.json (git-ignored), never
in Demo 1A's .foundry-state.json.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import sys

VOICE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = VOICE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.foundry_common import (  # noqa: E402  (Demo 1A helpers, reused read-only)
    ConfigError,
    load_env,
    load_tool_spec,
    read_state as read_text_agent_state,
)

VOICE_AGENT_DIR = VOICE_DIR / "agent"
VOICE_STATE_FILE = VOICE_DIR / ".voice-state.json"
TEMPLATE_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


# --------------------------------------------------------------------------- configuration


def load_voice_config() -> dict[str, Any]:
    """voice/agent/config.json if present, else voice/agent/config.example.json."""
    path = VOICE_AGENT_DIR / "config.json"
    if not path.exists():
        path = VOICE_AGENT_DIR / "config.example.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_voice_instructions(config: dict[str, Any] | None = None) -> str:
    config = config or load_voice_config()
    return (VOICE_AGENT_DIR / config.get("instructionsFile", "instructions.md")).read_text(encoding="utf-8").strip()


def template_placeholders(text: str) -> set[str]:
    return set(TEMPLATE_PLACEHOLDER.findall(text))


def voice_settings(config: dict[str, Any] | None = None) -> dict[str, str]:
    """Environment overrides for the voice agent. Nothing environment-specific is committed."""
    load_env()
    config = config or load_voice_config()
    return {
        "project_endpoint": os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip(),
        "tools_api_base_url": os.getenv("TOOLS_API_BASE_URL", "").strip().rstrip("/"),
        "agent_name": (os.getenv("FOUNDRY_VOICE_AGENT_NAME") or config["agentName"]).strip(),
        "model": (os.getenv("FOUNDRY_VOICE_MODEL") or config["model"]["model"]).strip(),
        "model_type": (os.getenv("FOUNDRY_VOICE_MODEL_TYPE") or config["model"]["modelType"]).strip(),
        "agent_version": os.getenv("FOUNDRY_VOICE_AGENT_VERSION", "").strip(),
        "vector_store_id": os.getenv("FOUNDRY_VECTOR_STORE_ID", "").strip(),
        "customer_id": (os.getenv("DEMO_CUSTOMER_ID")
                        or config["structuredInputs"]["customer_id"].get("defaultValue", "")).strip(),
    }


def resolve_vector_store_id(settings: dict[str, str], override: str | None = None) -> tuple[str | None, str]:
    """The shared policy vector store created by Demo 1A. Voice never creates or re-uploads knowledge."""
    if override:
        return override, "command line"
    if settings.get("vector_store_id"):
        return settings["vector_store_id"], "FOUNDRY_VECTOR_STORE_ID"
    state = read_text_agent_state()
    if state.get("vectorStoreId"):
        return str(state["vectorStoreId"]), ".foundry-state.json (Demo 1A, read-only)"
    return None, "not found"


# --------------------------------------------------------------------------- state


def read_voice_state() -> dict[str, Any]:
    if VOICE_STATE_FILE.exists():
        return json.loads(VOICE_STATE_FILE.read_text(encoding="utf-8"))
    return {}


def write_voice_state(state: dict[str, Any]) -> None:
    VOICE_STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def resolve_voice_agent_version(settings: dict[str, str], override: str | None = None) -> tuple[str | None, str]:
    """Precedence: override, FOUNDRY_VOICE_AGENT_VERSION, activeAgentVersion in voice/.voice-state.json, latest."""
    if override:
        return str(override), "command line"
    if settings.get("agent_version"):
        return settings["agent_version"], "FOUNDRY_VOICE_AGENT_VERSION"
    state = read_voice_state()
    if state.get("agentName") == settings.get("agent_name") and state.get("activeAgentVersion"):
        return str(state["activeAgentVersion"]), "voice/.voice-state.json"
    return None, "latest"


# --------------------------------------------------------------------------- toolbox


def toolbox_compatible_spec(spec: Any) -> Any:
    """Copy of the OpenAPI 3.0 spec expressed as OpenAPI 3.1, so documented nulls validate.

    Toolbox OpenAPI tools validate API responses as strict JSON Schema, which ignores the OpenAPI 3.0
    ``nullable`` keyword, so a documented null (for example a child passenger's loyaltyNumber) fails
    validation. The toolbox's 3.0 validator also rejects JSON Schema type arrays. The copy therefore
    declares ``openapi: 3.1.0`` (the spec uses no 3.0-only keywords) and rewrites ``nullable: true``
    as ``type: [T, "null"]``. The shared tools/openapi.json is not modified.
    """
    converted = _nullable_to_type_array(spec)
    if isinstance(converted, dict) and str(converted.get("openapi", "")).startswith("3.0"):
        converted["openapi"] = "3.1.0"
    return converted


def _nullable_to_type_array(spec: Any) -> Any:
    if isinstance(spec, list):
        return [_nullable_to_type_array(item) for item in spec]
    if not isinstance(spec, dict):
        return spec
    converted = {key: _nullable_to_type_array(value) for key, value in spec.items() if key != "nullable"}
    if spec.get("nullable") is True and "type" in converted:
        types = converted["type"] if isinstance(converted["type"], list) else [converted["type"]]
        converted["type"] = types + ([] if "null" in types else ["null"])
        if "enum" in converted and None not in converted["enum"]:
            converted["enum"] = [*converted["enum"], None]
    return converted


def build_toolbox_tools(config: dict[str, Any], tools_api_base_url: str, vector_store_id: str) -> list[Any]:
    """One toolbox = the shared Operations OpenAPI spec (unchanged) + File Search on the shared vector store."""
    from azure.ai.projects.models import (
        FileSearchToolboxTool,
        OpenApiAnonymousAuthDetails,
        OpenApiFunctionDefinition,
        OpenApiToolboxTool,
    )

    toolbox = config["toolbox"]
    openapi = toolbox["openapi"]
    file_search = toolbox["fileSearch"]
    return [
        OpenApiToolboxTool(
            name=openapi["name"],
            description=openapi["description"],
            openapi=OpenApiFunctionDefinition(
                name=openapi["name"],
                description=openapi["description"],
                spec=toolbox_compatible_spec(load_tool_spec(openapi["specFile"], tools_api_base_url)),
                auth=OpenApiAnonymousAuthDetails(),
            ),
        ),
        FileSearchToolboxTool(
            name=file_search["name"],
            description=file_search["description"],
            vector_store_ids=[vector_store_id],
            max_num_results=int(file_search.get("maxNumResults", 8)),
        ),
    ]


# --------------------------------------------------------------------------- voice agent definition


def build_voice_definition(config: dict[str, Any], model: str, model_type: str,
                           toolbox_name: str, toolbox_version: str, portal_default: str | None = None):
    """The voice agent definition: model, voice-native instructions, audio, identity input, one toolbox.

    By default every structured input is required with no default, so a session opened without a trusted
    identity is rejected. ``portal_default`` (opt-in) makes ``customer_id`` optional with that default, so the
    Foundry portal playground, which sends no structured inputs, can start a session.
    """
    from azure.ai.projects.models import (
        StructuredInputDefinition,
        VoiceAgentAudioConfig,
        VoiceAgentAudioInputConfig,
        VoiceAgentAudioOutputConfig,
        VoiceAgentAzureSemanticVadTurnDetection,
        VoiceAgentDefinition,
        VoiceAgentInputTranscription,
        VoiceAgentNoiseReduction,
        VoiceAgentStaticInterimResponseConfig,
        VoiceAgentTemplateGreetingConfig,
        VoiceAgentToolboxTool,
        VoiceOutputModality,
    )

    instructions = load_voice_instructions(config)
    inputs = config.get("structuredInputs", {})
    undeclared = template_placeholders(instructions) - set(inputs)
    if undeclared:
        raise ConfigError(f"instructions.md uses undeclared template inputs: {sorted(undeclared)}")

    voice = config["voice"]
    turn = config["turnDetection"]
    transcription = config["transcription"]
    interim = config.get("interimResponse")
    return VoiceAgentDefinition(
        model_type=model_type,
        model=model,
        instructions=instructions,
        structured_inputs={
            name: (StructuredInputDefinition(description=spec["description"], required=False,
                                             default_value=portal_default, schema={"type": "string"})
                   if portal_default and name == "customer_id" else
                   StructuredInputDefinition(description=spec["description"], required=True,
                                             schema={"type": "string"}))
            for name, spec in inputs.items()
        },
        greeting=VoiceAgentTemplateGreetingConfig(text=config["greeting"]) if config.get("greeting") else None,
        audio=VoiceAgentAudioConfig(
            input=VoiceAgentAudioInputConfig(
                turn_detection=VoiceAgentAzureSemanticVadTurnDetection(
                    interrupt_response=turn.get("interruptResponse", True),
                    create_response=turn.get("createResponse", True),
                    remove_filler_words=turn.get("removeFillerWords", True),
                ),
                noise_reduction=VoiceAgentNoiseReduction(type=config["noiseReduction"])
                if config.get("noiseReduction") else None,
                transcription=VoiceAgentInputTranscription(
                    model=transcription["model"],
                    language=transcription.get("language"),
                    phrase_list=transcription.get("phraseList"),
                ),
            ),
            output=VoiceAgentAudioOutputConfig(
                voice=voice["name"], voice_type=voice["type"], voice_locale=voice.get("locale")),
        ),
        output_modalities=[VoiceOutputModality.AUDIO],
        interim_response=VoiceAgentStaticInterimResponseConfig(
            triggers=interim["triggers"], texts=interim["texts"],
            latency_threshold_ms=int(interim["latencyThresholdMs"]),
        ) if interim else None,
        tools=[VoiceAgentToolboxTool(
            toolbox_name=toolbox_name,
            toolbox_version=str(toolbox_version),
            response_scheduling=config["toolbox"].get("responseScheduling", "when_idle"),
        )],
        store=bool(config.get("storeConversations", True)),
    )


def voice_metadata(config: dict[str, Any]) -> dict[str, str]:
    return {"displayName": config.get("displayName", ""), "sample": "contoso-air-customer-care",
            "channel": "voice"}
