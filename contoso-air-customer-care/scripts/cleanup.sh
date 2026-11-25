#!/usr/bin/env bash
# Clean up after the Contoso Air Customer Care demo.
#
# A. Local cleanup (default). Removes regenerable files only:
#      __pycache__ and .pytest_cache folders, .deploy/ (deployment staging), evaluation/results/.
#    Optional: --include-venv removes .venv; --include-local-state removes .env and .foundry-state.json.
#
# B. Azure cleanup (only with --azure). Deletes nothing without a typed confirmation per resource:
#      - the Operations API Container App (TOOLS_CONTAINER_APP_NAME in AZURE_RESOURCE_GROUP)
#      - the whole resource group, only with --delete-resource-group, after listing what it contains
#
# Foundry resources (agent, versions, vector store) are never deleted by this script; instructions
# for the Foundry portal are printed instead.
#
# Usage:
#   ./scripts/cleanup.sh                  # local cleanup only
#   ./scripts/cleanup.sh --dry-run        # show what would be removed
#   ./scripts/cleanup.sh --azure          # also delete the Container App after confirmation
set -u

cd "$(dirname "$0")/.."
INCLUDE_VENV=0; INCLUDE_STATE=0; AZURE=0; DELETE_GROUP=0; DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --include-venv) INCLUDE_VENV=1 ;;
    --include-local-state) INCLUDE_STATE=1 ;;
    --azure) AZURE=1 ;;
    --delete-resource-group) DELETE_GROUP=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

remove_path() {
  [ -e "$1" ] || return 0
  if [ "$DRY_RUN" -eq 1 ]; then echo "  [dry run] would remove $1"; else rm -rf "$1"; echo "  removed $1"; fi
}
setting() {
  local value
  value="$(printenv "$1" 2>/dev/null || true)"
  if [ -z "$value" ] && [ -f .env ]; then
    value="$(grep -E "^[[:space:]]*$1[[:space:]]*=" .env | tail -n 1 | cut -d= -f2- | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//')"
  fi
  printf '%s' "$value"
}
confirm_typed() {
  local answer
  read -r -p "  Type '$1' to delete $2 (anything else skips): " answer
  [ "$answer" = "$1" ]
}

# --------------------------------------------------------------------------- A. local
echo "A. Local cleanup"
while IFS= read -r dir; do remove_path "$dir"; done < <(
  find . -path ./.venv -prune -o -type d \( -name __pycache__ -o -name .pytest_cache \) -print)
remove_path ./.deploy
for item in evaluation/results/* evaluation/results/.[!.]*; do
  [ -e "$item" ] && [ "$(basename "$item")" != ".gitkeep" ] && remove_path "$item"
done
[ "$INCLUDE_VENV" -eq 1 ] && remove_path ./.venv
if [ "$INCLUDE_STATE" -eq 1 ]; then
  remove_path ./.env; remove_path ./.foundry-state.json
else
  echo "  kept .env and .foundry-state.json (use --include-local-state to remove them)"
fi

# --------------------------------------------------------------------------- B. Azure
if [ "$AZURE" -eq 0 ]; then
  printf '\nB. Azure / Foundry cleanup: skipped. Nothing in Azure or Foundry was changed.\n'
  echo "  To remove the Operations API run: ./scripts/cleanup.sh --azure"
  echo "  For the Foundry agent and knowledge, see README \"Clean up\"."
  exit 0
fi

printf '\nB. Azure cleanup (explicit confirmation required)\n'
command -v az >/dev/null 2>&1 || { echo "  Azure CLI (az) not found; nothing deleted."; exit 1; }
GROUP="$(setting AZURE_RESOURCE_GROUP)"
APP="$(setting TOOLS_CONTAINER_APP_NAME)"; APP="${APP:-contoso-air-tools}"
if [ -z "$GROUP" ]; then
  echo "  AZURE_RESOURCE_GROUP is not set in .env; nothing deleted."
  echo "  Manual command: az containerapp delete --name <app-name> --resource-group <your-resource-group>"
  exit 1
fi

if [ -n "$(az containerapp show --name "$APP" --resource-group "$GROUP" --query name -o tsv 2>/dev/null)" ]; then
  echo "  Operations API Container App: $APP (resource group $GROUP)"
  echo "  Command: az containerapp delete --name $APP --resource-group $GROUP --yes"
  if [ "$DRY_RUN" -eq 1 ]; then echo "  [dry run] not deleted"
  elif confirm_typed "$APP" "Container App '$APP'"; then
    az containerapp delete --name "$APP" --resource-group "$GROUP" --yes --only-show-errors && echo "  deleted Container App $APP"
  else echo "  skipped"; fi
else
  echo "  Container App '$APP' not found in resource group '$GROUP'; nothing to delete."
fi

if [ "$DELETE_GROUP" -eq 1 ]; then
  printf "\n  Resource group '%s' contains:\n" "$GROUP"
  az resource list --resource-group "$GROUP" --query '[].{type:type, name:name}' -o table 2>/dev/null
  echo "  Delete it ONLY if you created it for this sample and nothing else in it is shared."
  echo "  Command: az group delete --name $GROUP --yes"
  if [ "$DRY_RUN" -eq 1 ]; then echo "  [dry run] not deleted"
  elif confirm_typed "$GROUP" "resource group '$GROUP' and EVERYTHING in it"; then
    az group delete --name "$GROUP" --yes --no-wait && echo "  deletion of resource group $GROUP started (runs in the background)"
  else echo "  skipped"; fi
fi

AGENT="$(setting FOUNDRY_AGENT_NAME)"; AGENT="${AGENT:-contoso-air-customer-care}"
printf '\n  Foundry (manual, in the Foundry portal; this script never deletes Foundry resources):\n'
echo "    1. Agents -> $AGENT -> delete the agent (removes all versions)."
echo "    2. Data / Files -> delete the contoso-air-policies vector store and its four PDF files."
echo "    The Foundry project and model deployment were not created by this sample; keep or remove them as you prefer."
exit 0
