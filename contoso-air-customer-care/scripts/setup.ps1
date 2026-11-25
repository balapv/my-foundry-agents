<#
.SYNOPSIS
    Prepare this machine to present the Contoso Air Customer Care demo, then check that it is ready.

.DESCRIPTION
    Runs four stages and stops with an actionable message at the first stage that cannot continue:

      1. Local prerequisites       Python 3.10+, Azure CLI, .venv, packages from requirements.txt
      2. Environment configuration .env present and required settings filled in (values are never printed)
      3. Azure / Foundry           Azure CLI sign-in
      4. Validation                python scripts/validate_demo.py: data, knowledge PDFs, Operations API,
                                   Foundry project, agent and active version, knowledge, web app

    Setup never creates, updates or deletes the Foundry agent, its versions, the vector store or any
    Azure resource. To create the agent, follow README "Option A" (Foundry portal) or "Option B" (code).

.PARAMETER SkipInstall
    Skip "pip install -r requirements.txt".

.PARAMETER Hero
    Also run one live hero turn through the web app (one model call, about 30-45 seconds).

.EXAMPLE
    .\scripts\setup.ps1

.EXAMPLE
    .\scripts\setup.ps1 -SkipInstall -Hero
#>
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$Hero
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$env:PYTHONIOENCODING = 'utf-8'
$script:problems = 0
$required = @('FOUNDRY_PROJECT_ENDPOINT', 'FOUNDRY_MODEL_DEPLOYMENT_NAME', 'FOUNDRY_AGENT_NAME', 'TOOLS_API_BASE_URL')

function Write-Stage([string]$title) { Write-Host "`n$title" -ForegroundColor Cyan }
function Write-Pass([string]$message) { Write-Host "  [PASS] $message" -ForegroundColor Green }
function Write-Warn([string]$message, [string]$fix) {
    Write-Host "  [WARN] $message" -ForegroundColor Yellow
    if ($fix) { Write-Host "         -> $fix" }
}
function Write-Fail([string]$message, [string]$fix) {
    Write-Host "  [FAIL] $message" -ForegroundColor Red
    if ($fix) { Write-Host "         -> $fix" }
    $script:problems++
}
function Stop-Setup([string]$stage) {
    Write-Host "`nSETUP INCOMPLETE: fix the $stage items above, then run .\scripts\setup.ps1 again." -ForegroundColor Red
    exit 1
}

# Returns "major.minor" for a Python command, or $null (also for the Windows Store "python" alias).
function Get-PythonVersion([string[]]$command) {
    try {
        $exe = $command[0]
        $rest = @($command | Select-Object -Skip 1)
        $output = & $exe @rest -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$output" -match '^\d+\.\d+$') { return "$output" }
    } catch { }
    return $null
}

function Test-MinVersion([string]$version) {
    $parts = $version.Split('.')
    return ([int]$parts[0] -gt 3) -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10)
}

Write-Host 'Contoso Air Customer Care - demo setup' -ForegroundColor White

# --------------------------------------------------------------------------- 1. local prerequisites
Write-Stage '1. Local prerequisites'
$venvPython = Join-Path $repo '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    $basePython = $null
    foreach ($candidate in @(@('py', '-3'), @('python'), @('python3'))) {
        if (Get-Command $candidate[0] -ErrorAction SilentlyContinue) {
            $version = Get-PythonVersion $candidate
            if ($version -and (Test-MinVersion $version)) { $basePython = $candidate; break }
        }
    }
    if (-not $basePython) {
        Write-Fail 'Python 3.10 or later was not found.' 'Install it from https://www.python.org/downloads/ (or: winget install Python.Python.3.12), then open a new terminal.'
        Stop-Setup 'local prerequisite'
    }
    Write-Host "  Creating .venv with $($basePython -join ' ')..."
    $exe = $basePython[0]
    $rest = @($basePython | Select-Object -Skip 1)
    & $exe @rest -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Write-Fail 'Could not create the .venv virtual environment.' 'Run: python -m venv .venv and check the error.'
        Stop-Setup 'local prerequisite'
    }
}
$venvVersion = Get-PythonVersion @($venvPython)
if ($venvVersion -and (Test-MinVersion $venvVersion)) {
    Write-Pass "Python $venvVersion in .venv"
} else {
    Write-Fail "The .venv Python is missing or older than 3.10 ($venvVersion)." 'Delete the .venv folder and run setup again.'
    Stop-Setup 'local prerequisite'
}

if ($SkipInstall) {
    Write-Warn 'Skipped installing Python packages (-SkipInstall).'
} else {
    Write-Host '  Installing Python packages from requirements.txt...'
    & $venvPython -m pip install --disable-pip-version-check --quiet -r requirements.txt
    if ($LASTEXITCODE -eq 0) { Write-Pass 'Python packages installed' }
    else { Write-Fail 'pip install failed.' 'Run: .\.venv\Scripts\python.exe -m pip install -r requirements.txt and read the error.' }
}

if (Get-Command az -ErrorAction SilentlyContinue) { Write-Pass 'Azure CLI installed' }
else { Write-Fail 'Azure CLI (az) was not found.' 'Install it: winget install Microsoft.AzureCLI, then open a new terminal.' }

if (Get-Command node -ErrorAction SilentlyContinue) { Write-Pass 'Node.js installed (optional; used by one frontend syntax test)' }
else { Write-Warn 'Node.js not found (optional; one frontend syntax test is skipped).' }

if ($script:problems -gt 0) { Stop-Setup 'local prerequisite' }

# --------------------------------------------------------------------------- 2. environment configuration
Write-Stage '2. Environment configuration'
$envFile = Join-Path $repo '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $repo '.env.example') $envFile
    Write-Fail 'No .env file. Created one from .env.example.' 'Open .env and fill in the values for YOUR environment (see README "Prerequisites").'
    Stop-Setup 'environment configuration'
}
Write-Pass '.env present (git-ignored)'

$values = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') { $values[$Matches[1]] = $Matches[2].Trim('"', "'") }
}
$missing = @()
foreach ($name in $required) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if (-not $value) { $value = $values[$name] }
    if (-not $value) { $missing += $name }
}
if ($missing.Count -gt 0) {
    Write-Fail "Not set in .env: $($missing -join ', ')" 'Fill them in .env. TOOLS_API_BASE_URL comes from scripts/deploy_tools.py (README "Deploy the Operations API").'
    Stop-Setup 'environment configuration'
}
Write-Pass "Required settings set: $($required -join ', ') (values not shown)"
$toolsUrl = [Environment]::GetEnvironmentVariable('TOOLS_API_BASE_URL')
if (-not $toolsUrl) { $toolsUrl = $values['TOOLS_API_BASE_URL'] }
if ($toolsUrl -notmatch '^https://' -or $toolsUrl -match '//(localhost|127\.0\.0\.1)') {
    Write-Fail 'TOOLS_API_BASE_URL must be a public https:// URL; Foundry calls the tools from the cloud.' 'Deploy with: python scripts/deploy_tools.py --resource-group <rg> --update-env'
    Stop-Setup 'environment configuration'
}

# --------------------------------------------------------------------------- 3. Azure / Foundry prerequisites
Write-Stage '3. Azure / Foundry prerequisites'
$account = az account show --query '{name:name}' -o json 2>$null | Out-String
if ($LASTEXITCODE -ne 0 -or -not $account.Trim()) {
    Write-Fail 'Azure CLI is not signed in.' 'Run: az login   (then, if needed: az account set --subscription <subscription name>)'
    Stop-Setup 'Azure sign-in'
}
$accountInfo = $account | ConvertFrom-Json
Write-Pass "Azure CLI signed in (subscription: $($accountInfo.name))"
Write-Host '  The Foundry project, agent and version are checked in the next stage.'

# --------------------------------------------------------------------------- 4. validation
Write-Stage '4. Validation (python scripts\validate_demo.py)'
$validateArgs = @('scripts\validate_demo.py')
if ($Hero) { $validateArgs += '--hero' }
& $venvPython @validateArgs
$code = $LASTEXITCODE
if ($code -eq 0) {
    Write-Host "`nSETUP COMPLETE. Start the web app with:" -ForegroundColor Green
    Write-Host '  .\.venv\Scripts\python.exe -m uvicorn server:app --app-dir webapp/backend --port 8080'
}
exit $code
