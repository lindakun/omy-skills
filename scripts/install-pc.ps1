#Requires -Version 5.1
<#
.SYNOPSIS
  Install pc-assistant runtime (UFO² venv + optional API key).
.EXAMPLE
  .\scripts\install-pc.ps1 -ApiKey "ark-xxxx"
  .\scripts\install-pc.ps1 -ApiKey $env:VOLC_ARK_API_KEY
#>
param(
    [string]$ApiKey = $env:VOLC_ARK_API_KEY,
    [string]$RepoRoot = $env:OMY_SKILLS_ROOT,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    param([string]$Hint)
    if ($Hint -and (Test-Path (Join-Path $Hint "tools\ufo2"))) {
        return (Resolve-Path $Hint).Path
    }
    $here = $PSScriptRoot
    $candidate = (Resolve-Path (Join-Path $here "..")).Path
    if (Test-Path (Join-Path $candidate "tools\ufo2")) {
        return $candidate
    }
    throw "Cannot find omy-skills root (expected tools/ufo2). Set OMY_SKILLS_ROOT or run from repo."
}

$root = Resolve-RepoRoot -Hint $RepoRoot
$ufoRoot = Join-Path $root "tools\ufo2"
$venvPython = Join-Path $ufoRoot "venv\Scripts\python.exe"
$agentsYaml = Join-Path $ufoRoot "config\ufo\agents.yaml"

Write-Host "==> Repo root: $root"
Write-Host "==> UFO root:  $ufoRoot"

# Python version check
$pyVer = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "==> Python:    $pyVer ($Python)"
if ($pyVer -notmatch '^3\.11') {
    Write-Warning "UFO² works best with Python 3.11. Current: $pyVer. Continue anyway..."
}

Push-Location $ufoRoot
try {
    if (-not (Test-Path $venvPython)) {
        Write-Host "==> Creating venv..."
        & $Python -m venv venv
    } else {
        Write-Host "==> venv already exists"
    }

    $pip = Join-Path $ufoRoot "venv\Scripts\pip.exe"
    Write-Host "==> Installing requirements (may take several minutes)..."
    & $pip install -U pip
    & $pip install -r requirements.txt

    if ($ApiKey) {
        if (-not (Test-Path $agentsYaml)) {
            throw "Missing $agentsYaml"
        }
        $content = Get-Content -Raw -LiteralPath $agentsYaml
        if ($content -match 'YOUR_VOLC_ARK_API_KEY') {
            $content = $content -replace 'YOUR_VOLC_ARK_API_KEY', $ApiKey
            Set-Content -LiteralPath $agentsYaml -Value $content -NoNewline -Encoding UTF8
            Write-Host "==> Wrote API key into config/ufo/agents.yaml (local only; do not commit)"
        } else {
            Write-Host "==> agents.yaml already has non-placeholder keys; left unchanged"
        }
    } else {
        Write-Warning "No -ApiKey / VOLC_ARK_API_KEY. Edit tools/ufo2/config/ufo/agents.yaml manually."
    }
} finally {
    Pop-Location
}

# Persist OMY_SKILLS_ROOT for current user if not set
if (-not $env:OMY_SKILLS_ROOT) {
    [System.Environment]::SetEnvironmentVariable("OMY_SKILLS_ROOT", $root, "User")
    $env:OMY_SKILLS_ROOT = $root
    Write-Host "==> Set user env OMY_SKILLS_ROOT=$root"
}

# Persist UFO_ROOT for current user if not set
if (-not $env:UFO_ROOT) {
    [System.Environment]::SetEnvironmentVariable("UFO_ROOT", $ufoRoot, "User")
    $env:UFO_ROOT = $ufoRoot
    Write-Host "==> Set user env UFO_ROOT=$ufoRoot"
}

Write-Host ""
Write-Host "Done. Smoke test (optional):"
Write-Host "  cd `"$ufoRoot`""
Write-Host "  .\venv\Scripts\Activate.ps1"
Write-Host "  python -m ufo --task pc-smoke -r `"Step 1: Open Notepad, type Hello, then close it.`""
Write-Host ""
Write-Host "Register skills/pc-assistant with your Agent, then try: 用电脑打开记事本写一句 hello"
