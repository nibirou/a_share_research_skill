param(
    [switch]$NoInitialSync
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$hooksPath = Join-Path $repoRoot ".githooks"
$syncScript = Join-Path $repoRoot "scripts\sync_skill.ps1"

if (-not (Test-Path -LiteralPath $hooksPath)) {
    throw "Missing hooks directory: $hooksPath"
}

if (-not (Test-Path -LiteralPath $syncScript)) {
    throw "Missing sync script: $syncScript"
}

Push-Location $repoRoot
try {
    git config core.hooksPath .githooks
    $current = git config --get core.hooksPath
    if ($current -ne ".githooks") {
        throw "Failed to set core.hooksPath; current value is '$current'"
    }

    if (-not $NoInitialSync) {
        & $syncScript
    }

    Write-Host "Skill sync hooks installed for this repository."
    Write-Host "Git hook path: $current"
}
finally {
    Pop-Location
}
