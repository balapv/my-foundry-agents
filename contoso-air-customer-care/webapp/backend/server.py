"""Contoso Air Travel Assistant web app backend.

The web app is a *channel* for the Foundry prompt agent. It:

* starts a chat session for the signed-in customer (simulated for the demo, see DEMO SIGN-IN below),
* shows a greeting and upcoming-trip card using display-only facts from the Operations API,
* relays each chat message to the configured version of the same Foundry agent used in the Foundry
  portal, in one Foundry conversation per chat session, and
* streams the agent's reply plus friendly progress messages ("Checking your trip…") to the browser.

It makes no customer-service decisions. Rebooking options, policy answers, entitlements and
escalation all come from the agent. Run from the repository root:

    python -m uvicorn server:app --app-dir webapp/backend --port 8080
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402
import openai  # noqa: E402
from azure.core.exceptions import ClientAuthenticationError  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

from agent.foundry_common import (  # noqa: E402
    STATUS_MESSAGES,
    ConfigError,
    ConversationHandle,
    Settings,
    as_dict,
    clean_customer_text,
    create_conversation,
    get_settings,
    load_config,
    project_client,
    resolve_agent_version,
    response_kwargs,
    response_text,
    tool_category,
)

FRONTEND_DIR = REPO_ROOT / "webapp" / "frontend"
MAX_MESSAGE_CHARS = 2000
DEFAULT_TURN_TIMEOUT_SECONDS = 180.0

GENERIC_ERROR = (
    "Sorry, the Travel Assistant is unavailable right now. Please try again in a moment, "
    "or call Contoso Air Customer Care."
)
CUSTOMER_ERRORS = {
    "timeout": "Sorry, the Travel Assistant is taking longer than expected. Please try again.",
    "busy": "The Travel Assistant is very busy right now. Please try again in a minute.",
}

log = logging.getLogger("contoso_air.webapp")


class AgentResponseError(RuntimeError):
    """The Foundry agent reported a failed or incomplete response."""


class TurnTimeout(TimeoutError):
    """The agent did not finish a reply within the configured time."""


# --------------------------------------------------------------------------- streaming helpers


class CitationFilter:
    """Remove retrieval citation markers from streamed text.

    Handles both 【4:0†flight-disruption-policy.pdf】 markers and private-use filecite markers.
    Markers can be split across deltas, so text after an opening marker is held back until it closes.
    """

    PAIRS = {"\u3010": "\u3011", "\ue200": "\ue201"}

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, delta: str) -> str:
        text = self._pending + delta
        self._pending = ""
        out = []
        while text:
            starts = [(text.find(opener), opener) for opener in self.PAIRS if opener in text]
            if not starts:
                out.append(text)
                break
            start, opener = min(starts)
            out.append(text[:start])
            end = text.find(self.PAIRS[opener], start)
            if end < 0:
                self._pending = text[start:]
                break
            text = text[end + 1 :]
        return "".join(out)

    def flush(self) -> str:
        # An unterminated bracket is ordinary text, not a citation.
        pending, self._pending = self._pending, ""
        return clean_customer_text(pending) if pending.startswith("\ue200") else pending


def tool_activity(item: dict[str, Any]) -> str | None:
    """Tool category ('reservation', 'knowledge', ...) for a tool-call output item, else None."""
    kind = item.get("type", "")
    if kind == "file_search_call":
        return "knowledge"
    if kind.endswith("_call"):
        return tool_category(item.get("name") or item.get("operation_id"))
    return None


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def classify_error(exc: BaseException) -> tuple[str, str]:
    """Return (category for server logs, friendly message for the customer). Never expose details."""
    if isinstance(exc, (TurnTimeout, openai.APITimeoutError, httpx.TimeoutException, TimeoutError)):
        return "timeout", CUSTOMER_ERRORS["timeout"]
    if isinstance(exc, openai.RateLimitError):
        return "busy", CUSTOMER_ERRORS["busy"]
    if isinstance(exc, (ClientAuthenticationError, openai.AuthenticationError, openai.PermissionDeniedError)):
        return "authentication", GENERIC_ERROR
    if isinstance(exc, ConfigError):
        return "configuration", GENERIC_ERROR
    if isinstance(exc, (openai.APIConnectionError, openai.InternalServerError)):
        return "foundry_unavailable", GENERIC_ERROR
    if isinstance(exc, AgentResponseError):
        return "agent_response_failed", GENERIC_ERROR
    if isinstance(exc, openai.APIStatusError):
        return f"foundry_http_{exc.status_code}", GENERIC_ERROR
    return "unexpected", GENERIC_ERROR


# --------------------------------------------------------------------------- sessions


@dataclass
class ChatSession:
    id: str
    customer_id: str
    agent_version: str | None
    handle: ConversationHandle | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionStore:
    """In-memory chat sessions for a single-instance demo. Each maps to one Foundry conversation."""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.Lock()

    def create(self, customer_id: str, agent_version: str | None) -> ChatSession:
        session = ChatSession(id=uuid.uuid4().hex, customer_id=customer_id, agent_version=agent_version)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> ChatSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None


# --------------------------------------------------------------------------- display data
# The greeting and trip card show Operations API facts as-is. They are not used to answer the
# customer; the agent retrieves and verifies everything itself.


def fetch_reservations(settings: Settings, customer_id: str) -> dict[str, Any]:
    response = httpx.get(f"{settings.tools_api_base_url}/customers/{customer_id}/reservations", timeout=10.0)
    response.raise_for_status()
    return response.json()


def fetch_flight_status(settings: Settings, flight_number: str, date: str) -> dict[str, Any]:
    response = httpx.get(f"{settings.tools_api_base_url}/flight-status/{flight_number}",
                         params={"date": date}, timeout=10.0)
    response.raise_for_status()
    return response.json()


def trip_summary(payload: dict[str, Any], statuses: dict[tuple[str, str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Shape the reservation (and flight-status) API responses for the greeting and trip card."""
    statuses = statuses or {}
    customer = payload.get("customer") or {}
    reservations = payload.get("reservations") or []
    trip = None
    if reservations:
        reservation = reservations[0]
        segments = []
        for segment in reservation.get("segments", []):
            status = statuses.get((segment.get("flightNumber"), segment.get("date"))) or {}
            segments.append({
                **{key: segment.get(key) for key in
                   ("flightNumber", "date", "origin", "destination", "scheduledDeparture", "scheduledArrival")},
                "originCity": status.get("originCity"),
                "destinationCity": status.get("destinationCity"),
                "flightStatus": status.get("status"),
            })
        trip = {
            "confirmationCode": reservation.get("confirmationCode"),
            "cabin": reservation.get("cabin"),
            "passengers": [
                f"{p.get('firstName', '')} {p.get('lastName', '')}".strip() for p in reservation.get("passengers", [])
            ],
            "segments": segments,
        }
    return {"firstName": customer.get("firstName"), "loyaltyTier": customer.get("loyaltyTier"), "trip": trip}


def load_trip_summary(settings: Settings, customer_id: str,
                      reservations_fetcher: Callable[[Settings, str], dict[str, Any]],
                      status_fetcher: Callable[[Settings, str, str], dict[str, Any]]) -> dict[str, Any]:
    payload = reservations_fetcher(settings, customer_id)
    statuses: dict[tuple[str, str], dict[str, Any]] = {}
    for reservation in (payload.get("reservations") or [])[:1]:
        for segment in reservation.get("segments", []):
            key = (segment.get("flightNumber"), segment.get("date"))
            try:
                statuses[key] = status_fetcher(settings, *key)
            except Exception as exc:  # noqa: BLE001 - the card simply omits the status
                log.warning("Could not load flight status for the trip card: %s", exc)
    return trip_summary(payload, statuses)


# --------------------------------------------------------------------------- app


class ChatRequest(BaseModel):
    # Only the session and the message are accepted. The customer identity comes from the server-side
    # session, never from the browser, so a customer ID in the request body is rejected.
    model_config = ConfigDict(extra="forbid")

    sessionId: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


def create_app(
    settings: Settings | None = None,
    openai_client_factory: Callable[[], Any] | None = None,
    reservations_fetcher: Callable[[Settings, str], dict[str, Any]] = fetch_reservations,
    status_fetcher: Callable[[Settings, str, str], dict[str, Any]] = fetch_flight_status,
    serve_frontend: bool = True,
    turn_timeout_seconds: float | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    config = load_config()
    sessions = SessionStore()
    client_lock = threading.Lock()
    clients: dict[str, Any] = {}
    turn_timeout = turn_timeout_seconds or float(
        os.getenv("WEBAPP_TURN_TIMEOUT_SECONDS") or DEFAULT_TURN_TIMEOUT_SECONDS)

    def default_factory() -> Any:
        settings.require("project_endpoint", "agent_name")
        return project_client(settings).get_openai_client()

    def openai_client() -> Any:
        with client_lock:
            if "openai" not in clients:
                clients["openai"] = (openai_client_factory or default_factory)()
            return clients["openai"]

    def signed_in_customer_id() -> str:
        # DEMO SIGN-IN: every browser is treated as the demo customer configured on the server
        # (DEMO_CUSTOMER_ID, default CUST-1007). A production app would take the customer ID from its
        # own authenticated session instead. This is not production authentication guidance.
        return settings.demo_customer_id

    app = FastAPI(title="Contoso Air Travel Assistant", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        version, _source = resolve_agent_version(settings)
        return {"status": "ok", "agentName": settings.agent_name, "agentVersion": version or "latest"}

    @app.post("/api/session")
    def new_session() -> dict[str, Any]:
        """Start a chat session for the signed-in customer, pinned to the configured agent version."""
        version, source = resolve_agent_version(settings)
        session = sessions.create(signed_in_customer_id(), version)
        if version is None:
            log.warning("No agent version configured; session %s uses the latest version of %s.",
                        session.id, settings.agent_name)
        else:
            log.info("Session %s uses agent %s version %s (from %s).", session.id, settings.agent_name, version, source)
        summary: dict[str, Any] = {"firstName": None, "loyaltyTier": None, "trip": None}
        if settings.tools_api_base_url:
            try:
                summary = load_trip_summary(settings, session.customer_id, reservations_fetcher, status_fetcher)
            except Exception as exc:  # noqa: BLE001 - the greeting card is optional; chat still works
                log.warning("Could not load trip summary: %s", exc)
        return {
            "sessionId": session.id,
            **summary,
            "heroPrompt": config.get("heroPrompt"),
            "starterPrompts": config.get("starterPrompts", []),
        }

    @app.delete("/api/session/{session_id}")
    def end_session(session_id: str) -> dict[str, bool]:
        return {"deleted": sessions.delete(session_id)}

    @app.post("/api/chat")
    def chat(request: ChatRequest) -> StreamingResponse:
        session = sessions.get(request.sessionId)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found. Start a new conversation.")
        message = request.message.strip()
        if not message:
            raise HTTPException(status_code=422, detail="Message is empty.")
        return StreamingResponse(
            stream_turn(session, message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def stream_turn(session: ChatSession, message: str) -> Iterator[str]:
        """Relay one customer message to the Foundry agent and stream its reply as server-sent events."""
        if not session.lock.acquire(blocking=False):
            yield sse("error", {"message": "Please wait for the current reply to finish."})
            return
        started = time.monotonic()
        activity: list[str] = []
        stream = None
        try:
            client = openai_client()
            if session.handle is None:
                session.handle = create_conversation(client, session.customer_id)
            stream = client.responses.create(
                stream=True,
                timeout=turn_timeout,
                **response_kwargs(session.handle, message, settings.agent_name, session.agent_version),
            )
            citations = CitationFilter()
            hidden_items: set[str] = set()
            last_status = None
            streamed = False
            final_text = None
            for event in stream:
                if time.monotonic() - started > turn_timeout:
                    raise TurnTimeout(f"Agent turn exceeded {turn_timeout:.0f}s")
                kind = getattr(event, "type", "")
                if kind == "response.output_item.added":
                    item = as_dict(event.item)
                    status_key = None
                    if item.get("type") == "message":
                        # Progress ("commentary") messages are not part of the reply.
                        if item.get("phase") == "commentary":
                            hidden_items.add(item.get("id"))
                        elif streamed:
                            yield sse("delta", {"text": "\n\n"})
                    elif item.get("type") == "reasoning":
                        status_key = "reviewing" if "flight_search" in activity else None
                    else:
                        status_key = tool_activity(item)
                        if status_key:
                            activity.append(status_key)
                    status = STATUS_MESSAGES.get(status_key) if status_key else None
                    if status and status != last_status:
                        last_status = status
                        yield sse("status", {"message": status})
                elif kind == "response.output_text.delta":
                    if getattr(event, "item_id", None) in hidden_items:
                        continue
                    text = citations.feed(getattr(event, "delta", "") or "")
                    if text:
                        streamed = True
                        yield sse("delta", {"text": text})
                elif kind == "response.completed":
                    final_text = response_text(event.response)
                elif kind in ("response.failed", "response.incomplete", "error"):
                    detail = getattr(getattr(event, "response", None), "error", None) or getattr(event, "message", "")
                    raise AgentResponseError(f"Agent response {kind}: {detail}")
            tail = citations.flush()
            if tail:
                yield sse("delta", {"text": tail})
            session.handle.turns += 1
            log.info("Turn completed [session=%s version=%s seconds=%.1f tools=%s]", session.id,
                     session.agent_version or "latest", time.monotonic() - started, ",".join(activity) or "none")
            yield sse("done", {"text": clean_customer_text(final_text or "")})
        except Exception as exc:  # noqa: BLE001 - never show raw errors or traces to customers
            category, customer_message = classify_error(exc)
            reference = uuid.uuid4().hex[:8]
            log.exception("Agent turn failed [ref=%s category=%s session=%s conversation=%s version=%s]",
                          reference, category, session.id, getattr(session.handle, "id", None),
                          session.agent_version or "latest")
            yield sse("error", {"message": customer_message, "reference": reference})
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001
                    pass
            session.lock.release()

    @app.exception_handler(RequestValidationError)
    def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": "That request could not be processed."}, status_code=422)

    @app.exception_handler(Exception)
    def unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        reference = uuid.uuid4().hex[:8]
        log.error("Unhandled error [ref=%s]", reference, exc_info=exc)
        return JSONResponse({"detail": GENERIC_ERROR, "reference": reference}, status_code=500)

    if serve_frontend and FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("azure").setLevel(logging.WARNING)
app = create_app()
