#Requires -Version 5.1
<#
.SYNOPSIS
  Symlink omy-skills/skills/* into common Agent skill directories.
  Does not touch LLM keys or mobilerun app-support configs.
.EXAMPLE
  .\scripts\link-skills.ps1
  .\scripts\link-skills.ps1 -DryRun
  .\scripts\link-skills.ps1 -Unlink
#>
param(
    [switch]$DryRun,
    [switch]$Unlink
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$skillsSrc = Join-Path $root "skills"
if (-not (Test-Path $skillsSrc)) {
    throw "Missing $skillsSrc"
}

$candidates = @(
    (Join-Path $env:USERPROFILE ".claude\skills"),
    (Join-Path $env:USERPROFILE ".codex\skills"),
    (Join-Path $env:USERPROFILE ".agents\skills"),
    (Join-Path $env:USERPROFILE ".opencode\skills")
)

Get-ChildItem -Directory $skillsSrc | ForEach-Object {
    $name = $_.Name
    $src = $_.FullName
    if (-not (Test-Path (Join-Path $src "SKILL.md"))) {
        Write-Host "skip (no SKILL.md): $src"
        return
    }
    foreach ($parent in $candidates) {
        if (-not (Test-Path $parent)) { continue }
        $dest = Join-Path $parent $name
        if ($Unlink) {
            if (Test-Path $dest) {
                $item = Get-Item $dest -Force
                if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                    if ($DryRun) { Write-Host "DRY unlink $dest" }
                    else { Remove-Item $dest -Force; Write-Host "unlinked $dest" }
                }
            }
            continue
        }
        if ((Test-Path $dest) -and -not ((Get-Item $dest).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            Write-Host "skip (exists, not symlink): $dest"
            continue
        }
        if ($DryRun) {
            Write-Host "DRY link $dest -> $src"
        } else {
            # Windows: directory junction/symlink (may need Developer Mode for symlink)
            if (Test-Path $dest) { Remove-Item $dest -Force }
            try {
                New-Item -ItemType SymbolicLink -Path $dest -Target $src | Out-Null
            } catch {
                cmd /c mklink /J "$dest" "$src" | Out-Null
            }
            Write-Host "linked $dest -> $src"
        }
    }
}

Write-Host ""
Write-Host "Done. Tip: `$env:OMY_SKILLS_ROOT = '$root'"
Write-Host "Only existing skill roots were used; create a target dir first if needed."
