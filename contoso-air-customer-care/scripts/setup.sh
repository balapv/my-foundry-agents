#!/usr/bin/env bash
# Prepare this machine to present the Contoso Air Customer Care demo, then check that it is ready.
#
# Stages (stops with an actionable message at the first stage that cannot continue):
#   1. Local prerequisites        Python 3.10+, Azure CLI, .venv, packages from requirements.txt
#   2. Environment configuration  .env present and required settings filled in (values are never printed)
#   3. Azure / Foundry            Azure CLI sign-in
#   4. Validation                 python scripts/validate_demo.py: data, knowledge PDFs, Operations API,
#                                 Foundry project, agent and active version, knowledge, web app
#
# Setup never creates, updates or deletes the Foundry agent, its versions, the vector store or any
# Azure resource.
#
# Usage (from anywhere):
#   ./scripts/setup.sh                    # full setup
#   ./scripts/setup.sh --skip-install     # skip pip install
#   ./scripts/setup.sh --hero             # also run one live hero turn (one model call)
set -u

cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
SKIP_INSTALL=0
HERO=0
for arg in "$@"; do
  case "$arg" in
    --skip-install) SKIP_INSTALL=1 ;;
    --hero) HERO=1 ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

REQUIRED="FOUNDRY_PROJECT_ENDPOINT FOUNDRY_MODEL_DEPLOYMENT_NAME FOUNDRY_AGENT_NAME TOOLS_API_BASE_URL"
PROBLEMS=0
pass() { printf '  [PASS] %s\n' "$1"; }
warn() { printf '  [WARN] %s\n' "$1"; [ -n "${2:-}" ] && printf '         -> %s\n' "$2"; return 0; }
fail() { printf '  [FAIL] %s\n' "$1"; [ -n "${2:-}" ] && printf '         -> %s\n' "$2"; PROBLEMS=$((PROBLEMS + 1)); return 0; }
stop_setup() { printf '\nSETUP INCOMPLETE: fix the %s items above, then run ./scripts/setup.sh again.\n' "$1"; exit 1; }
py_version() { "$@" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null; }
is_supported() { "$@" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; }

echo "Contoso Air Customer Care - demo setup"

# --------------------------------------------------------------------------- 1. local prerequisites
printf '\n1. Local prerequisites\n'
VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  BASE_PY=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && is_supported "$candidate"; then BASE_PY="$candidate"; break; fi
  done
  if [ -z "$BASE_PY" ]; then
    fail "Python 3.10 or later was not found." "Install it from https://www.python.org/downloads/ or your package manager."
    stop_setup "local prerequisite"
  fi
  echo "  Creating .venv with $BASE_PY..."
  if ! "$BASE_PY" -m venv .venv || [ ! -x "$VENV_PY" ]; then
    fail "Could not create the .venv virtual environment." "On Debian/Ubuntu install python3-venv, then run setup again."
    stop_setup "local prerequisite"
  fi
fi
if is_supported "$VENV_PY"; then
  pass "Python $(py_version "$VENV_PY") in .venv"
else
  fail "The .venv Python is older than 3.10." "Delete the .venv folder and run setup again."
  stop_setup "local prerequisite"
fi

if [ "$SKIP_INSTALL" -eq 1 ]; then
  warn "Skipped installing Python packages (--skip-install)."
else
  echo "  Installing Python packages from requirements.txt..."
  if "$VENV_PY" -m pip install --disable-pip-version-check --quiet -r requirements.txt; then
    pass "Python packages installed"
  else
    fail "pip install failed." "Run: .venv/bin/python -m pip install -r requirements.txt and read the error."
  fi
fi

if command -v az >/dev/null 2>&1; then pass "Azure CLI installed"
else fail "Azure CLI (az) was not found." "Install it: https://learn.microsoft.com/cli/azure/install-azure-cli"; fi

if command -v node >/dev/null 2>&1; then pass "Node.js installed (optional; used by one frontend syntax test)"
else warn "Node.js not found (optional; one frontend syntax test is skipped)."; fi

[ "$PROBLEMS" -gt 0 ] && stop_setup "local prerequisite"

# --------------------------------------------------------------------------- 2. environment configuration
printf '\n2. Environment configuration\n'
if [ ! -f .env ]; then
  cp .env.example .env
  fail "No .env file. Created one from .env.example." "Open .env and fill in the values for YOUR environment (see README \"Prerequisites\")."
  stop_setup "environment configuration"
fi
pass ".env present (git-ignored)"

env_value() {
  local name="$1" value
  value="$(printenv "$name" 2>/dev/null || true)"
  if [ -z "$value" ]; then
    value="$(grep -E "^[[:space:]]*${name}[[:space:]]*=" .env | tail -n 1 | cut -d= -f2- | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//')"
  fi
  printf '%s' "$value"
}
MISSING=""
for name in $REQUIRED; do
  [ -z "$(env_value "$name")" ] && MISSING="$MISSING $name"
done
if [ -n "$MISSING" ]; then
  fail "Not set in .env:$MISSING" "Fill them in .env. TOOLS_API_BASE_URL comes from scripts/deploy_tools.py (README \"Deploy the Operations API\")."
  stop_setup "environment configuration"
fi
pass "Required settings set: $REQUIRED (values not shown)"
TOOLS_URL="$(env_value TOOLS_API_BASE_URL)"
case "$TOOLS_URL" in
  https://localhost*|https://127.0.0.1*|http://*)
    fail "TOOLS_API_BASE_URL must be a public https:// URL; Foundry calls the tools from the cloud." \
         "Deploy with: python scripts/deploy_tools.py --resource-group <rg> --update-env"
    stop_setup "environment configuration" ;;
esac

# --------------------------------------------------------------------------- 3. Azure / Foundry prerequisites
printf '\n3. Azure / Foundry prerequisites\n'
if ! SUBSCRIPTION="$(az account show --query name -o tsv 2>/dev/null)" || [ -z "$SUBSCRIPTION" ]; then
  fail "Azure CLI is not signed in." "Run: az login   (then, if needed: az account set --subscription <subscription name>)"
  stop_setup "Azure sign-in"
fi
pass "Azure CLI signed in (subscription: $SUBSCRIPTION)"
echo "  The Foundry project, agent and version are checked in the next stage."

# --------------------------------------------------------------------------- 4. validation
printf '\n4. Validation (python scripts/validate_demo.py)\n'
if [ "$HERO" -eq 1 ]; then "$VENV_PY" scripts/validate_demo.py --hero; else "$VENV_PY" scripts/validate_demo.py; fi
CODE=$?
if [ "$CODE" -eq 0 ]; then
  printf '\nSETUP COMPLETE. Start the web app with:\n'
  echo "  .venv/bin/python -m uvicorn server:app --app-dir webapp/backend --port 8080"
fi
exit "$CODE"
