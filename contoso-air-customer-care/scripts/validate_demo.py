"""Is the Contoso Air demo ready to present right now?

Runs a focused, read-only set of checks and ends with DEMO READY or DEMO NOT READY:

    1. Local prerequisites   Python version, installed packages, required demo files
    2. Configuration         .env present, required settings set (values are never printed)
    3. Data and knowledge    synthetic data current and valid, policy PDFs current
    4. Operations API        /health, the demo customer's reservation, the cancelled flight
    5. Foundry               sign-in, project reachable, agent and resolved version exist,
                             knowledge (vector store) indexed, tool points at the Operations API
    6. Web application       backend starts in-process, /api/health, /api/session, frontend served

It never creates, updates or deletes the agent, its versions, the vector store or any data.

Usage (from the repository root):

    python scripts/validate_demo.py                   # quick checks, no model calls (about 10-20 s)
    python scripts/validate_demo.py --hero            # ...plus ONE live hero turn through the web app
    python scripts/validate_demo.py --comprehensive   # ...plus pytest, validate_webapp.py and the
                                                      #    deterministic evaluation suite (slow, many model calls)

Exits with code 1 when the demo is not ready.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.foundry_common import (  # noqa: E402
    as_dict,
    configure_console,
    get_settings,
    load_config,
    load_instructions,
    project_client,
    resolve_agent_version,
    validate_tools_url,
)

MIN_PYTHON = (3, 10)
REQUIRED_PACKAGES = ("fastapi", "uvicorn", "httpx", "openai", "azure.ai.projects", "azure.identity", "dotenv", "pytest")
REQUIRED_SETTINGS = {
    "FOUNDRY_PROJECT_ENDPOINT": "project_endpoint",
    "FOUNDRY_MODEL_DEPLOYMENT_NAME": "model_deployment",
    "FOUNDRY_AGENT_NAME": "agent_name",
    "TOOLS_API_BASE_URL": "tools_api_base_url",
}
REQUIRED_FILES = (
    "agent/instructions.md",
    "agent/create_agent.py",
    "tools/openapi.json",
    "webapp/frontend/index.html",
    "docs/foundry-ui-agent-setup.md",
    "demo/demo-script.md",
    "demo/setup-checklist.md",
    "demo/troubleshooting.md",
    "demo/architecture.md",
    "demo/fallback-transcript.md",
)


@dataclass
class Check:
    section: str
    name: str
    status: str  # PASS, WARN or FAIL
    detail: str = ""
    fix: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    section: str = ""

    def add(self, name: str, status: str, detail: str = "", fix: str = "") -> Check:
        check = Check(self.section, name, status, detail, fix)
        self.checks.append(check)
        line = f"  [{status}] {name}"
        if detail:
            line += f": {detail}"
        print(line)
        if fix and status != "PASS":
            print(f"         -> {fix}")
        return check

    def ok(self, name: str, detail: str = "") -> None:
        self.add(name, "PASS", detail)

    def warn(self, name: str, detail: str, fix: str = "") -> None:
        self.add(name, "WARN", detail, fix)

    def fail(self, name: str, detail: str, fix: str = "") -> None:
        self.add(name, "FAIL", detail, fix)

    def start(self, title: str) -> None:
        self.section = title
        print(f"\n{title}")

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == "FAIL"]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == "WARN"]


def run_script(args: list[str], timeout: float = 600) -> tuple[int, str]:
    process = subprocess.run([sys.executable, *args], cwd=REPO_ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout)
    output = (process.stdout + process.stderr).strip()
    return process.returncode, output.splitlines()[-1] if output else ""


def describe_error(exc: BaseException) -> str:
    """A short, secret-free description of an exception (no URLs or response bodies)."""
    text = str(exc).splitlines()[0] if str(exc) else ""
    if "://" in text:
        text = ""
    return f"{type(exc).__name__}{': ' + text[:160] if text else ''}"


# --------------------------------------------------------------------------- 1. local


def check_local(report: Report) -> None:
    report.start("1. Local prerequisites")
    version = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info >= MIN_PYTHON:
        report.ok("Python", version)
    else:
        report.fail("Python", f"{version} is older than {'.'.join(map(str, MIN_PYTHON))}",
                    "Install Python 3.10 or later and re-run scripts/setup.ps1 (or setup.sh).")
    if sys.prefix == sys.base_prefix:
        report.warn("Virtual environment", "not running inside a virtual environment",
                    "Activate .venv (.venv\\Scripts\\Activate.ps1 or source .venv/bin/activate).")
    else:
        report.ok("Virtual environment", "active")
    missing = [name for name in REQUIRED_PACKAGES if importlib.util.find_spec(name) is None]
    if missing:
        report.fail("Python packages", f"missing {', '.join(missing)}", "Run: python -m pip install -r requirements.txt")
    else:
        report.ok("Python packages", "installed")
    absent = [path for path in REQUIRED_FILES if not (REPO_ROOT / path).exists()]
    if absent:
        report.fail("Demo files", f"missing {', '.join(absent)}", "Restore the missing files from the repository.")
    else:
        report.ok("Demo files", f"{len(REQUIRED_FILES)} present")


# --------------------------------------------------------------------------- 2. configuration


def check_configuration(report: Report, settings: Any) -> bool:
    report.start("2. Configuration")
    if (REPO_ROOT / ".env").exists():
        report.ok(".env", "present")
    else:
        report.warn(".env", "not found; using process environment variables only",
                    "Copy .env.example to .env and fill in your values.")
    missing = [env for env, attr in REQUIRED_SETTINGS.items() if not getattr(settings, attr)]
    if missing:
        report.fail("Required settings", f"not set: {', '.join(missing)}", "Set them in .env (see .env.example).")
    else:
        report.ok("Required settings", "set (values not shown)")
    if settings.tools_api_base_url:
        for warning in validate_tools_url(settings.tools_api_base_url):
            report.fail("TOOLS_API_BASE_URL", warning)
    if settings.agent_name:
        report.ok("Agent name", settings.agent_name)
    version, source = resolve_agent_version(settings)
    if version:
        report.ok("Configured agent version", f"{version} (from {source})")
    else:
        report.warn("Configured agent version", "none configured; clients will use the agent's latest version",
                    "Set FOUNDRY_AGENT_VERSION in .env to pin the version you validated.")
    return not missing


# --------------------------------------------------------------------------- 3. data and knowledge


def check_data_and_knowledge(report: Report) -> None:
    report.start("3. Data and knowledge")
    for name, script, fix in (
        ("Synthetic data", "data/generate_data.py", "Do not edit data by hand. Restore data/*.json from the repository."),
        ("Knowledge PDFs", "knowledge/build_pdfs.py", "Run: python knowledge/build_pdfs.py (then see troubleshooting.md "
                                                      "before refreshing the agent's knowledge)."),
    ):
        code, last_line = run_script([script, "--check"])
        if code == 0:
            report.ok(name, last_line)
        else:
            report.fail(name, last_line or f"{script} --check failed", fix)


# --------------------------------------------------------------------------- 4. Operations API


def check_operations_api(report: Report, settings: Any) -> None:
    import httpx

    report.start("4. Operations API")
    if not settings.tools_api_base_url:
        report.fail("Operations API", "TOOLS_API_BASE_URL is not set", "Deploy with scripts/deploy_tools.py, then set it in .env.")
        return
    base = settings.tools_api_base_url
    fix = ("Check the Container App in the Azure portal; redeploy with "
           "python scripts/deploy_tools.py --resource-group <rg> --update-env if needed.")
    try:
        started = time.monotonic()
        health = httpx.get(f"{base}/health", timeout=30)  # allows for a container cold start
        health.raise_for_status()
        report.ok("Health", f"HTTP {health.status_code} in {time.monotonic() - started:.1f}s")
    except Exception as exc:  # noqa: BLE001
        report.fail("Health", describe_error(exc), fix)
        return
    try:
        payload = httpx.get(f"{base}/customers/{settings.demo_customer_id}/reservations", timeout=15).json()
        reservations = payload.get("reservations") or []
        if payload.get("error") or not reservations:
            report.fail("Demo customer reservation", f"none returned for {settings.demo_customer_id}",
                        "Check DEMO_CUSTOMER_ID and that the deployed API serves the current data.")
            return
        reservation = reservations[0]
        segment = (reservation.get("segments") or [{}])[0]
        report.ok("Demo customer reservation",
                  f"{len(reservation.get('passengers', []))} passengers, {reservation.get('cabin')}, "
                  f"{segment.get('flightNumber')} {segment.get('origin')}-{segment.get('destination')} on {segment.get('date')}")
        status = httpx.get(f"{base}/flight-status/{segment.get('flightNumber')}",
                           params={"date": segment.get("date")}, timeout=15).json()
        if status.get("status") == "Cancelled":
            report.ok("Hero flight status", f"{segment.get('flightNumber')} is Cancelled")
        else:
            report.fail("Hero flight status", f"{segment.get('flightNumber')} is {status.get('status') or status.get('error')}",
                        "The deployed API should rebase dates so the hero flight is cancelled tomorrow; "
                        "check DEMO_TODAY on the Container App.")
    except Exception as exc:  # noqa: BLE001
        report.fail("Demo customer reservation", describe_error(exc), fix)


# --------------------------------------------------------------------------- 5. Foundry


def check_foundry(report: Report, settings: Any) -> None:
    report.start("5. Foundry agent")
    if not settings.project_endpoint or not settings.agent_name:
        report.fail("Foundry", "FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_AGENT_NAME is not set")
        return
    from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ResourceNotFoundError

    try:
        client = project_client(settings)
        agent = as_dict(client.agents.get(settings.agent_name))
        latest = ((agent.get("versions") or {}).get("latest") or {}).get("version")
        report.ok("Sign-in and project", "reachable")
        report.ok("Agent exists", f"{settings.agent_name} (latest version {latest})")
    except ClientAuthenticationError as exc:
        report.fail("Sign-in", describe_error(exc), "Run: az login (and az account set --subscription <your subscription>).")
        return
    except ResourceNotFoundError:
        report.fail("Agent exists", f"no agent named {settings.agent_name} in this project",
                    "Check FOUNDRY_AGENT_NAME, or create the agent (README Option A or Option B).")
        return
    except HttpResponseError as exc:
        hint = "Your account needs the Foundry User role (or higher) on the project." if exc.status_code == 403 else \
            "Check FOUNDRY_PROJECT_ENDPOINT (project Overview page in the Foundry portal)."
        report.fail("Sign-in and project", f"HTTP {exc.status_code}", hint)
        return
    except Exception as exc:  # noqa: BLE001
        report.fail("Sign-in and project", describe_error(exc),
                    "Check network access, FOUNDRY_PROJECT_ENDPOINT and az login.")
        return

    version, source = resolve_agent_version(settings)
    version = version or latest
    try:
        details = as_dict(client.agents.get_version(settings.agent_name, str(version)))
    except ResourceNotFoundError:
        report.fail("Agent version", f"version {version} (from {source}) does not exist",
                    "Set FOUNDRY_AGENT_VERSION to an existing version (see troubleshooting.md).")
        return
    definition = details.get("definition") or {}
    report.ok("Agent version", f"{version} ({definition.get('kind')} agent, model {definition.get('model')})")
    if latest and str(latest) != str(version):
        report.warn("Newer version exists", f"latest is {latest}; the demo uses {version}",
                    "Fine if intentional. Run validation against the version you will present.")
    if definition.get("kind") != "prompt":
        report.fail("Agent kind", f"{definition.get('kind')}", "The demo expects a prompt agent.")

    if (definition.get("instructions") or "").strip() == load_instructions().strip():
        report.ok("Instructions", "match agent/instructions.md")
    else:
        report.warn("Instructions", "differ from agent/instructions.md",
                    "Expected if the version was edited in the portal; otherwise the agent and repository have drifted.")

    tools = [dict(tool) for tool in definition.get("tools") or []]
    file_search = [t for t in tools if t.get("type") == "file_search"]
    openapi = [t for t in tools if t.get("type") == "openapi"]
    check_knowledge(report, client, file_search)
    if len(openapi) != 1:
        report.fail("Operations API tool", f"{len(openapi)} OpenAPI tools found; expected 1",
                    "Add the Contoso Air Operations OpenAPI tool (docs/foundry-ui-agent-setup.md).")
    else:
        spec = dict(openapi[0].get("openapi") or {}).get("spec") or {}
        operations = sorted(op.get("operationId", "") for path in (spec.get("paths") or {}).values()
                            for op in path.values() if isinstance(op, dict))
        servers = [server.get("url", "").rstrip("/") for server in spec.get("servers") or []]
        report.ok("Operations API tool", ", ".join(operations))
        if settings.tools_api_base_url and settings.tools_api_base_url not in servers:
            report.fail("Tool server URL", "the agent's OpenAPI tool points to a different server than TOOLS_API_BASE_URL",
                        "Update the tool's server URL in the portal, or align TOOLS_API_BASE_URL with the deployed API.")
        else:
            report.ok("Tool server URL", "matches TOOLS_API_BASE_URL")


def check_knowledge(report: Report, client: Any, file_search: list[dict[str, Any]]) -> None:
    if not file_search:
        report.fail("Knowledge", "no File Search tool on the agent", "Add the four policy PDFs as knowledge.")
        return
    store_ids = list(file_search[0].get("vector_store_ids") or [])
    expected = len(load_config()["knowledge"]["files"])
    try:
        store = client.get_openai_client().vector_stores.retrieve(store_ids[0])
    except Exception as exc:  # noqa: BLE001
        report.fail("Knowledge", f"vector store not readable ({describe_error(exc)})",
                    "Open the agent's Knowledge in the portal; see troubleshooting.md.")
        return
    counts = store.file_counts
    if store.status == "completed" and counts.completed >= expected and counts.failed == 0:
        report.ok("Knowledge", f"{counts.completed} documents indexed")
    else:
        report.fail("Knowledge", f"status {store.status}, {counts.completed}/{expected} indexed, {counts.failed} failed",
                    "Wait for indexing to finish, or see troubleshooting.md (knowledge/vector store).")
        return
    knowledge_hash = (store.metadata or {}).get("knowledgeHash")
    if knowledge_hash:
        from agent.create_agent import knowledge_hash as current_hash

        if knowledge_hash == current_hash(load_config()["knowledge"]["files"]):
            report.ok("Knowledge content", "matches knowledge/*.pdf")
        else:
            report.warn("Knowledge content", "indexed PDFs differ from knowledge/*.pdf",
                        "Only refresh knowledge after the demo; see troubleshooting.md.")


# --------------------------------------------------------------------------- 6. web application


def load_server_module() -> Any:
    backend = REPO_ROOT / "webapp" / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    return importlib.import_module("server")


def check_webapp(report: Report, settings: Any) -> None:
    report.start("6. Web application")
    try:
        from fastapi.testclient import TestClient

        server = load_server_module()
        logging.getLogger().setLevel(logging.WARNING)  # the backend configures INFO request logging on import
        client = TestClient(server.create_app(settings=settings))
        health = client.get("/api/health").json()
        expected, _ = resolve_agent_version(settings)
        report.ok("Backend starts", f"agent {health.get('agentName')} version {health.get('agentVersion')}")
        if expected and str(health.get("agentVersion")) != str(expected):
            report.fail("Web app agent version", f"{health.get('agentVersion')} != {expected}")
        session = client.post("/api/session").json()
        trip = session.get("trip") or {}
        segment = (trip.get("segments") or [{}])[0]
        if session.get("firstName") and segment.get("flightStatus") == "Cancelled":
            report.ok("Session and trip card", f"{len(trip.get('passengers', []))} travelers, "
                                               f"{segment.get('flightNumber')} {segment.get('flightStatus')}")
        else:
            report.fail("Session and trip card", "greeting or cancelled trip missing",
                        "Check TOOLS_API_BASE_URL and DEMO_CUSTOMER_ID.")
        client.delete(f"/api/session/{session.get('sessionId')}")
        page = client.get("/")
        if page.status_code == 200 and "Contoso Air" in page.text:
            report.ok("Frontend", "served at /")
        else:
            report.fail("Frontend", f"HTTP {page.status_code}")
    except Exception as exc:  # noqa: BLE001
        report.fail("Web application", describe_error(exc),
                    "Run: python -m uvicorn server:app --app-dir webapp/backend --port 8080 to see the error.")


# --------------------------------------------------------------------------- optional live checks


def check_hero(report: Report) -> None:
    """One live hero turn through the web app, using the same checks as scripts/validate_webapp.py."""
    report.start("7. Live hero smoke check (one model call)")
    import httpx

    from scripts import validate_webapp as web

    port = web.free_port()
    process = web.start_server(port)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=httpx.Timeout(300, connect=10)) as client:
            session = client.post("/api/session").json()
            prompt = session.get("heroPrompt") or load_config()["heroPrompt"]
            turn = web.send(client, session["sessionId"], prompt)
            web.common_checks(turn)
            web.check_hero(turn)
            client.delete(f"/api/session/{session['sessionId']}")
    finally:
        process.terminate()
        process.wait(timeout=15)
    print(f"  progress: {' -> '.join(turn.statuses) or '(none)'}")
    failed = [name for name, ok in turn.checks if not ok]
    if failed:
        report.fail("Hero scenario", f"{len(failed)} of {len(turn.checks)} checks failed in {turn.seconds:.0f}s: "
                    + "; ".join(failed), "See demo/troubleshooting.md (unexpected agent answer).")
    else:
        report.ok("Hero scenario", f"{len(turn.checks)} checks passed in {turn.seconds:.0f}s")


def check_comprehensive(report: Report) -> None:
    report.start("8. Comprehensive checks (slow; many model calls)")
    steps = [
        ("Offline test suite", ["-m", "pytest", "-q"]),
        ("Web app hero + follow-ups", ["scripts/validate_webapp.py"]),
        ("Evaluation suite (deterministic checks)", ["evaluation/run_evaluation.py", "--no-judge"]),
    ]
    for name, args in steps:
        started = time.monotonic()
        code, last_line = run_script(args, timeout=3600)
        detail = f"{last_line} ({time.monotonic() - started:.0f}s)"
        if code == 0:
            report.ok(name, detail)
        else:
            report.fail(name, detail, f"Run python {' '.join(args)} for details.")


# --------------------------------------------------------------------------- main


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hero", action="store_true", help="Also run one live hero turn through the web app.")
    parser.add_argument("--comprehensive", action="store_true",
                        help="Also run pytest, scripts/validate_webapp.py and evaluation/run_evaluation.py --no-judge.")
    args = parser.parse_args()

    started = time.monotonic()
    report = Report()
    print("Contoso Air demo readiness check")
    check_local(report)
    settings = get_settings()
    configured = check_configuration(report, settings)
    check_data_and_knowledge(report)
    check_operations_api(report, settings)
    if configured:
        check_foundry(report, settings)
        check_webapp(report, settings)
    if args.hero and not args.comprehensive and not report.failures:
        check_hero(report)
    if args.comprehensive and not report.failures:
        check_comprehensive(report)

    print(f"\nCompleted in {time.monotonic() - started:.0f}s with {len(report.failures)} failure(s) "
          f"and {len(report.warnings)} warning(s).")
    if report.failures:
        print("\nDEMO NOT READY\n\nNeeds attention:")
        for number, check in enumerate(report.failures, 1):
            print(f"  {number}. [{check.section}] {check.name}: {check.detail}")
            if check.fix:
                print(f"     Fix: {check.fix}")
        print("\nSee demo/troubleshooting.md for quick recovery steps.")
        return 1
    print("\nDEMO READY")
    if not (args.hero or args.comprehensive):
        print("(Quick checks only. Add --hero for one live hero turn before presenting.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
