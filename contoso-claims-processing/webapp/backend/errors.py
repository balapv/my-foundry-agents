"""Adjuster-facing error mapping and safe server-side logging.

The browser receives a short, friendly message and a reference ID. The specific cause (which
evidence file failed, which exception the SDK raised, Foundry conversation/response IDs) is written
only to the server log, with endpoints, GUIDs, tokens and local paths scrubbed from free text.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER_NAME = "claims_review"

MESSAGES = {
    "evidence_validation": (
        "The evidence package for this claim could not be verified, so nothing was sent to the review agent. "
        "Please contact claims support and quote the reference below."
    ),
    "configuration": (
        "The claims review agent is not available because the application is not configured correctly. "
        "Please contact your administrator and quote the reference below."
    ),
    "timeout": (
        "The review agent did not finish in the expected time. "
        "Start a new review to try again with a clean conversation."
    ),
    "agent_error": "The review agent could not complete this request. Please try again.",
    "empty_response": "The review agent did not return an answer. Please try again.",
}
# Whether the adjuster can usefully retry, and whether a retry should start a clean conversation.
RETRY = {
    "evidence_validation": "none",
    "configuration": "none",
    "timeout": "new_review",
    "agent_error": "retry",
    "empty_response": "retry",
}


@dataclass
class ReviewError(Exception):
    """A classified failure of one review turn."""

    code: str
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self.code}: {self.detail}"


def new_reference() -> str:
    return "CR-" + secrets.token_hex(3).upper()


def public_error(code: str, reference: str) -> dict[str, str]:
    return {"code": code, "message": MESSAGES.get(code, MESSAGES["agent_error"]),
            "reference": reference, "retry": RETRY.get(code, "retry")}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

_AUTH_NAMES = ("ClientAuthenticationError", "CredentialUnavailableError", "AuthenticationError", "PermissionDeniedError")
_TIMEOUT_NAMES = ("APITimeoutError", "TimeoutError", "ReadTimeout", "ConnectTimeout", "ServiceResponseTimeoutError")


def _chain(exc: BaseException):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def classify(exc: BaseException) -> ReviewError:
    """Map an exception raised while running a turn to an adjuster-facing error code."""
    if isinstance(exc, ReviewError):
        return exc
    detail = scrub(f"{type(exc).__name__}: {exc}")
    for item in _chain(exc):
        names = {cls.__name__ for cls in type(item).__mro__}
        if names.intersection(_AUTH_NAMES):
            return ReviewError("configuration", detail)
        if names.intersection(_TIMEOUT_NAMES):
            return ReviewError("timeout", detail)
        status = getattr(item, "status_code", None)
        if status is None:
            status = getattr(getattr(item, "response", None), "status_code", None)
        if status in (401, 403, 404):
            # Unauthorized, forbidden, or the configured agent/version does not exist in the project.
            return ReviewError("configuration", detail)
        if status in (408, 504):
            return ReviewError("timeout", detail)
    return ReviewError("agent_error", detail)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_SCRUBBERS = (
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "<token>"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*"), "Bearer <redacted>"),
    (re.compile(r"(?i)\b(api[-_]?key|access[-_]?token|sig|signature|key)\s*[=:]\s*[^\s,;&\"']+"), r"\1=<redacted>"),
    (re.compile(r"https?://[^\s\"'<>)]+"), "<url>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<guid>"),
    (re.compile(r"\b[A-Za-z]:[\\/][^\s\"'<>|]*"), "<path>"),
    (re.compile(r"(?<![\w.])/(?:home|Users|tmp|var|etc|opt|mnt|root)/[^\s\"'<>|]*"), "<path>"),
    (re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]{16,}"), "<data>"),
)


def scrub(text: str) -> str:
    """Remove endpoints, GUIDs (subscription/tenant IDs), tokens, data URIs and local paths from free text."""
    text = str(text)
    for pattern, replacement in _SCRUBBERS:
        text = pattern.sub(replacement, text)
    return text[:2000]


class _JsonLines(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "level": record.levelname,
                   "event": record.getMessage()}
        payload.update(getattr(record, "fields", {}) or {})
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(log_dir: Path) -> logging.Logger:
    """JSON-lines log in a git-ignored folder (webapp/.logs/ by default), plus the console."""
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_claims_review_configured", None) == str(log_dir):
        return logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = _JsonLines()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "claims-review.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:  # pragma: no cover - read-only filesystem; console logging still works
        pass
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    logger._claims_review_configured = str(log_dir)  # type: ignore[attr-defined]
    return logger


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log a structured event. Free-text fields named 'detail' are scrubbed."""
    if "detail" in fields:
        fields["detail"] = scrub(fields["detail"])
    logging.getLogger(LOGGER_NAME).log(level, event, extra={"fields": fields})
