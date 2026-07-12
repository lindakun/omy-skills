#Requires -Version 5.1
<#
.SYNOPSIS
  Prepare mobile-assistant: copy mobilerun config template and inject API key.
  Does not install ADB/Python/mobilerun for you — prints remaining steps.
.EXAMPLE
  .\scripts\install-mobile.ps1 -ApiKey "ark-xxxx" -MobilerunHome "C:\src\mobilerun"
#>
param(
    [string]$ApiKey = $env:VOLC_ARK_API_KEY,
    [string]$RepoRoot = $env:OMY_SKILLS_ROOT,
    [string]$MobilerunHome = $env:MOBILERUN_HOME,
    [string]$DeviceSerial = ""
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    param([string]$Hint)
    if ($Hint -and (Test-Path (Join-Path $Hint "tools\mobilerun"))) {
        return (Resolve-Path $Hint).Path
    }
    $candidate = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    if (Test-Path (Join-Path $candidate "tools\mobilerun")) {
        return $candidate
    }
    throw "Cannot find omy-skills root. Set OMY_SKILLS_ROOT or run from repo."
}

$root = Resolve-RepoRoot -Hint $RepoRoot
$template = Join-Path $root "tools\mobilerun\config_multi_windows.yaml"
if (-not (Test-Path $template)) {
    throw "Missing template: $template"
}

# Local config under repo (gitignored pattern via *.local.yaml guidance; we write to config.local.yaml)
$localConfigDir = Join-Path $root "tools\mobilerun"
$localConfig = Join-Path $localConfigDir "config.local.yaml"

Write-Host "==> Repo root: $root"
Copy-Item -LiteralPath $template -Destination $localConfig -Force
$content = Get-Content -Raw -LiteralPath $localConfig

if ($ApiKey) {
    $content = $content -replace 'YOUR_VOLC_ARK_API_KEY', $ApiKey
    Write-Host "==> Injected VOLC API key into local config"
} else {
    Write-Warning "No -ApiKey / VOLC_ARK_API_KEY. Edit $localConfig and replace YOUR_VOLC_ARK_API_KEY"
}

if ($DeviceSerial) {
    # Prefer USB device profile with given serial
    $content = $content -replace 'serial:\s*emulator-5554', "serial: $DeviceSerial"
    $content = $content -replace '<<:\s*\*android_emulator', '<<: *android_usb'
    Write-Host "==> Device serial set to $DeviceSerial"
} else {
    Write-Host "==> Tip: pass -DeviceSerial from 'adb devices' output for physical phones"
}

Set-Content -LiteralPath $localConfig -Value $content -NoNewline -Encoding UTF8
Write-Host "==> Wrote $localConfig (do not commit if it contains real keys)"

if (-not $env:OMY_SKILLS_ROOT) {
    [System.Environment]::SetEnvironmentVariable("OMY_SKILLS_ROOT", $root, "User")
    $env:OMY_SKILLS_ROOT = $root
    Write-Host "==> Set user env OMY_SKILLS_ROOT=$root"
}

[System.Environment]::SetEnvironmentVariable("MOBILERUN_CONFIG", $localConfig, "User")
$env:MOBILERUN_CONFIG = $localConfig
Write-Host "==> Set user env MOBILERUN_CONFIG=$localConfig"

if ($MobilerunHome) {
    [System.Environment]::SetEnvironmentVariable("MOBILERUN_HOME", $MobilerunHome, "User")
    $env:MOBILERUN_HOME = $MobilerunHome
    Write-Host "==> Set user env MOBILERUN_HOME=$MobilerunHome"
    Copy-Item -LiteralPath $localConfig -Destination (Join-Path $MobilerunHome "config_multi_windows.yaml") -Force
    Write-Host "==> Also copied config to MOBILERUN_HOME"
}

Write-Host ""
Write-Host "Next steps (if not done yet):"
Write-Host "  1. Install Python 3.11~3.13 and add to PATH"
Write-Host "  2. Install Android Platform Tools; ensure 'adb' works"
Write-Host "  3. Enable USB debugging on phone; adb devices shows 'device'"
Write-Host "  4. git clone https://github.com/droidrun/mobilerun.git"
Write-Host "     cd mobilerun; pip install -e .; mobilerun setup"
Write-Host "  5. Re-run this script with -MobilerunHome <path-to-mobilerun>"
Write-Host "  6. Test: mobilerun run `"打开设置查看Android版本`""
Write-Host ""
Write-Host "Register skills/mobile-assistant with your Agent, then try: 用手机打开设置"
