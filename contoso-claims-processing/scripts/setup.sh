#!/usr/bin/env bash
# Prepare this machine to present the Contoso Claims Processing demo (macOS/Linux).
#
# Verifies or prepares, in order:
#   1. Python 3.12+ and the project virtual environment (.venv) with requirements.txt installed
#   2. Node.js 20+ (used only by the frontend unit tests)
#   3. .env (copied from .env.example on first run; you then fill it in and rerun)
#   4. Azure CLI sign-in (used by the application and Foundry SDK through DefaultAzureCredential)
#   5. Demo readiness: scripts/validate_demo.py --quick (configuration, evidence hashes, Claims
#      Operations API, Foundry project, agent version 3, File Search vector store, OpenAPI tool,
#      application, demo files)
#
# It never creates, updates or republishes the Foundry agent, its vector store or any Azure
# resource, and it never prints .env values.
#
# Usage: bash scripts/setup.sh [--reinstall] [--full]
#   --reinstall  reinstall Python dependencies even when present
#   --full       run the full readiness check including all offline test suites (about two minutes)
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
REINSTALL=0
FULL=0
for arg in "$@"; do
  case "$arg" in
    --reinstall) REINSTALL=1 ;;
    --full) FULL=1 ;;
    *) echo "unknown option: $arg"; exit 2 ;;
  esac
done

step() { printf '\n== %s\n' "$1"; }
ok() { printf '  OK    %s\n' "$1"; }
warn() { printf '  WARN  %s\n' "$1"; }
fail() {
  printf '  FAIL  %s\n  Fix:  %s\n\nCLAIMS DEMO NOT READY\n' "$1" "$2"
  exit 1
}

step 'Python 3.12+ and virtual environment'
VENV_PY=.venv/bin/python
if [ ! -x "$VENV_PY" ]; then
  BASE=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       [ "$("$candidate" -c 'import sys; print(int(sys.version_info >= (3, 12)))' 2>/dev/null)" = "1" ]; then
      BASE="$candidate"; break
    fi
  done
  [ -n "$BASE" ] || fail 'Python 3.12 or later was not found.' 'Install Python 3.12+ (python.org, Homebrew or your package manager), then rerun.'
  "$BASE" -m venv .venv || fail 'Could not create .venv.' 'Install the venv module (for example python3-venv), then rerun.'
  REINSTALL=1
  ok 'created .venv'
fi
VERSION=$("$VENV_PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
"$VENV_PY" -c 'import sys; sys.exit(sys.version_info < (3, 12))' || fail ".venv uses Python $VERSION." 'Delete .venv and rerun with Python 3.12+ installed.'
ok "Python $VERSION (.venv)"

if [ "$REINSTALL" = 1 ] || ! "$VENV_PY" -c 'import fastapi, uvicorn, dotenv, pypdf, azure.ai.projects, azure.identity, openai' 2>/dev/null; then
  echo '  installing requirements.txt ...'
  "$VENV_PY" -m pip install --quiet --disable-pip-version-check -r requirements.txt || fail 'pip install failed.' 'Check network access to PyPI, then rerun.'
fi
ok 'Python dependencies installed'

step 'Node.js 20+ (frontend tests)'
if command -v node >/dev/null 2>&1; then
  NODE=$(node --version)
  MAJOR=${NODE#v}; MAJOR=${MAJOR%%.*}
  if [ "$MAJOR" -ge 20 ]; then ok "Node.js $NODE"; else warn "Node.js $NODE; install 20+ to run the frontend tests (the demo itself does not need Node)."; fi
else
  warn 'Node.js not found; install 20+ to run the frontend tests (the demo itself does not need Node).'
fi

step 'Environment configuration (.env)'
if [ ! -f .env ]; then
  cp .env.example .env
  fail 'Created .env from .env.example; it needs your values.' 'Fill in FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_DEPLOYMENT_NAME, TOOLS_API_BASE_URL and FOUNDRY_AGENT_VERSION=3 in .env, then rerun.'
fi
ok '.env present (values not shown)'

step 'Azure sign-in'
command -v az >/dev/null 2>&1 || fail 'Azure CLI not found.' 'Install the Azure CLI (https://aka.ms/installazurecli), run az login, then rerun.'
az account show --only-show-errors --output none 2>/dev/null || fail 'Not signed in to Azure.' 'Run az login (and az account set --subscription <the Foundry project subscription>), then rerun.'
ok 'Azure CLI signed in'

step 'Demo readiness'
if [ "$FULL" = 1 ]; then
  exec "$VENV_PY" scripts/validate_demo.py
fi
exec "$VENV_PY" scripts/validate_demo.py --quick
