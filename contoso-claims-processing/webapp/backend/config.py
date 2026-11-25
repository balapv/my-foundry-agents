"""Runtime configuration for Contoso Claims Review, read from environment variables (.env)."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEBAPP_DIR = ROOT / "webapp"
FRONTEND_DIR = WEBAPP_DIR / "frontend"
DEFAULT_LOG_DIR = WEBAPP_DIR / ".logs"

# The application reuses the validated Phase 2 evidence path in agent/common.py rather than copying it.
for path in (ROOT, ROOT / "agent"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import common  # noqa: E402  (agent/common.py)

DEFAULT_CLAIM_ID = "CLM-10482"
DEFAULT_TURN_TIMEOUT_SECONDS = 180.0


@dataclass(frozen=True)
class Settings:
    project_endpoint: str
    agent_name: str
    agent_version: str | None
    claims_api_base_url: str | None
    default_claim_id: str
    turn_timeout_seconds: float
    image_detail: str
    log_dir: Path


def load_dotenv_file() -> None:
    """Load the project's .env (git-ignored) when python-dotenv is available."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is in requirements.txt
        return
    load_dotenv(ROOT / ".env")


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Read settings. Missing Foundry settings are reported when a review starts, not at startup,
    so the claim workspace and evidence viewer still work without cloud configuration."""
    env = os.environ if env is None else env
    config = common.load_config()
    try:
        timeout = float(env.get("CLAIMS_REVIEW_TURN_TIMEOUT_SECONDS") or DEFAULT_TURN_TIMEOUT_SECONDS)
    except ValueError:
        timeout = DEFAULT_TURN_TIMEOUT_SECONDS
    log_dir = env.get("CLAIMS_REVIEW_LOG_DIR")
    return Settings(
        project_endpoint=(env.get("FOUNDRY_PROJECT_ENDPOINT") or "").strip(),
        agent_name=(env.get("FOUNDRY_AGENT_NAME") or config["agentName"]).strip(),
        agent_version=(env.get("FOUNDRY_AGENT_VERSION") or "").strip() or None,
        claims_api_base_url=(env.get("CLAIMS_API_BASE_URL") or env.get("TOOLS_API_BASE_URL") or "").strip() or None,
        default_claim_id=(env.get("CLAIMS_REVIEW_DEFAULT_CLAIM") or DEFAULT_CLAIM_ID).strip(),
        turn_timeout_seconds=max(timeout, 10.0),
        image_detail=config["imageDetail"],
        log_dir=Path(log_dir) if log_dir else DEFAULT_LOG_DIR,
    )
