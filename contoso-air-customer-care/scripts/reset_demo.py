"""Reset the Contoso Air demo to a clean starting state. Safe to run right before presenting.

What it resets (local, disposable state only):

* Python caches: __pycache__ folders and .pytest_cache (outside .venv).
* Evaluation run output in evaluation/results/, only with --clear-results.
* Web chat sessions: these live in the web app's memory. The script checks whether the web app is
  running and tells you to restart it or reload the page. Reloading the page always starts a new
  conversation, because the browser stores no session state.

What it verifies, read-only, after the reset:

* The synthetic data and knowledge PDFs are current (the data is deterministic; it is never regenerated here).
* The Operations API is healthy and the hero flight is cancelled "tomorrow".
* The configured Foundry agent version exists, with its knowledge and Operations API tool.

What it never touches: the Foundry agent or its versions, the vector store, the knowledge
documents, policies, synthetic data, .env, .foundry-state.json or any Azure resource.

Usage (from the repository root):

    python scripts/reset_demo.py
    python scripts/reset_demo.py --clear-results     # also delete evaluation/results/
    python scripts/reset_demo.py --port 8080         # web app port to check (default 8080)
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.foundry_common import configure_console, get_settings  # noqa: E402
from scripts.validate_demo import (  # noqa: E402
    Report,
    check_data_and_knowledge,
    check_foundry,
    check_operations_api,
)

SKIP_DIRS = {".venv", "venv", ".git", "node_modules"}


def cache_dirs() -> list[Path]:
    found = []
    for path in REPO_ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        if path.is_dir() and path.name in ("__pycache__", ".pytest_cache"):
            found.append(path)
    return found


def clear_caches() -> None:
    removed = 0
    for path in cache_dirs():
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    print(f"  Removed {removed} Python cache folder(s).")


def clear_results() -> None:
    results = REPO_ROOT / "evaluation" / "results"
    files = [p for p in results.glob("*") if p.name != ".gitkeep"] if results.exists() else []
    for path in files:
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    print(f"  Removed {len(files)} item(s) from evaluation/results/.")


def check_web_sessions(port: int) -> None:
    import httpx

    try:
        health = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=3).json()
    except Exception:  # noqa: BLE001 - not running is the normal case
        print(f"  Web app is not running on port {port}. It starts with no conversations.")
        return
    print(f"  Web app is running on port {port} (agent version {health.get('agentVersion')}).")
    print("  Conversations live in its memory. For a clean start, either:")
    print("    - reload the Travel Assistant page (starts a new conversation), or")
    print("    - stop the web app (Ctrl+C) and start it again (clears every conversation).")


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clear-results", action="store_true", help="Also delete evaluation/results/.")
    parser.add_argument("--port", type=int, default=8080, help="Web app port to check (default 8080).")
    args = parser.parse_args()

    print("Resetting local demo state")
    clear_caches()
    if args.clear_results:
        clear_results()
    check_web_sessions(args.port)

    print("\nVerifying demo state (read-only)")
    report = Report()
    settings = get_settings()
    check_data_and_knowledge(report)
    check_operations_api(report, settings)
    check_foundry(report, settings)

    print("\nManual steps: start a new chat in the Foundry playground, and reload the Travel Assistant page.")
    if report.failures:
        print(f"\nRESET DONE, BUT {len(report.failures)} CHECK(S) FAILED. See demo/troubleshooting.md.")
        return 1
    print("\nRESET COMPLETE. Nothing in Foundry or Azure was changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
