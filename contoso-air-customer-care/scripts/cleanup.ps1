<#
.SYNOPSIS
    Clean up after the Contoso Air Customer Care demo.

.DESCRIPTION
    A. Local cleanup (default). Removes regenerable files only:
         __pycache__ and .pytest_cache folders, .deploy\ (deployment staging), evaluation\results\.
       Optional: -IncludeVenv removes .venv; -IncludeLocalState removes .env and .foundry-state.json.

    B. Azure cleanup (only with -Azure). Deletes nothing without a typed confirmation per resource:
         - the Operations API Container App (TOOLS_CONTAINER_APP_NAME in AZURE_RESOURCE_GROUP)
         - the whole resource group, only with -DeleteResourceGroup, after listing what it contains

    Foundry resources are never deleted by this script. The agent, its versions and the
    contoso-air-policies vector store are removed in the Foundry portal (instructions are printed),
    so a shared Foundry project is never changed by accident. The Foundry project and model
    deployment are not created by this sample and are never touched.

.PARAMETER DryRun
    Show what would be removed without removing anything.

.EXAMPLE
    .\scripts\cleanup.ps1                 # local cleanup only

.EXAMPLE
    .\scripts\cleanup.ps1 -Azure          # local cleanup, then delete the Container App after confirmation
#>
[CmdletBinding()]
param(
    [switch]$IncludeVenv,
    [switch]$IncludeLocalState,
    [switch]$Azure,
    [switch]$DeleteResourceGroup,
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$prefix = if ($DryRun) { '  [dry run] would remove' } else { '  removed' }

function Remove-Path([string]$path) {
    if (-not (Test-Path $path)) { return }
    if (-not $DryRun) { Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue }
    Write-Host "$prefix $(Resolve-Path -Relative $path -ErrorAction SilentlyContinue)"
}

function Get-Setting([string]$name) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ($value) { return $value }
    if (Test-Path '.env') {
        foreach ($line in Get-Content '.env') {
            if ($line -match "^\s*$name\s*=\s*(.*?)\s*$") { return $Matches[1].Trim('"', "'") }
        }
    }
    return $null
}

function Confirm-Typed([string]$expected, [string]$what) {
    $answer = Read-Host "  Type '$expected' to delete $what (anything else skips)"
    return $answer -ceq $expected
}

# --------------------------------------------------------------------------- A. local
Write-Host 'A. Local cleanup' -ForegroundColor Cyan
$caches = Get-ChildItem -Path $repo -Recurse -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @('__pycache__', '.pytest_cache') -and $_.FullName -notmatch '[\\/]\.venv[\\/]' }
foreach ($dir in $caches) { Remove-Path $dir.FullName }
Remove-Path (Join-Path $repo '.deploy')
Get-ChildItem (Join-Path $repo 'evaluation\results') -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne '.gitkeep' } | ForEach-Object { Remove-Path $_.FullName }
if ($IncludeVenv) { Remove-Path (Join-Path $repo '.venv') }
if ($IncludeLocalState) {
    Remove-Path (Join-Path $repo '.env')
    Remove-Path (Join-Path $repo '.foundry-state.json')
} else {
    Write-Host '  kept .env and .foundry-state.json (use -IncludeLocalState to remove them)'
}

# --------------------------------------------------------------------------- B. Azure
if (-not $Azure) {
    Write-Host "`nB. Azure / Foundry cleanup: skipped. Nothing in Azure or Foundry was changed." -ForegroundColor Cyan
    Write-Host '  To remove the Operations API run: .\scripts\cleanup.ps1 -Azure'
    Write-Host '  For the Foundry agent and knowledge, see README "Clean up".'
    exit 0
}

Write-Host "`nB. Azure cleanup (explicit confirmation required)" -ForegroundColor Cyan
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Host '  Azure CLI (az) not found; nothing deleted.' -ForegroundColor Red
    exit 1
}
$group = Get-Setting 'AZURE_RESOURCE_GROUP'
$app = Get-Setting 'TOOLS_CONTAINER_APP_NAME'
if (-not $app) { $app = 'contoso-air-tools' }
if (-not $group) {
    Write-Host '  AZURE_RESOURCE_GROUP is not set in .env; nothing deleted.' -ForegroundColor Yellow
    Write-Host '  Manual command: az containerapp delete --name <app-name> --resource-group <your-resource-group>'
    exit 1
}

$exists = az containerapp show --name $app --resource-group $group --query name -o tsv 2>$null
if ($LASTEXITCODE -eq 0 -and $exists) {
    Write-Host "  Operations API Container App: $app (resource group $group)"
    Write-Host "  Command: az containerapp delete --name $app --resource-group $group --yes"
    if ($DryRun) { Write-Host '  [dry run] not deleted' }
    elseif (Confirm-Typed $app "Container App '$app'") {
        az containerapp delete --name $app --resource-group $group --yes --only-show-errors
        if ($LASTEXITCODE -eq 0) { Write-Host "  deleted Container App $app" -ForegroundColor Green }
    } else { Write-Host '  skipped' }
} else {
    Write-Host "  Container App '$app' not found in resource group '$group'; nothing to delete."
}

if ($DeleteResourceGroup) {
    Write-Host "`n  Resource group '$group' contains:"
    az resource list --resource-group $group --query '[].{type:type, name:name}' -o table 2>$null
    Write-Host '  Delete it ONLY if you created it for this sample and nothing else in it is shared.' -ForegroundColor Yellow
    Write-Host "  Command: az group delete --name $group --yes"
    if ($DryRun) { Write-Host '  [dry run] not deleted' }
    elseif (Confirm-Typed $group "resource group '$group' and EVERYTHING in it") {
        az group delete --name $group --yes --no-wait
        if ($LASTEXITCODE -eq 0) { Write-Host "  deletion of resource group $group started (runs in the background)" -ForegroundColor Green }
    } else { Write-Host '  skipped' }
}

$agent = Get-Setting 'FOUNDRY_AGENT_NAME'
if (-not $agent) { $agent = 'contoso-air-customer-care' }
Write-Host "`n  Foundry (manual, in the Foundry portal; this script never deletes Foundry resources):"
Write-Host "    1. Agents -> $agent -> delete the agent (removes all versions)."
Write-Host '    2. Data / Files -> delete the contoso-air-policies vector store and its four PDF files.'
Write-Host '    The Foundry project and model deployment were not created by this sample; keep or remove them as you prefer.'
exit 0
