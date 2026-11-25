"""Invocation of the existing Foundry prompt agent (contoso-claims-review-agent).

This is the same runtime path as agent/run_claim_review.py: a Foundry conversation, a response
that references the agent by name and version, the claim evidence attached to the first user
message, and follow-ups sent as text in the same conversation. Responses are streamed only so the
workspace can show which kind of work the agent is actually doing (records, guidance, writing).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from .config import Settings, common
from .errors import ReviewError

# Stage names shown by the frontend; each is set only when the corresponding event is observed.
ITEM_STAGES = {"openapi_call": "records", "file_search_call": "guidance"}


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


class FoundryRuntime:
    """Lazily creates the Foundry project client and resolves the configured agent version."""

    def __init__(self, settings: Settings, project_factory: Callable[[Settings], Any] | None = None):
        self.settings = settings
        self._project_factory = project_factory or (
            lambda s: common.project_client({"FOUNDRY_PROJECT_ENDPOINT": s.project_endpoint}))
        self._lock = threading.Lock()
        self._project = None
        self._client = None
        self._version: str | None = None

    # -- configuration -------------------------------------------------------------------------

    def ensure_configured(self) -> None:
        if not self.settings.project_endpoint:
            raise ReviewError("configuration", "FOUNDRY_PROJECT_ENDPOINT is not set")
        if not self.settings.agent_name:
            raise ReviewError("configuration", "FOUNDRY_AGENT_NAME is not set")

    def configured_version(self) -> str | None:
        """The version used without contacting Foundry: FOUNDRY_AGENT_VERSION, else the deployment state file."""
        if self.settings.agent_version:
            return self.settings.agent_version
        try:
            return common.load_state()["agents"].get(self.settings.agent_name, {}).get("version")
        except (OSError, ValueError, KeyError):
            return None

    def agent(self) -> tuple[str, str]:
        """(name, version). Version: FOUNDRY_AGENT_VERSION, else .foundry-state.json, else the latest in Foundry."""
        with self._lock:
            if self._version is None:
                version = self.configured_version()
                if not version:
                    version = str(self._project_or_create().agents.get(agent_name=self.settings.agent_name)
                                  .versions["latest"].version)
                self._version = str(version)
            return self.settings.agent_name, self._version

    def _project_or_create(self):
        if self._project is None:
            self.ensure_configured()
            self._project = self._project_factory(self.settings)
        return self._project

    def client(self):
        with self._lock:
            if self._client is None:
                self._client = self._project_or_create().get_openai_client()
            return self._client

    # -- conversation --------------------------------------------------------------------------

    def create_conversation(self, claim_id: str) -> str:
        conversation = self.client().conversations.create(
            metadata={"claim": claim_id, "demo": "contoso-claims-processing", "channel": "claims-review-webapp"})
        return conversation.id

    def run_turn(self, conversation_id: str, message: Any, on_stage: Callable[[str], None], timeout: float) -> Any:
        """Send one user turn to the agent in the conversation and return the completed response."""
        name, version = self.agent()
        deadline = time.monotonic() + timeout
        stream = self.client().responses.create(
            conversation=conversation_id,
            input=message,
            include=["file_search_call.results"],
            extra_body=common.agent_reference(name, version),
            stream=True,
            timeout=timeout,
        )
        completed = None
        try:
            for event in stream:
                if time.monotonic() > deadline:
                    raise ReviewError("timeout", f"turn exceeded {timeout:.0f} s")
                kind = _get(event, "type")
                if kind in ("response.created", "response.in_progress"):
                    on_stage("reviewing")
                elif kind == "response.output_item.added":
                    item = _get(event, "item")
                    item_type = _get(item, "type")
                    if item_type in ITEM_STAGES:
                        on_stage(ITEM_STAGES[item_type])
                    elif item_type == "message" and _get(item, "phase") in (None, "final_answer"):
                        on_stage("writing")
                elif kind == "response.completed":
                    completed = _get(event, "response")
                elif kind == "response.failed":
                    error = _get(_get(event, "response"), "error")
                    raise ReviewError("agent_error", f"response failed: {_get(error, 'code')} {_get(error, 'message')}")
                elif kind == "response.incomplete":
                    details = _get(_get(event, "response"), "incomplete_details")
                    raise ReviewError("agent_error", f"response incomplete: {_get(details, 'reason')}")
                elif kind == "error":
                    raise ReviewError("agent_error", f"stream error: {_get(event, 'code')} {_get(event, 'message')}")
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        if completed is None:
            raise ReviewError("agent_error", "stream ended without a completed response")
        return completed
