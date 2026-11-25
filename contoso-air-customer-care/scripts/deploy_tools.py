"""Deploy the Contoso Air Operations API (mock tools service) to Azure Container Apps.

Foundry calls OpenAPI tools from the cloud, so the tools API needs a public HTTPS
endpoint. This script:

1. Stages a Docker build context (tools/ + data/*.json) in .deploy/tools.
2. Creates the resource group if needed.
3. Runs ``az containerapp up --source`` (the image is built in Azure Container
   Registry, so Docker is not required locally).
4. Keeps one replica warm, and sets TOOLS_API_PUBLIC_URL so the served OpenAPI
   specs advertise the https URL.
5. Smoke-tests /health and the hero reservation, then prints the base URL.

Usage (PowerShell or bash):
    python scripts/deploy_tools.py --resource-group <rg> --location westus3
    python scripts/deploy_tools.py --update-env        # also writes TOOLS_API_BASE_URL to .env
    python scripts/deploy_tools.py --stage-only .deploy/tools

Values default to AZURE_RESOURCE_GROUP, AZURE_LOCATION and TOOLS_CONTAINER_APP_NAME in .env.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
DATA_DIR = REPO_ROOT / "data"
DEFAULT_STAGE_DIR = REPO_ROOT / ".deploy" / "tools"
ENV_FILE = REPO_ROOT / ".env"
HERO_CUSTOMER = "CUST-1007"
HERO_RESERVATION = "CT8K2P"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is in requirements.txt
        return
    load_dotenv(ENV_FILE)


def stage(target: Path) -> Path:
    """Create a self-contained Docker build context for the tools service."""
    target = target.resolve()
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(TOOLS_DIR, target, ignore=IGNORE)
    data_target = target / "data"
    data_target.mkdir(parents=True, exist_ok=True)
    data_files = sorted(DATA_DIR.glob("*.json"))
    if not data_files:
        raise SystemExit("No synthetic data found. Run: python data/generate_data.py")
    for path in data_files:
        shutil.copy2(path, data_target / path.name)
    return target


def find_az() -> str:
    az = shutil.which("az") or shutil.which("az.cmd")
    if not az:
        raise SystemExit("Azure CLI (az) not found. Install it and run 'az login' first.")
    return az


def run_az(az: str, *args: str, capture: bool = False) -> str:
    cmd = [az, *args]
    print(f"> az {' '.join(args)}", flush=True)
    # The Azure CLI on Windows crashes on non-cp1252 characters in streamed ACR build logs.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    result = subprocess.run(cmd, text=True, capture_output=capture, env=env, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        if capture:
            sys.stderr.write(result.stderr or "")
        raise SystemExit(f"Azure CLI command failed (exit {result.returncode}).")
    return (result.stdout or "").strip() if capture else ""


def ensure_prerequisites(az: str) -> None:
    run_az(az, "account", "show", "--query", "name", "-o", "tsv", capture=True)
    run_az(az, "extension", "add", "--name", "containerapp", "--upgrade", "--only-show-errors")
    for namespace in ("Microsoft.App", "Microsoft.OperationalInsights", "Microsoft.ContainerRegistry"):
        state = run_az(az, "provider", "show", "-n", namespace, "--query", "registrationState", "-o", "tsv", capture=True)
        if state != "Registered":
            run_az(az, "provider", "register", "-n", namespace, "--wait")


def ensure_resource_group(az: str, name: str, location: str) -> None:
    exists = run_az(az, "group", "exists", "-n", name, capture=True)
    if exists.lower() != "true":
        run_az(az, "group", "create", "-n", name, "-l", location, "--tags", "project=contoso-air-customer-care", "-o", "none")


def wait_for_latest_revision(az: str, name: str, resource_group: str, timeout: int = 300) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        names = run_az(az, "containerapp", "show", "-n", name, "-g", resource_group, "--query",
                       "[properties.latestRevisionName, properties.latestReadyRevisionName]", "-o", "tsv", capture=True).split()
        if len(names) == 2 and names[0] == names[1]:
            print(f"Revision {names[0]} is ready.")
            return
        time.sleep(10)
    raise SystemExit("Timed out waiting for the latest Container App revision to become ready.")


def http_get_json(url: str, timeout: float = 20.0) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        try:
            return err.code, json.loads(body)
        except json.JSONDecodeError:
            return err.code, {"raw": body}


def smoke_test(base_url: str, attempts: int = 12) -> None:
    for attempt in range(1, attempts + 1):
        try:
            status, body = http_get_json(f"{base_url}/health")
            if status == 200:
                print(f"Health OK: currentDate={body.get('currentDate')} flights={body.get('flights')}")
                break
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            print(f"  waiting for the app ({attempt}/{attempts}): {err}")
        time.sleep(10)
    else:
        raise SystemExit(f"The tools API at {base_url} did not become healthy.")

    status, body = http_get_json(f"{base_url}/customers/{HERO_CUSTOMER}/reservations")
    codes = [r.get("confirmationCode") for r in body.get("reservations", [])] if status == 200 else []
    if HERO_RESERVATION not in codes:
        raise SystemExit(f"Smoke test failed: expected {HERO_RESERVATION} for {HERO_CUSTOMER}, got HTTP {status}: {body}")
    status, spec = http_get_json(f"{base_url}/openapi.json")
    served = (spec.get("servers") or [{}])[0].get("url", "")
    if status != 200 or not served.startswith("https://"):
        raise SystemExit(f"OpenAPI spec should advertise an https server URL, got HTTP {status}: {served!r}")
    print(f"Smoke test OK: {HERO_CUSTOMER} -> {HERO_RESERVATION}; spec advertises {served}")


def update_env_file(base_url: str) -> None:
    if not ENV_FILE.exists():
        example = REPO_ROOT / ".env.example"
        ENV_FILE.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    text = ENV_FILE.read_text(encoding="utf-8")
    line = f"TOOLS_API_BASE_URL={base_url}"
    if re.search(r"^TOOLS_API_BASE_URL=.*$", text, flags=re.MULTILINE):
        text = re.sub(r"^TOOLS_API_BASE_URL=.*$", line, text, flags=re.MULTILINE)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    ENV_FILE.write_text(text, encoding="utf-8")
    print(f"Updated {ENV_FILE.name}: {line}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resource-group", default=None, help="Resource group (default: AZURE_RESOURCE_GROUP).")
    parser.add_argument("--location", default=None, help="Azure region (default: AZURE_LOCATION or westus3).")
    parser.add_argument("--name", default=None, help="Container App name (default: TOOLS_CONTAINER_APP_NAME).")
    parser.add_argument("--stage-only", nargs="?", const=str(DEFAULT_STAGE_DIR), default=None, metavar="DIR",
                        help="Only create the Docker build context (default .deploy/tools) and exit.")
    parser.add_argument("--update-env", action="store_true", help="Write TOOLS_API_BASE_URL to .env after deploying.")
    parser.add_argument("--skip-smoke-test", action="store_true", help="Do not call the deployed API.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_env()
    args = parse_args(argv)

    if args.stage_only:
        target = stage(Path(args.stage_only))
        print(f"Staged build context: {target}")
        return 0

    resource_group = args.resource_group or os.environ.get("AZURE_RESOURCE_GROUP", "").strip()
    location = args.location or os.environ.get("AZURE_LOCATION", "").strip() or "westus3"
    name = args.name or os.environ.get("TOOLS_CONTAINER_APP_NAME", "").strip() or "contoso-air-tools"
    if not resource_group:
        raise SystemExit("Set --resource-group or AZURE_RESOURCE_GROUP in .env.")

    az = find_az()
    ensure_prerequisites(az)
    ensure_resource_group(az, resource_group, location)
    source = stage(DEFAULT_STAGE_DIR)

    env_vars = [f"DEMO_TIMEZONE={os.environ.get('DEMO_TIMEZONE', '').strip() or 'America/Los_Angeles'}"]
    for pinned in ("DEMO_TODAY", "DEMO_TIME"):
        if os.environ.get(pinned, "").strip():
            env_vars.append(f"{pinned}={os.environ[pinned].strip()}")

    run_az(az, "containerapp", "up", "--name", name, "--resource-group", resource_group, "--location", location,
           "--source", str(source), "--ingress", "external", "--target-port", "8000",
           "--env-vars", *env_vars)

    fqdn = run_az(az, "containerapp", "show", "-n", name, "-g", resource_group,
                  "--query", "properties.configuration.ingress.fqdn", "-o", "tsv", capture=True)
    if not fqdn:
        raise SystemExit("Could not read the Container App FQDN.")
    base_url = f"https://{fqdn}"

    run_az(az, "containerapp", "update", "-n", name, "-g", resource_group, "--min-replicas", "1", "--max-replicas", "2",
           "--set-env-vars", f"TOOLS_API_PUBLIC_URL={base_url}", "--only-show-errors", "-o", "none")
    wait_for_latest_revision(az, name, resource_group)

    if not args.skip_smoke_test:
        smoke_test(base_url)
    if args.update_env:
        update_env_file(base_url)

    print("\nTools API deployed.")
    print(f"  TOOLS_API_BASE_URL={base_url}")
    print(f"  OpenAPI spec for the Foundry UI: {base_url}/openapi.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
