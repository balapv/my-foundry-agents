"""Reset the Contoso Claims Processing demo to a clean starting state between presentations.

What it does
  - Removes disposable local runtime state: the Claims Review application log (webapp/.logs/) and
    the pytest cache. With --results it also removes saved smoke/evaluation results
    (evaluation/results/). All of these are git-ignored and recreated on demand.
  - Checks whether the Claims Review application is running. Review sessions live only in that
    server's memory and the browser holds the session ID only in page memory, so a fresh Foundry
    conversation is guaranteed by restarting the server (or, at minimum, reloading the page /
    pressing "New review"). The script tells you which applies.
  - Verifies that the hero evidence, agent instructions, guidance PDFs and OpenAPI description
    still match the validated baseline (demo/baseline.json), that the application is configured
    for the validated agent version, and (unless --offline) that this version, its model,
    instructions, File Search vector store and Claims Operations API tool are available in Foundry.

What it never does
  - Modify or regenerate synthetic data, evidence, guidance or the OpenAPI description.
  - Create, update or delete an agent, agent version, vector store or file in Foundry.
  - Touch the Claims Operations API, its Container App or any other Azure resource.
  - Delete .env, .foundry-state.json, agent/config.json or .deploy/ (needed to run the demo).

Usage (from contoso-claims-processing/):
  python scripts/reset_demo.py                 # reset + verify (a few seconds)
  python scripts/reset_demo.py --results       # also delete evaluation/results/
  python scripts/reset_demo.py --offline       # skip the Foundry/Azure verification
  python scripts/reset_demo.py --url http://127.0.0.1:8010   # where the application runs
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import demo_readiness  # noqa: E402
from demo_readiness import Check  # noqa: E402

DEFAULT_URL = "http://127.0.0.1:8010"
LOG_DIR = ROOT / "webapp" / ".logs"
DISPOSABLE = [ROOT / ".pytest_cache"]
RESULTS_DIR = ROOT / "evaluation" / "results"


def app_running(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/about", timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def remove(path: Path) -> str:
    """Delete one git-ignored runtime directory inside this project."""
    if path.is_symlink() or ROOT not in path.resolve().parents:
        raise ValueError(f"refusing to remove {path}")
    if not path.exists():
        return f"{path.relative_to(ROOT).as_posix()}/ already clean"
    shutil.rmtree(path)
    return f"removed {path.relative_to(ROOT).as_posix()}/"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Claims Review application URL (default {DEFAULT_URL})")
    parser.add_argument("--results", action="store_true", help="also delete saved evaluation/smoke results")
    parser.add_argument("--offline", action="store_true", help="skip the Foundry/Azure verification")
    args = parser.parse_args(argv)

    checks: list[Check] = []
    print("== review sessions")
    about = app_running(args.url)
    if about:
        print(f"  The Claims Review application is running at {args.url} ({about.get('agentName')} v{about.get('agentVersion')}).")
        print("  Its review sessions are in server memory. For a guaranteed fresh Foundry conversation:")
        print("    restart the server (Ctrl+C, then start it again), then reload the browser page.")
        print("  Minimum without a restart: reload the page or press 'New review'; old sessions cannot be resumed.")
    else:
        print(f"  No application is running at {args.url}; the next start has no review sessions.")

    print("== disposable runtime state")
    targets = DISPOSABLE + ([RESULTS_DIR] if args.results else [])
    if about:
        print("  kept webapp/.logs/ (the running server is writing to it; restart, then reset again to clear it)")
    else:
        targets.insert(0, LOG_DIR)
    for path in targets:
        try:
            print(f"  {remove(path)}")
        except OSError as exc:
            checks.append(Check("reset", f"remove {path.name}", False, str(exc)[:120],
                                "Stop the application server, then run the reset again."))
    if not args.results:
        print("  kept evaluation/results/ (use --results to delete saved run records)")

    groups = [("configuration", demo_readiness.configuration()), ("baseline", demo_readiness.frozen_baseline())]
    if not args.offline:
        groups.append(("Foundry (read-only)", demo_readiness.foundry()))
    for title, group in groups:
        print(f"== {title}")
        for check in group:
            label = "SKIP" if check.ok is None else "PASS" if check.ok else "FAIL"
            print(f"  {label}  {check.name}" + (f" - {check.detail}" if check.detail else ""))
        checks += group

    print("\nNot changed: data, evidence, guidance, OpenAPI, agent versions, vector store, Claims Operations API, Azure resources.")
    failed = [c for c in checks if c.ok is False]
    if failed:
        print("\nRemediation:")
        for check in failed:
            print(f"  - [{check.group}] {check.name}: {check.fix}")
        print("\nDEMO RESET INCOMPLETE")
        return 1
    print("\nDEMO RESET COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
