param(
    [string]$Source = "",
    [string]$Destination = "",
    [switch]$Quiet,
    [switch]$Auto
)

$ErrorActionPreference = "Stop"

function Get-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (Test-Path -LiteralPath $Path) {
        return (Resolve-Path -LiteralPath $Path).Path
    }
    return [System.IO.Path]::GetFullPath($Path)
}

function Write-Info {
    param([string]$Message)
    if (-not $Quiet) {
        Write-Host $Message
    }
}

$repoRoot = Get-FullPath (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($Source)) {
    $Source = Join-Path $repoRoot "skill"
}
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $env:USERPROFILE ".codex\skills\a-share-research-html"
}

$sourcePath = Get-FullPath $Source
$destinationPath = Get-FullPath $Destination
$expectedInstallRoot = Get-FullPath (Join-Path $env:USERPROFILE ".codex\skills")

if (-not (Test-Path -LiteralPath (Join-Path $sourcePath "SKILL.md"))) {
    throw "Source skill is invalid: missing SKILL.md at $sourcePath"
}

if (-not $destinationPath.StartsWith($expectedInstallRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to sync outside Codex skills directory: $destinationPath"
}

if ($sourcePath.Equals($destinationPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Source and destination are the same path: $sourcePath"
}

New-Item -ItemType Directory -Force -Path $destinationPath | Out-Null

$robocopyArgs = @(
    $sourcePath,
    $destinationPath,
    "/MIR",
    "/XD", "__pycache__",
    "/XF", "*.pyc",
    "/R:2",
    "/W:1"
)

if ($Quiet) {
    $robocopyArgs += @("/NFL", "/NDL", "/NJH", "/NJS", "/NP")
}

Write-Info "Syncing skill:"
Write-Info "  from: $sourcePath"
Write-Info "  to:   $destinationPath"

& robocopy @robocopyArgs | Out-Host
$code = $LASTEXITCODE
if ($code -ge 8) {
    throw "robocopy failed with exit code $code"
}

$metadata = [ordered]@{
    synced_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss K")
    source = $sourcePath
    destination = $destinationPath
    mode = if ($Auto) { "auto" } else { "manual" }
}
$metadataPath = Join-Path $destinationPath ".codex-sync.json"
($metadata | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $metadataPath -Encoding UTF8

Write-Info "Skill sync complete."
