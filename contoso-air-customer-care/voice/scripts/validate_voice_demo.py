"""Is the Contoso Air voice demo (Demo 1B) ready to present right now?

Runs a focused, read-only set of checks and ends with VOICE DEMO READY or VOICE DEMO NOT READY:

    1. Local prerequisites   Python, packages, voice demo files, Demo 1A fallback files
    2. Configuration         .env settings (values never printed), voice configuration as validated
    3. Data and knowledge    shared synthetic data and policy PDFs (same checks as Demo 1A)
    4. Operations API        /health, the demo customer's reservation, the cancelled flight
    5. Foundry voice agent   sign-in, agent and configured version exist, model/voice/barge-in settings,
                             portal-playground identity default, toolbox (Operations API + File Search),
                             shared policy vector store indexed

It never creates, updates or deletes agents, versions, toolboxes, vector stores or data. The default run
makes no model or voice-session calls. --live adds ONE scripted V2-hero voice call (about 2 minutes).

Usage (from contoso-air-customer-care/):

    python voice/scripts/validate_voice_demo.py           # quick checks, about 15-30 s
    python voice/scripts/validate_voice_demo.py --live    # ...plus one scripted hero voice call

Exits with code 1 when the voice demo is not ready.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

VOICE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = VOICE_DIR.parent
for path in (REPO_ROOT, VOICE_DIR / "agent"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent.foundry_common import as_dict, configure_console, get_settings, validate_tools_url  # noqa: E402
from scripts.validate_demo import (  # noqa: E402  (Demo 1A readiness helpers, reused read-only)
    Report,
    check_data_and_knowledge,
    check_knowledge,
    check_operations_api,
    describe_error,
    is_installed,
)
from voice_common import (  # noqa: E402
    load_voice_config,
    load_voice_instructions,
    resolve_voice_agent_version,
    voice_settings,
)

MIN_PYTHON = (3, 10)
REQUIRED_PACKAGES = ("azure.ai.projects", "azure.identity", "httpx", "dotenv")
LIVE_PACKAGES = ("websockets", "azure.cognitiveservices.speech")
EXPECTED_OPERATIONS = ["get_customer_reservations", "get_flight_status", "search_alternative_flights"]
# The configuration validated in Phases V2 and V3. Changing any of these needs a new validation pass.
VALIDATED_CONFIG = {
    "model": "gpt-realtime-2.1",
    "voice": "en-US-AvaNeural",
    "turnDetection": "azure_semantic_vad",
}
VOICE_DEMO_FILES = (
    "voice/README.md",
    "voice/agent/instructions.md",
    "voice/agent/create_agent.py",
    "voice/agent/run_session.py",
    "voice/evaluation/test_cases.json",
    "voice/demo/demo-script.md",
    "voice/demo/setup-checklist.md",
    "voice/demo/troubleshooting.md",
    "voice/demo/validation-record.md",
    "voice/demo/assets/voice-architecture.svg",
)
FALLBACK_FILES = (
    "demo/demo-script.md",
    "demo/fallback-transcript.md",
    "scripts/validate_demo.py",
    "webapp/frontend/index.html",
    "webapp/backend/server.py",
)
LIVE_SCENARIO = "V2-hero"


# --------------------------------------------------------------------------- 1. local


def check_local(report: Report, live: bool) -> None:
    report.start("1. Local prerequisites")
    version = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info >= MIN_PYTHON:
        report.ok("Python", version)
    else:
        report.fail("Python", f"{version} is older than 3.10", "Install Python 3.10 or later.")
    packages = REQUIRED_PACKAGES + (LIVE_PACKAGES if live else ())
    missing = [name for name in packages if not is_installed(name)]
    if missing:
        report.fail("Python packages", f"missing {', '.join(missing)}",
                    "Run: python -m pip install -r voice/requirements.txt")
    else:
        report.ok("Python packages", "installed")
    for name, files, fix in (
        ("Voice demo files", VOICE_DEMO_FILES, "Restore the missing files from the repository."),
        ("Demo 1A fallback files", FALLBACK_FILES, "Restore Demo 1A from the repository; the fallback must stay ready."),
    ):
        absent = missing_files(files)
        if absent:
            report.fail(name, f"missing {', '.join(absent)}", fix)
        else:
            report.ok(name, f"{len(files)} present")


def missing_files(files: tuple[str, ...], root: Path = REPO_ROOT) -> list[str]:
    return [path for path in files if not (root / path).exists()]


# --------------------------------------------------------------------------- 2. configuration


def config_mismatches(config: dict[str, Any], settings: dict[str, str]) -> list[str]:
    """Differences between the voice configuration in use and the validated one."""
    actual = {
        "model": settings.get("model"),
        "voice": (config.get("voice") or {}).get("name"),
        "turnDetection": (config.get("turnDetection") or {}).get("type"),
    }
    problems = [f"{key} is {actual[key]!r}, validated {expected!r}"
                for key, expected in VALIDATED_CONFIG.items() if actual[key] != expected]
    if not (config.get("turnDetection") or {}).get("interruptResponse", False):
        problems.append("turnDetection.interruptResponse is off, so the caller cannot barge in")
    return problems


def check_configuration(report: Report, config: dict[str, Any], settings: dict[str, str]) -> bool:
    report.start("2. Configuration")
    if (REPO_ROOT / ".env").exists():
        report.ok(".env", "present")
    else:
        report.warn(".env", "not found; using process environment variables only",
                    "Copy .env.example to .env and fill in your values.")
    missing = [env for env, key in (("FOUNDRY_PROJECT_ENDPOINT", "project_endpoint"),
                                    ("TOOLS_API_BASE_URL", "tools_api_base_url")) if not settings[key]]
    if missing:
        report.fail("Required settings", f"not set: {', '.join(missing)}", "Set them in .env (see .env.example).")
    else:
        report.ok("Required settings", "set (values not shown)")
    for warning in validate_tools_url(settings["tools_api_base_url"]) if settings["tools_api_base_url"] else ():
        report.fail("TOOLS_API_BASE_URL", warning)
    problems = config_mismatches(config, settings)
    if problems:
        report.fail("Voice configuration", "; ".join(problems),
                    "Present only the validated configuration (voice/agent/config.example.json).")
    else:
        report.ok("Voice configuration", f"{settings['model']}, {config['voice']['name']}, semantic VAD with barge-in")
    version, source = resolve_voice_agent_version(settings)
    if version:
        report.ok("Configured voice version", f"{version} (from {source})")
    else:
        report.warn("Configured voice version", "none configured; the agent's latest version will be used",
                    "Set FOUNDRY_VOICE_AGENT_VERSION in .env to the version you validated.")
    return not missing


# --------------------------------------------------------------------------- 5. Foundry voice agent


def definition_drift(definition: dict[str, Any]) -> list[str]:
    """Differences between a deployed voice agent definition and the validated configuration."""
    audio = definition.get("audio") or {}
    turn = (audio.get("input") or {}).get("turn_detection") or {}
    deployed = {"model": definition.get("model"), "voice": (audio.get("output") or {}).get("voice"),
                "turnDetection": turn.get("type")}
    drift = [f"{key} is {deployed[key]!r}, expected {expected!r}"
             for key, expected in VALIDATED_CONFIG.items() if deployed[key] != expected]
    if not turn.get("interrupt_response"):
        drift.append("interrupt_response is off")
    return drift


def check_definition(report: Report, definition: dict[str, Any], config: dict[str, Any]) -> None:
    """The deployed definition matches what was validated: kind, model, voice, barge-in, identity input."""
    if definition.get("kind") != "voice":
        report.fail("Agent kind", f"{definition.get('kind')}", "The demo expects a voice-based prompt agent.")
    drift = definition_drift(definition)
    if drift:
        report.fail("Voice settings", "; ".join(drift),
                    "Present the validated version (see voice/demo/foundation-notes.md).")
    else:
        report.ok("Voice settings", f"{VALIDATED_CONFIG['model']}, {VALIDATED_CONFIG['voice']}, "
                                    "semantic VAD with barge-in")
    if (definition.get("instructions") or "").strip() == load_voice_instructions(config).strip():
        report.ok("Instructions", "match voice/agent/instructions.md")
    else:
        report.warn("Instructions", "differ from voice/agent/instructions.md",
                    "Expected only if the version was edited in the portal; otherwise the agent and "
                    "repository have drifted.")
    customer = (definition.get("structured_inputs") or {}).get("customer_id") or {}
    if customer.get("default_value"):
        report.ok("Portal playground identity", "customer_id has a demo default, so the playground can connect")
    else:
        report.fail("Portal playground identity",
                    "customer_id is required with no default; the portal playground cannot connect",
                    "Present a version published with --portal-default (see voice/demo/troubleshooting.md).")


def check_toolbox(report: Report, project: Any, definition: dict[str, Any], settings: dict[str, str]) -> None:
    tools = [dict(tool) for tool in definition.get("tools") or [] if dict(tool).get("type") == "toolbox"]
    if len(tools) != 1:
        report.fail("Toolbox", f"{len(tools)} toolbox references found; expected 1", "Present the validated version.")
        return
    name, version = tools[0].get("toolbox_name"), str(tools[0].get("toolbox_version"))
    try:
        toolbox = as_dict(project.toolboxes.get_version(name, version))
    except Exception as exc:  # noqa: BLE001
        report.fail("Toolbox", f"{name} version {version} not readable ({describe_error(exc)})",
                    "Check the toolbox in the Foundry portal.")
        return
    report.ok("Toolbox", f"{name} version {version}")
    entries = [dict(tool) for tool in toolbox.get("tools") or []]
    openapi = [t for t in entries if t.get("type") == "openapi"]
    file_search = [t for t in entries if t.get("type") == "file_search"]
    if len(openapi) != 1:
        report.fail("Operations API tool", f"{len(openapi)} OpenAPI tools in the toolbox; expected 1")
    else:
        spec = dict(openapi[0].get("openapi") or {}).get("spec") or {}
        operations = sorted(op.get("operationId", "") for path in (spec.get("paths") or {}).values()
                            for op in path.values() if isinstance(op, dict))
        servers = [server.get("url", "").rstrip("/") for server in spec.get("servers") or []]
        if operations != EXPECTED_OPERATIONS:
            report.fail("Operations API tool", f"operations {operations}; expected {EXPECTED_OPERATIONS}")
        else:
            report.ok("Operations API tool", ", ".join(operations))
        if settings["tools_api_base_url"] and settings["tools_api_base_url"] not in servers:
            report.fail("Tool server URL", "the toolbox points to a different server than TOOLS_API_BASE_URL",
                        "Align TOOLS_API_BASE_URL with the deployed API (see voice/demo/troubleshooting.md).")
        else:
            report.ok("Tool server URL", "matches TOOLS_API_BASE_URL")
    check_knowledge(report, project, file_search)


def check_foundry(report: Report, config: dict[str, Any], settings: dict[str, str]) -> str | None:
    """Returns the voice agent version that was checked, for the optional live call."""
    report.start("5. Foundry voice agent")
    from azure.ai.projects import AIProjectClient
    from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ResourceNotFoundError
    from azure.identity import DefaultAzureCredential

    name = settings["agent_name"]
    try:
        with DefaultAzureCredential() as credential, \
                AIProjectClient(endpoint=settings["project_endpoint"], credential=credential) as project:
            agent = as_dict(project.agents.get(name))
            latest = ((agent.get("versions") or {}).get("latest") or {}).get("version")
            report.ok("Sign-in and project", "reachable")
            report.ok("Voice agent exists", f"{name} (latest version {latest})")
            version, source = resolve_voice_agent_version(settings)
            version = str(version or latest)
            try:
                definition = as_dict(project.agents.get_version(name, version)).get("definition") or {}
            except ResourceNotFoundError:
                report.fail("Voice agent version", f"version {version} (from {source}) does not exist",
                            "Set FOUNDRY_VOICE_AGENT_VERSION to the validated version.")
                return None
            report.ok("Voice agent version", f"{version} (from {source})")
            if latest and str(latest) != version:
                report.warn("Newer version exists", f"latest is {latest}; the demo uses {version}",
                            "The portal playground opens the latest version by default; select the demo version there.")
            check_definition(report, definition, config)
            check_toolbox(report, project, definition, settings)
            return version
    except ClientAuthenticationError as exc:
        report.fail("Sign-in", describe_error(exc), "Run: az login (and az account set --subscription <your subscription>).")
    except ResourceNotFoundError:
        report.fail("Voice agent exists", f"no agent named {name} in this project",
                    "Check FOUNDRY_PROJECT_ENDPOINT, or create it: python voice/agent/create_agent.py --portal-default")
    except HttpResponseError as exc:
        hint = "Your account needs the Foundry User role (or higher) on the project." if exc.status_code == 403 else \
            "Check FOUNDRY_PROJECT_ENDPOINT (project Overview page in the Foundry portal)."
        report.fail("Sign-in and project", f"HTTP {exc.status_code}", hint)
    except Exception as exc:  # noqa: BLE001
        report.fail("Sign-in and project", describe_error(exc), "Check network access, FOUNDRY_PROJECT_ENDPOINT and az login.")
    return None


# --------------------------------------------------------------------------- optional live call


def parse_live_verdict(output: str) -> tuple[bool, str]:
    """Reads the voice harness's '=> PASS: n/m checks, ...' result line."""
    match = re.search(r"=> (PASS|FAIL|ERROR):? ([^\n]*)", output)
    if not match:
        return False, "no result line from the voice harness"
    detail = re.sub(r"https?://\S+", "", match.group(2)).split(" Results")[0].strip().rstrip(".,;")
    return match.group(1) == "PASS", f"{match.group(1)} {detail}"


def check_live(report: Report, version: str) -> None:
    report.start(f"6. Live voice smoke call ({LIVE_SCENARIO}, version {version}; one scripted call)")
    started = time.monotonic()
    try:
        process = subprocess.run(
            [sys.executable, str(VOICE_DIR / "agent" / "run_session.py"), "--scenario", LIVE_SCENARIO,
             "--version", version],
            cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        passed, detail = parse_live_verdict(process.stdout + process.stderr)
    except subprocess.TimeoutExpired:
        passed, detail = False, "timed out"
    detail = f"{detail} ({time.monotonic() - started:.0f}s)"
    if passed:
        report.ok("Hero voice call", detail)
    else:
        report.fail("Hero voice call", detail,
                    f"Read transcript.md in the newest voice/results/*-{LIVE_SCENARIO}* folder. Wording varies between "
                    "runs; see voice/demo/troubleshooting.md before changing anything.")


# --------------------------------------------------------------------------- main


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help=f"also run one scripted {LIVE_SCENARIO} voice call")
    args = parser.parse_args()

    started = time.monotonic()
    report = Report()
    print("Contoso Air voice demo readiness check")
    check_local(report, args.live)
    config = load_voice_config()
    settings = voice_settings(config)
    configured = check_configuration(report, config, settings)
    check_data_and_knowledge(report)
    check_operations_api(report, get_settings())
    version = check_foundry(report, config, settings) if configured else None
    if args.live and version and not report.failures:
        check_live(report, version)

    print(f"\nCompleted in {time.monotonic() - started:.0f}s with {len(report.failures)} failure(s) "
          f"and {len(report.warnings)} warning(s).")
    if report.failures:
        print("\nVOICE DEMO NOT READY\n\nNeeds attention:")
        for number, check in enumerate(report.failures, 1):
            print(f"  {number}. [{check.section}] {check.name}: {check.detail}")
            if check.fix:
                print(f"     Fix: {check.fix}")
        print("\nSee voice/demo/troubleshooting.md. Check the Demo 1A fallback with: python scripts/validate_demo.py")
        return 1
    print("\nVOICE DEMO READY")
    if not args.live:
        print("(Quick checks only. Add --live for one scripted voice call, then make one spoken test call in the portal.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
