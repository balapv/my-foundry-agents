"""Claims-review sessions: one Foundry conversation per review, evidence attached once.

A session belongs to one claim. Its first turn verifies the claim's evidence package against the
manifest, creates the Foundry conversation and sends the evidence with the adjuster's message.
Later turns send only the adjuster's text in the same conversation, where the agent still has the
evidence and its earlier tool results. Starting a new review discards the local session; it never
changes claim data, evidence, the agent or any cloud resource.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import claims
from .config import Settings, common
from .errors import ReviewError, classify, log_event, new_reference, public_error
from .foundry import FoundryRuntime

MAX_MESSAGE_CHARS = 4000


class SessionNotFound(Exception):
    pass


class SessionBusy(Exception):
    pass


@dataclass
class Turn:
    turn_id: str
    prompt: str
    started: float = field(default_factory=time.monotonic)
    status: str = "running"  # running | completed | failed
    stage: str = "queued"
    stages_seen: list[str] = field(default_factory=list)
    finished: float | None = None
    answer: str | None = None
    error: dict[str, str] | None = None
    evidence_attached: dict[str, int] | None = None

    def set_stage(self, stage: str) -> None:
        self.stage = stage
        if stage not in self.stages_seen:
            self.stages_seen.append(stage)

    def public(self) -> dict[str, Any]:
        end = self.finished or time.monotonic()
        return {
            "turnId": self.turn_id,
            "prompt": self.prompt,
            "status": self.status,
            "stage": self.stage,
            "stagesSeen": list(self.stages_seen),
            "elapsedSeconds": round(end - self.started, 1),
            "answer": self.answer,
            "evidenceAttached": self.evidence_attached,
            "error": self.error,
        }


@dataclass
class Session:
    session_id: str
    claim_id: str
    last_used: float = field(default_factory=time.monotonic)
    conversation_id: str | None = None
    evidence_sent: bool = False
    turns: dict[str, Turn] = field(default_factory=dict)
    running: str | None = None
    closed: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Server-side only: lets a presenter find the run in Foundry. Never sent to the browser.
    response_ids: list[str] = field(default_factory=list)

    @property
    def log_id(self) -> str:
        return hashlib.sha256(self.session_id.encode()).hexdigest()[:10]


def _attachment_summary(message: dict[str, Any]) -> dict[str, int]:
    parts = message.get("content", [])
    return {"documents": sum(1 for p in parts if p.get("type") == "input_file"),
            "photos": sum(1 for p in parts if p.get("type") == "input_image")}


class ReviewService:
    """In-memory review sessions (single-process demo application)."""

    def __init__(self, settings: Settings, runtime: FoundryRuntime, claim_exists: Callable[[str], bool],
                 max_sessions: int = 100, idle_seconds: float = 4 * 3600, run_in_thread: bool = True):
        self.settings = settings
        self.runtime = runtime
        self.claim_exists = claim_exists
        self.max_sessions = max_sessions
        self.idle_seconds = idle_seconds
        self.run_in_thread = run_in_thread
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = threading.Lock()

    # -- sessions ------------------------------------------------------------------------------

    def create(self, claim_id: str) -> Session:
        if not claims.CLAIM_ID.fullmatch(claim_id or "") or not self.claim_exists(claim_id):
            raise claims.NotFound("unknown claim")
        session = Session(session_id=secrets.token_urlsafe(24), claim_id=claim_id)
        with self._lock:
            self._evict()
            self._sessions[session.session_id] = session
        log_event("review.session_created", session=session.log_id, claim=claim_id)
        return session

    def get(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(session_id or "")
            if session is None or session.closed:
                raise SessionNotFound()
            session.last_used = time.monotonic()
            self._sessions.move_to_end(session_id)
            return session

    def delete(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id or "", None)
        if session is None:
            raise SessionNotFound()
        session.closed = True
        log_event("review.session_reset", session=session.log_id, claim=session.claim_id,
                  conversationId=session.conversation_id, turns=len(session.turns))

    def _evict(self) -> None:
        now = time.monotonic()
        for sid in [sid for sid, s in self._sessions.items() if s.running is None and now - s.last_used > self.idle_seconds]:
            self._sessions.pop(sid).closed = True
        while len(self._sessions) >= self.max_sessions:
            idle = next((sid for sid, s in self._sessions.items() if s.running is None), None)
            if idle is None:
                break
            self._sessions.pop(idle).closed = True

    # -- turns ---------------------------------------------------------------------------------

    def send(self, session_id: str, text: str) -> Turn:
        text = (text or "").strip()
        if not text:
            raise ValueError("message is empty")
        if len(text) > MAX_MESSAGE_CHARS:
            raise ValueError("message is too long")
        session = self.get(session_id)
        with session.lock:
            if session.running is not None:
                raise SessionBusy()
            turn = Turn(turn_id=f"t{len(session.turns) + 1}", prompt=text)
            session.turns[turn.turn_id] = turn
            session.running = turn.turn_id
        if self.run_in_thread:
            threading.Thread(target=self._run, args=(session, turn), daemon=True,
                             name=f"claims-review-{turn.turn_id}").start()
        else:
            self._run(session, turn)
        return turn

    def turn(self, session_id: str, turn_id: str) -> Turn:
        session = self.get(session_id)
        turn = session.turns.get(turn_id)
        if turn is None:
            raise SessionNotFound()
        return turn

    def _run(self, session: Session, turn: Turn) -> None:
        started = time.monotonic()
        conversation_id = session.conversation_id
        first = conversation_id is None
        attachments = None
        fields: dict[str, Any] = {"session": session.log_id, "claim": session.claim_id, "turn": turn.turn_id,
                                  "firstTurn": first}
        try:
            self.runtime.ensure_configured()
            if first:
                turn.set_stage("verifying")
                include = claims.has_evidence_package(session.claim_id)
                try:
                    # Verifies every listed file against its manifest hash before anything is sent.
                    message = common.evidence_message(session.claim_id, turn.prompt, self.settings.image_detail, include)
                except (common.ConfigurationError, OSError, KeyError, ValueError) as exc:
                    raise ReviewError("evidence_validation", str(exc)) from exc
                attachments = _attachment_summary(message)
                fields["attachments"] = attachments
                payload: Any = [message]
                name, version = self.runtime.agent()
                conversation_id = self.runtime.create_conversation(session.claim_id)
            else:
                name, version = self.runtime.agent()
                payload = turn.prompt
            fields.update(agent=name, agentVersion=version, conversationId=conversation_id)
            turn.set_stage("sending")
            response = self.runtime.run_turn(conversation_id, payload, turn.set_stage,
                                             self.settings.turn_timeout_seconds)
            answer = common.final_text(response).strip()
            details = common.trace(response)
            fields.update(responseId=details["responseId"],
                          apiCalls=[{"operation": c["operation"], "errorCode": c["errorCode"]} for c in details["apiCalls"]],
                          repeatedApiCalls=details["repeatedApiCalls"],
                          fileSearchFiles=sorted({r["file"] for s in details["fileSearches"] for r in s["results"] if r["file"]}),
                          usage=details["usage"])
            if not answer:
                raise ReviewError("empty_response", "the response contained no answer text")
            with session.lock:
                if first:
                    session.conversation_id = conversation_id
                    session.evidence_sent = bool(attachments and (attachments["documents"] or attachments["photos"]))
                session.response_ids.append(details["responseId"])
                turn.answer = answer
                turn.evidence_attached = attachments
                turn.status = "completed"
            log_event("review.turn_completed", seconds=round(time.monotonic() - started, 1), **fields)
        except Exception as exc:  # every failure becomes an adjuster-facing error with a reference
            error = classify(exc)
            reference = new_reference()
            # A failed first turn leaves no conversation on the session, so a retry starts clean.
            turn.error = public_error(error.code, reference)
            turn.status = "failed"
            log_event("review.turn_failed", logging.WARNING, reference=reference, errorCode=error.code,
                      detail=error.detail, seconds=round(time.monotonic() - started, 1), **fields)
        finally:
            turn.finished = time.monotonic()
            with session.lock:
                session.running = None
