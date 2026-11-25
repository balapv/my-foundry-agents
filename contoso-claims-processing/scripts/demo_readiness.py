"""Presentation-readiness checks for the Contoso Claims Processing demo.

Used by scripts/validate_demo.py (the one readiness command), scripts/reset_demo.py and the setup
scripts. Every check is read-only: nothing here creates, updates or deletes an agent, vector store,
file or Azure resource, and no check prints endpoint URLs, IDs or other .env values.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = ROOT / "demo" / "baseline.json"
for path in (ROOT, ROOT / "agent"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import common  # noqa: E402  (agent/common.py)

MIN_PYTHON = (3, 12)
MIN_NODE = 20
REQUIRED_PACKAGES = ("fastapi", "uvicorn", "dotenv", "pypdf", "azure.ai.projects", "azure.identity", "openai")
REQUIRED_SETTINGS = ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL_DEPLOYMENT_NAME", "TOOLS_API_BASE_URL")
PRIVATE_PATHS = (".env", ".foundry-state.json", "agent/config.json", ".deploy/", "evaluation/results/", "webapp/.logs/")
FOUNDRY_SCOPE = "https://ai.azure.com/.default"


@dataclass
class Check:
    group: str
    name: str
    ok: bool | None  # None = skipped
    detail: str = ""
    fix: str = ""


def baseline() -> dict[str, Any]:
    return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def _run(argv: list[str], timeout: float = 30) -> tuple[int, str]:
    try:
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 1, type(exc).__name__
    return result.returncode, (result.stdout + result.stderr).strip()


def _guard(group: str, name: str, fix: str, func: Callable[[], Check]) -> Check:
    try:
        return func()
    except Exception as exc:  # report and continue: a readiness run must always reach the verdict
        return Check(group, name, False, f"{type(exc).__name__}: {str(exc)[:160]}", fix)


# ---------------------------------------------------------------------------
# Local environment and configuration
# ---------------------------------------------------------------------------


def local_environment() -> list[Check]:
    group = "environment"
    checks = [Check(group, "Python", sys.version_info[:2] >= MIN_PYTHON, f"{sys.version.split()[0]}",
                    f"Install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ and run scripts/setup.ps1 (or setup.sh).")]
    in_venv = sys.prefix != sys.base_prefix
    checks.append(Check(group, "virtual environment", in_venv, "active" if in_venv else "not a virtual environment",
                        "Run with .venv\\Scripts\\python.exe (Windows) or .venv/bin/python; create it with scripts/setup.ps1."))
    missing = [name for name in REQUIRED_PACKAGES if importlib.util.find_spec(name) is None]
    checks.append(Check(group, "Python dependencies", not missing, "installed" if not missing else f"missing {missing}",
                        "pip install -r requirements.txt"))
    node = shutil.which("node")
    version = _run([node, "--version"])[1] if node else ""
    major = int(m.group(1)) if (m := re.match(r"v(\d+)", version)) else 0
    checks.append(Check(group, "Node.js (frontend tests)", major >= MIN_NODE, version or "not found",
                        f"Install Node.js {MIN_NODE}+; it is used only for the frontend unit tests."))
    return checks


def configuration() -> list[Check]:
    group = "configuration"
    load_env()
    base = baseline()
    checks = []
    env_file = (ROOT / ".env").is_file()
    checks.append(Check(group, ".env present", env_file, "found" if env_file else "missing",
                        "Copy .env.example to .env and fill in the Foundry project and Claims Operations API values."))
    missing = [name for name in REQUIRED_SETTINGS if not os.environ.get(name, "").strip()]
    checks.append(Check(group, "required settings", not missing, "set (values not shown)" if not missing else f"missing {missing}",
                        "Set the missing values in .env (see .env.example)."))
    tools_url = os.environ.get("TOOLS_API_BASE_URL", "")
    if tools_url:
        checks.append(Check(group, "TOOLS_API_BASE_URL is https", tools_url.startswith("https://"), "",
                            "Foundry calls the API from the cloud; use the deployed https URL (scripts/deploy_tools.py --update-env)."))
    name = os.environ.get("FOUNDRY_AGENT_NAME", "").strip() or common.load_config()["agentName"]
    checks.append(Check(group, "agent name", name == base["agentName"], name,
                        f"Clear FOUNDRY_AGENT_NAME in .env or set it to {base['agentName']}."))
    state = common.load_state()
    record = state.get("agents", {}).get(base["agentName"], {})
    configured = os.environ.get("FOUNDRY_AGENT_VERSION", "").strip() or record.get("version")
    source = "FOUNDRY_AGENT_VERSION" if os.environ.get("FOUNDRY_AGENT_VERSION", "").strip() else ".foundry-state.json"
    checks.append(Check(group, "configured agent version", configured == base["agentVersion"],
                        f"v{configured} (from {source})" if configured else "not configured",
                        f"Set FOUNDRY_AGENT_VERSION={base['agentVersion']} in .env. Do not create a new agent version for the demo."))
    store = state.get("vectorStores", {}).get(base["knowledgeVectorStoreName"], {})
    checks.append(Check(group, "deployment state", bool(record and store.get("id")),
                        ".foundry-state.json records the agent and vector store" if record and store.get("id") else
                        ".foundry-state.json has no agent/vector store record",
                        "Restore .foundry-state.json from the machine that created the agent, or see docs for agent/create_agent.py."))
    return checks


def private_files() -> list[Check]:
    group = "repository"
    not_ignored = [p for p in PRIVATE_PATHS
                   if _run(["git", "check-ignore", "-q", "--no-index", p + ("probe" if p.endswith("/") else "")])[0] != 0]
    tracked = _run(["git", "ls-files", "--", *PRIVATE_PATHS])[1].split()
    return [Check(group, "private/runtime files ignored", not not_ignored and not tracked,
                  "ignored and untracked" if not not_ignored and not tracked else f"not ignored {not_ignored}, tracked {tracked}",
                  "Restore .gitignore; git rm --cached any tracked private file.")]


def frozen_baseline() -> list[Check]:
    group = "baseline"
    base = baseline()
    changed = [name for name, digest in base["sha256"].items()
               if not (ROOT / name).is_file() or common.sha256((ROOT / name).read_bytes()) != digest]
    checks = [Check(group, "validated files unchanged", not changed,
                    f"{len(base['sha256'])} files match" if not changed else f"changed: {changed}",
                    "Do not present with modified evidence, instructions, guidance or OpenAPI; restore them with "
                    "git checkout (claims-processing-v1) and use the fallback assets until fixed.")]

    def evidence() -> Check:
        _, items = common.claim_evidence(base["heroClaimId"])
        ok = len(items) == base["heroEvidenceCount"]
        return Check(group, f"{base['heroClaimId']} evidence hashes", ok, f"{len(items)} items verified",
                     "Restore evidence/ from the tag; never rebuild it just before presenting.")

    checks.append(_guard(group, f"{base['heroClaimId']} evidence hashes",
                         "Restore evidence/ from the tag; never rebuild it just before presenting.", evidence))
    return checks


def documentation() -> list[Check]:
    group = "demo files"
    base = baseline()
    missing_docs = [p for p in base["demoDocuments"] if not (ROOT / p).is_file() or (ROOT / p).stat().st_size < 200]
    checks = [Check(group, "presenter documents", not missing_docs,
                    f"{len(base['demoDocuments'])} present" if not missing_docs else f"missing {missing_docs}",
                    "Restore demo/ from the claims-processing-v1 tag.")]
    bad = []
    for name in base["fallbackAssets"]:
        path = ROOT / name
        if not path.is_file():
            bad.append(name)
            continue
        head = path.read_bytes()[:256]
        if (path.suffix == ".png" and not head.startswith(b"\x89PNG")) or (path.suffix == ".svg" and b"<svg" not in head + path.read_bytes()[:2048]):
            bad.append(name)
    checks.append(Check(group, "fallback assets", not bad,
                        f"{len(base['fallbackAssets'])} present" if not bad else f"missing/invalid {bad}",
                        "Restore demo/assets/ from the claims-processing-v1 tag."))
    transcript = ROOT / "demo" / "fallback-transcript.md"
    labelled = transcript.is_file() and "validated previous run" in transcript.read_text(encoding="utf-8").lower()
    checks.append(Check(group, "fallback transcript labelled", labelled, "labelled as a validated previous run" if labelled else "",
                        "The transcript must say it is a validated previous run, not a live result."))
    return checks


# ---------------------------------------------------------------------------
# Claims Review application (in-process; no browser, no model call)
# ---------------------------------------------------------------------------


def application(use_deployed_api: bool) -> list[Check]:
    group = "application"
    base = baseline()
    fix = "Run the webapp tests (pytest tests/test_webapp.py) and see demo/troubleshooting.md."

    def run() -> list[Check]:
        from fastapi.testclient import TestClient

        from webapp.backend.app import create_app
        from webapp.backend.config import load_settings

        load_env()
        settings = load_settings()
        if not use_deployed_api:
            settings = dataclasses.replace(settings, claims_api_base_url=None)
        client = TestClient(create_app(settings))
        checks = []
        index = client.get("/")
        assets = re.findall(r'(?:src|href)="/ui/([^"]+)"', index.text)
        asset_status = {a: client.get(f"/ui/{a}").status_code for a in assets}
        ok = index.status_code == 200 and assets and all(s == 200 for s in asset_status.values())
        checks.append(Check(group, "frontend assets", bool(ok), f"index + {len(assets)} assets served", fix))
        about = client.get("/api/about").json()
        checks.append(Check(group, "application agent version", about.get("agentVersion") == base["agentVersion"],
                            f"{about.get('agentName')} v{about.get('agentVersion')}",
                            f"Set FOUNDRY_AGENT_VERSION={base['agentVersion']} in .env."))
        workspace = client.get(f"/api/claims/{base['heroClaimId']}")
        body = workspace.json() if workspace.status_code == 200 else {}
        summary = body.get("summary") or {}
        facts_ok = (summary.get("policyholder") == "Jordan Lee" and summary.get("estimateTotal") == 7850
                    and summary.get("collisionDeductible") == 1000 and body.get("recordsAvailable") is True)
        source = "deployed Claims Operations API" if settings.claims_api_base_url else "in-process Claims Operations API"
        checks.append(Check(group, f"{base['heroClaimId']} workspace facts", facts_ok,
                            f"{summary.get('policyholder')}, {summary.get('claimStatus')}, estimate {summary.get('estimateTotal')}, "
                            f"deductible {summary.get('collisionDeductible')} via {source}",
                            "Check the Claims Operations API (see Claims Operations API checks) and demo/troubleshooting.md."))
        evidence = body.get("evidence") or []
        served = [client.get(item["url"]) for item in evidence]
        manifest, items = common.claim_evidence(base["heroClaimId"])
        expected = {entry["documentId"]: common.sha256(content) for entry, content in items}
        matches = [item["documentId"] for item, r in zip(evidence, served)
                   if r.status_code == 200 and common.sha256(r.content) == expected.get(item["documentId"])]
        checks.append(Check(group, "evidence served", len(matches) == base["heroEvidenceCount"] == len(evidence),
                            f"{len(matches)}/{len(evidence)} evidence items served intact "
                            f"({sum(i['kind'] == 'pdf' for i in evidence)} PDFs, {sum(i['kind'] == 'photo' for i in evidence)} photos)", fix))
        guidance = body.get("guidance") or []
        ok = len(guidance) == 4 and all(client.get(g["url"]).content.startswith(b"%PDF") for g in guidance)
        checks.append(Check(group, "guidance PDFs served", ok, f"{len(guidance)} guidance PDFs",
                            "Run python knowledge/build_pdfs.py --check."))
        return checks

    try:
        return run()
    except Exception as exc:
        return [Check(group, "application", False, f"{type(exc).__name__}: {str(exc)[:160]}", fix)]


# ---------------------------------------------------------------------------
# Azure, Foundry and the deployed Claims Operations API (read-only)
# ---------------------------------------------------------------------------


# Requests used for the live API check: one existing record per operation, plus one unknown ID.
LIVE_REQUESTS = [
    ("/claims/{claimId}", "/claims/CLM-10482", None),
    ("/policies/{policyId}", "/policies/PAP-4471920", None),
    ("/customers/{customerId}/claim-history", "/customers/CUST-24817/claim-history", None),
    ("/vehicles/{vehicleId}", "/vehicles/VEH-58213", None),
    ("/claims/{claimId}", "/claims/CLM-99999", "CLAIM_NOT_FOUND"),
]


def live_check(base_url: str, quiet: bool = False) -> list[str]:
    """Call each operation of a running Claims Operations API and validate it against tools/openapi.json."""
    sys.path.insert(0, str(ROOT / "tests"))
    from openapi_validation import response_schema, validate

    spec = json.loads(common.OPENAPI_FILE.read_text(encoding="utf-8"))
    problems = []
    for template, path, expected_error in LIVE_REQUESTS:
        try:
            status, body = _http_json(base_url.rstrip("/") + path)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            problems.append(f"GET {path}: {exc}")
            continue
        if status != 200 or body is None:
            problems.append(f"GET {path}: HTTP {status}")
            continue
        errors = validate(body, response_schema(spec, template))
        if errors:
            problems.append(f"GET {path}: {errors[0]}")
        error_code = (body.get("error") or {}).get("code")
        if error_code != expected_error:
            problems.append(f"GET {path}: expected error {expected_error}, got {error_code}")
        if not quiet:
            print(f"  GET {path} -> {error_code or 'ok'}")
    try:
        status, served = _http_json(base_url.rstrip("/") + "/openapi.json")
        if (served or {}).get("paths") != spec["paths"]:
            problems.append("/openapi.json paths differ from tools/openapi.json")
        if not quiet:
            print(f"  GET /openapi.json -> servers {(served or {}).get('servers')}")
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        problems.append(f"GET /openapi.json: {exc}")
    return problems


def _http_json(url: str, timeout: float = 15) -> tuple[int, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, None


def claims_api() -> list[Check]:
    group = "Claims Operations API"
    load_env()
    url = os.environ.get("TOOLS_API_BASE_URL", "").rstrip("/")
    if not url:
        return [Check(group, "health", False, "TOOLS_API_BASE_URL not set", "Set TOOLS_API_BASE_URL in .env.")]
    fix = ("Open <TOOLS_API_BASE_URL>/health in a browser. If it is down, check the Container App in the Azure portal "
           "(min replicas 1) or redeploy with python scripts/deploy_tools.py. See demo/troubleshooting.md.")

    def health() -> Check:
        status, body = _http_json(f"{url}/health")
        return Check(group, "health", status == 200, f"HTTP {status}, {(body or {}).get('claims')} claims", fix)

    def operations() -> Check:
        problems = live_check(url, quiet=True)
        return Check(group, "operations match OpenAPI", not problems,
                     "4 operations + not-found behaviour" if not problems else "; ".join(problems)[:200],
                     fix + " If SERVICE_UNAVAILABLE is returned, clear the simulated outage: "
                           "python scripts/deploy_tools.py --set-outage \"\"")

    return [_guard(group, "health", fix, health), _guard(group, "operations match OpenAPI", fix, operations)]


def foundry() -> list[Check]:
    group = "Foundry"
    load_env()
    base = baseline()
    checks: list[Check] = []
    auth_fix = "Run az login (and az account set --subscription <the Foundry project's subscription>), then retry."

    def credential() -> Check:
        from azure.identity import DefaultAzureCredential

        DefaultAzureCredential(exclude_interactive_browser_credential=True).get_token(FOUNDRY_SCOPE)
        return Check(group, "Azure sign-in", True, "token acquired", auth_fix)

    checks.append(_guard(group, "Azure sign-in", auth_fix, credential))
    if not checks[-1].ok:
        return checks + [Check(group, "agent and knowledge", None, "skipped: not signed in")]
    if not os.environ.get("FOUNDRY_PROJECT_ENDPOINT"):
        return checks + [Check(group, "project", False, "FOUNDRY_PROJECT_ENDPOINT not set", "Set it in .env.")]

    project = common.project_client({"FOUNDRY_PROJECT_ENDPOINT": os.environ["FOUNDRY_PROJECT_ENDPOINT"]})
    version_fix = (f"Confirm {base['agentName']} version {base['agentVersion']} in the Foundry portal (Agents > "
                   f"{base['agentName']} > Versions) and set FOUNDRY_AGENT_VERSION={base['agentVersion']}. Do not publish a new version.")
    found: dict[str, Any] = {}

    def agent_version() -> Check:
        version = project.agents.get_version(agent_name=base["agentName"], agent_version=base["agentVersion"])
        found.update(version.as_dict())
        return Check(group, "agent version available", True, f"{base['agentName']} v{found.get('version')}", version_fix)

    checks.append(_guard(group, "project connectivity / agent version",
                         "Check FOUNDRY_PROJECT_ENDPOINT, your sign-in and Azure AI User access on the project. " + version_fix,
                         agent_version))
    if not found:
        return checks
    definition = found.get("definition") or {}
    checks.append(Check(group, "model", definition.get("model") == base["model"], str(definition.get("model")), version_fix))
    instructions_ok = common.sha256((definition.get("instructions") or "").encode("utf-8")) == base["sha256"]["agent/instructions.md"]
    checks.append(Check(group, "instructions match baseline", instructions_ok, "match" if instructions_ok else "differ", version_fix))
    tools = definition.get("tools") or []
    state_store = common.load_state().get("vectorStores", {}).get(base["knowledgeVectorStoreName"], {}).get("id")
    file_search = next((t for t in tools if t.get("type") == "file_search"), {})
    checks.append(Check(group, "File Search tool", bool(state_store) and state_store in (file_search.get("vector_store_ids") or []),
                        "bound to the recorded guidance vector store" if file_search else "missing", version_fix))
    openapi = next((t.get("openapi") for t in tools if t.get("type") == "openapi"), {}) or {}
    spec = openapi.get("spec") or {}
    local = json.loads(common.OPENAPI_FILE.read_text(encoding="utf-8"))
    server = ((spec.get("servers") or [{}])[0].get("url") or "").rstrip("/")
    tools_url = os.environ.get("TOOLS_API_BASE_URL", "").rstrip("/")
    ok = openapi.get("name") == base["openApiToolName"] and spec.get("paths") == local["paths"] and server == tools_url
    checks.append(Check(group, "OpenAPI tool", ok,
                        f"{openapi.get('name')}: {len(spec.get('paths') or {})} paths, server "
                        f"{'matches TOOLS_API_BASE_URL' if server == tools_url else 'differs from TOOLS_API_BASE_URL'}",
                        "TOOLS_API_BASE_URL in .env must be the URL the validated agent version calls. " + version_fix))

    def latest() -> Check:
        latest_version = str(project.agents.get(agent_name=base["agentName"]).versions["latest"].version)
        note = "latest" if latest_version == base["agentVersion"] else f"latest is v{latest_version}; the app pins v{base['agentVersion']}"
        return Check(group, "latest version", True, note)

    checks.append(_guard(group, "latest version", version_fix, latest))

    def vector_store() -> Check:
        store = project.get_openai_client().vector_stores.retrieve(state_store)
        counts = store.file_counts
        ok = store.status == "completed" and counts.completed == len(common.KNOWLEDGE_FILES) and counts.failed == 0
        return Check(group, "guidance vector store", ok, f"{store.status}, {counts.completed}/{counts.total} files indexed",
                     "Do not recreate it before presenting; use the fallback and repair afterwards with agent/create_agent.py.")

    checks.append(_guard(group, "guidance vector store", "Check the vector store in the Foundry portal (Data > Vector stores).",
                         vector_store))
    return checks
