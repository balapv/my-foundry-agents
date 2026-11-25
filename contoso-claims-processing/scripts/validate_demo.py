"""Is the Contoso Claims Processing demo ready to present right now?

One command answers that question and ends with exactly one status line:

    CLAIMS DEMO READY        or        CLAIMS DEMO NOT READY (followed by the remediation)

Checks, in order (all read-only; nothing creates, updates or deletes an agent or Azure resource):

  offline suites  data, evidence, api, hygiene, knowledge, agent, evaluation, webapp: each stage's
                  generator --check / dry run plus its pytest file, and the node frontend tests
  environment     Python 3.12+, virtual environment, dependencies, Node.js 20+
  configuration   .env present with required settings (values never printed), agent name, agent
                  version pinned to the validated baseline (demo/baseline.json), deployment state
  repository      private/runtime files git-ignored and untracked
  baseline        hero evidence, instructions, guidance PDFs and OpenAPI unchanged (SHA-256)
  demo files      presenter documents, fallback screenshots/architecture visual, labelled transcript
  application     Claims Review backend in-process: frontend assets, CLM-10482 workspace facts,
                  8 evidence items served intact, guidance PDFs, configured agent version
  Claims API      deployed Claims Operations API health and every operation against tools/openapi.json
  Foundry         Azure sign-in, project connectivity, agent version, model, instructions, File Search
                  vector store and OpenAPI tool of the validated version

No model is called unless --live is given. --live then runs ONE hero review and the headlamp
follow-up through the application (scripts/smoke_webapp.py --hero 1 --repeat 0; about a minute).

Usage (from contoso-claims-processing/):
  python scripts/validate_demo.py            # full readiness (about 2 minutes)
  python scripts/validate_demo.py --quick    # skip the offline test suites (seconds; just before presenting)
  python scripts/validate_demo.py --live     # also one live hero review + follow-up
  python scripts/validate_demo.py --offline  # no Azure/Foundry/network checks (development, CI)
  python scripts/validate_demo.py --api-url http://127.0.0.1:8000   # also smoke-test another API instance
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import demo_readiness  # noqa: E402
from demo_readiness import Check, live_check  # noqa: E402

STAGES = [
    ("data", [ROOT / "data" / "generate_data.py", "--check"], "tests/test_data.py"),
    ("evidence", [ROOT / "evidence" / "build_evidence.py", "--check"], "tests/test_evidence.py"),
    ("api", [ROOT / "tools" / "build_openapi.py", "--check"], "tests/test_tools_api.py"),
    ("hygiene", None, "tests/test_hygiene.py"),
    ("knowledge", [ROOT / "knowledge" / "build_pdfs.py", "--check"], "tests/test_knowledge.py"),
    ("agent", [ROOT / "agent" / "create_agent.py", "--dry-run"], "tests/test_agent.py"),
    ("evaluation", [ROOT / "evaluation" / "run_evaluation.py", "--list"], "tests/test_evaluation.py"),
    ("webapp", ["node", "--test", "webapp/frontend/tests"], "tests/test_webapp.py"),
]


def run(command: list) -> tuple[int, str]:
    """Run a Python script/module with this interpreter, or a node command as given."""
    argv = list(map(str, command)) if command[0] == "node" else [sys.executable, *map(str, command)]
    try:
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        return 1, f"{argv[0]} was not found; install Node.js 20 or later to run the frontend tests."
    return result.returncode, (result.stdout + result.stderr).strip()


def check_summary(check: list, output: str) -> str:
    if check[0] == "node":
        counts = dict(re.findall(r"^(?:#|ℹ) (tests|pass|fail|skipped|todo) (\d+)$", output, re.M))
        return ", ".join(f"{counts[k]} {k}" for k in ("tests", "pass", "fail", "skipped") if k in counts) or output[-200:]
    return output.splitlines()[-1] if output else ""


def check_label(check: list) -> str:
    if check[0] == "node":
        return " ".join(map(str, check))
    return f"{Path(check[0]).relative_to(ROOT).as_posix()} {check[1]}"


def pytest_summary(output: str) -> str:
    lines = [line.strip(" =") for line in output.splitlines() if re.search(r"\d+ (passed|failed|error)", line)]
    return lines[-1] if lines else "no pytest summary found"


def offline_suites() -> list[Check]:
    checks = []
    for name, check, test_file in STAGES:
        ok = True
        details = []
        if check:
            code, output = run(check)
            details.append(f"{check_label(check)}: {check_summary(check, output)}")
            ok &= code == 0
            if code:
                print(output)
            elif check[0] == "node" and (not re.search(r"^(?:#|ℹ) fail 0$", output, re.M)
                                         or re.search(r"^(?:#|ℹ) skipped [1-9]", output, re.M)):
                ok = False
                print(output)
        code, output = run(["-m", "pytest", test_file, "-rfEsw", "-p", "no:cacheprovider"])
        details.append(f"{test_file}: {pytest_summary(output)}")
        if code:
            print(output)
        ok &= code == 0
        checks.append(Check("offline suites", name, ok, "; ".join(details),
                            f"Fix the failing {name} checks above (python -m pytest {test_file} -rfEsw)."))
        print_check(checks[-1])
    return checks


def live_hero() -> Check:
    """One hero review and the headlamp follow-up through the application (two model calls)."""
    print("  running one live hero review + headlamp follow-up (about a minute)...", flush=True)
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "smoke_webapp.py"), "--hero", "1", "--repeat", "0"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    output = result.stdout + result.stderr
    lines = [line.strip() for line in output.splitlines() if re.match(r"\s+(A1|A2) (PASS|FAIL)|\s+x |^\d+/\d+ scored", line)]
    for line in lines:
        print(f"    {line}")
    return Check("live", "hero review + follow-up", result.returncode == 0, "; ".join(lines[-1:]) or output[-200:],
                 "Read the answer in evaluation/results/webapp-smoke/. A rate limit or slow model is a live-service "
                 "condition: wait a few minutes and run --live once more, or present with the fallback "
                 "(demo/troubleshooting.md). Do not change the agent.")


def print_check(check: Check) -> None:
    label = "SKIP" if check.ok is None else "PASS" if check.ok else "FAIL"
    print(f"  {label}  {check.name}" + (f" - {check.detail}" if check.detail else ""), flush=True)


def run_group(title: str, checks: list[Check]) -> list[Check]:
    print(f"== {title}", flush=True)
    for check in checks:
        print_check(check)
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="skip the offline test suites")
    parser.add_argument("--offline", action="store_true", help="skip Azure, Foundry and network checks")
    parser.add_argument("--live", action="store_true", help="also run one live hero review and follow-up")
    parser.add_argument("--api-url", help="also smoke-test the Claims Operations API at this base URL")
    args = parser.parse_args(argv)
    if args.live and args.offline:
        parser.error("--live needs Foundry; do not combine it with --offline")

    results: list[Check] = []
    if not args.quick:
        print("== offline suites", flush=True)
        results += offline_suites()
    results += run_group("environment", demo_readiness.local_environment())
    results += run_group("configuration", demo_readiness.configuration())
    results += run_group("repository", demo_readiness.private_files())
    results += run_group("baseline", demo_readiness.frozen_baseline())
    results += run_group("demo files", demo_readiness.documentation())
    results += run_group("application", demo_readiness.application(use_deployed_api=not args.offline))
    if args.offline:
        results.append(Check("cloud", "Azure, Foundry and Claims Operations API", None, "skipped (--offline)"))
        print_check(results[-1])
    else:
        results += run_group("Claims Operations API", demo_readiness.claims_api())
        results += run_group("Foundry", demo_readiness.foundry())
    if args.api_url:
        problems = live_check(args.api_url)
        results += run_group(f"API at {args.api_url}", [Check("api-url", "operations match OpenAPI", not problems,
                                                              "; ".join(problems)[:200], "See the problems listed.")])
    if args.live:
        print("== live", flush=True)
        if any(c.ok is False for c in results):
            results.append(Check("live", "hero review + follow-up", None, "skipped: fix the failures above first"))
            print_check(results[-1])
        else:
            results.append(live_hero())
            print_check(results[-1])

    failed = [c for c in results if c.ok is False]
    skipped = [c for c in results if c.ok is None]
    passed = sum(c.ok is True for c in results)
    print(f"\n{passed} passed, {len(failed)} failed, {len(skipped)} skipped")
    if failed or args.offline:
        print("\nRemediation:")
        for check in failed:
            print(f"  - [{check.group}] {check.name}: {check.fix}")
        if args.offline:
            print("  - Cloud readiness was not checked (--offline). Run without --offline before presenting.")
        print("\nCLAIMS DEMO NOT READY")
        return 1 if failed else 0
    if not args.live:
        print("\nOptional: python scripts/validate_demo.py --quick --live  (one live hero review + follow-up)")
    print("\nCLAIMS DEMO READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
