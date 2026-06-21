$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$skillsDir = Join-Path $codexHome "skills"
$runtimeDir = Join-Path $codexHome "obsidian-knowledge-skills"

New-Item -ItemType Directory -Force -Path $skillsDir | Out-Null

$skillNames = @()
Get-ChildItem -Path (Join-Path $scriptDir "skills") -Directory | ForEach-Object {
    $skillNames += $_.Name
    $target = Join-Path $skillsDir $_.Name
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
    Copy-Item -Path $_.FullName -Destination $skillsDir -Recurse -Force
}

if (Test-Path -LiteralPath $runtimeDir) {
    Remove-Item -LiteralPath $runtimeDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $runtimeDir "scripts") | Out-Null
Copy-Item -Path (Join-Path $scriptDir "scripts\vault_engine.py") -Destination (Join-Path $runtimeDir "scripts") -Force
Copy-Item -Path (Join-Path $scriptDir "AGENTS.md") -Destination $runtimeDir -Force

$manifest = [ordered]@{
    name = "codex-obsidian-knowledge-skills"
    installed_at = (Get-Date).ToUniversalTime().ToString("o")
    skills = $skillNames
    runtime_dir = $runtimeDir
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $runtimeDir "install-manifest.json") -Encoding UTF8

Write-Host "Installed skills to $skillsDir"
Write-Host "Installed runtime to $runtimeDir"
