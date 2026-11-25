<#
.SYNOPSIS
  Prepare this machine to present the Contoso Claims Processing demo (Windows).

.DESCRIPTION
  Verifies or prepares, in order:
    1. Python 3.12+ and the project virtual environment (.venv) with requirements.txt installed
    2. Node.js 20+ (used only by the frontend unit tests)
    3. .env (copied from .env.example on first run; you then fill it in and rerun)
    4. Azure CLI sign-in (used by the application and Foundry SDK through DefaultAzureCredential)
    5. Demo readiness: scripts/validate_demo.py --quick (configuration, evidence hashes, Claims
       Operations API, Foundry project, agent version 3, File Search vector store, OpenAPI tool,
       application, demo files)

  It never creates, updates or republishes the Foundry agent, its vector store or any Azure
  resource, and it never prints .env values.

.PARAMETER Reinstall
  Reinstall Python dependencies even when they are already present.

.PARAMETER Full
  Run the full readiness check, including all offline test suites (about two minutes).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>
param(
    [switch]$Reinstall,
    [switch]$Full
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONIOENCODING = 'utf-8'

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "  OK    $text" -ForegroundColor Green }
function Fail($text, $fix) {
    Write-Host "  FAIL  $text" -ForegroundColor Red
    Write-Host "  Fix:  $fix"
    Write-Host "`nCLAIMS DEMO NOT READY" -ForegroundColor Red
    exit 1
}

Step 'Python 3.12+ and virtual environment'
$venvPython = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    $base = $null
    foreach ($candidate in @('py -3', 'python')) {
        $parts = $candidate.Split(' ')
        if (Get-Command $parts[0] -ErrorAction SilentlyContinue) {
            $pyArgs = @($parts | Select-Object -Skip 1)
            $ok = & $parts[0] @pyArgs -c 'import sys; print(int(sys.version_info >= (3, 12)))' 2>$null
            if ($ok -eq '1') { $base = $parts; break }
        }
    }
    if (-not $base) { Fail 'Python 3.12 or later was not found.' 'Install Python 3.12+ from python.org (tick "Add to PATH"), then rerun.' }
    $pyArgs = @($base | Select-Object -Skip 1)
    & $base[0] @pyArgs -m venv .venv
    if ($LASTEXITCODE) { Fail 'Could not create .venv.' 'Check the Python installation, then rerun.' }
    $Reinstall = $true
    Ok 'created .venv'
}
$version = & $venvPython -c 'import sys; print(sys.version.split()[0]); sys.exit(sys.version_info < (3, 12))'
if ($LASTEXITCODE) { Fail ".venv uses Python $version." 'Delete .venv and rerun with Python 3.12+ installed.' }
Ok "Python $version (.venv)"

& $venvPython -c 'import fastapi, uvicorn, dotenv, pypdf, azure.ai.projects, azure.identity, openai' 2>$null
if ($LASTEXITCODE -or $Reinstall) {
    Write-Host '  installing requirements.txt ...'
    & $venvPython -m pip install --quiet --disable-pip-version-check -r requirements.txt
    if ($LASTEXITCODE) { Fail 'pip install failed.' 'Check network access to PyPI, then rerun.' }
}
Ok 'Python dependencies installed'

Step 'Node.js 20+ (frontend tests)'
if (Get-Command node -ErrorAction SilentlyContinue) {
    $node = (& node --version).Trim()
    if ([int]($node.TrimStart('v').Split('.')[0]) -ge 20) { Ok "Node.js $node" }
    else { Write-Host "  WARN  Node.js $node; install 20+ to run the frontend tests (the demo itself does not need Node)." -ForegroundColor Yellow }
} else {
    Write-Host '  WARN  Node.js not found; install 20+ to run the frontend tests (the demo itself does not need Node).' -ForegroundColor Yellow
}

Step 'Environment configuration (.env)'
if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Fail 'Created .env from .env.example; it needs your values.' 'Fill in FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_DEPLOYMENT_NAME, TOOLS_API_BASE_URL and FOUNDRY_AGENT_VERSION=3 in .env, then rerun.'
}
Ok '.env present (values not shown)'

Step 'Azure sign-in'
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Fail 'Azure CLI not found.' 'Install the Azure CLI (https://aka.ms/installazurecliwindows), run az login, then rerun.'
}
& az account show --only-show-errors --output none 2>$null
if ($LASTEXITCODE) { Fail 'Not signed in to Azure.' 'Run az login (and az account set --subscription <the Foundry project subscription>), then rerun.' }
Ok 'Azure CLI signed in'

Step 'Demo readiness'
$readinessArgs = @('scripts\validate_demo.py')
if (-not $Full) { $readinessArgs += '--quick' }
& $venvPython @readinessArgs
exit $LASTEXITCODE
