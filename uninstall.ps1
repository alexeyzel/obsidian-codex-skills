$ErrorActionPreference = "Stop"

$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$skillsDir = Join-Path $codexHome "skills"
$runtimeDir = Join-Path $codexHome "obsidian-knowledge-skills"
$manifestPath = Join-Path $runtimeDir "install-manifest.json"
$fallbackSkillNames = @("vault-setup", "vault-index", "vault-ingest", "vault-rules", "meeting-prep", "internet-research")

if (Test-Path -LiteralPath $manifestPath) {
    $manifest = Get-Content -Raw -Path $manifestPath | ConvertFrom-Json
    $skillNames = @($manifest.skills)
    if ($skillNames.Count -eq 0) {
        $skillNames = $fallbackSkillNames
    }
}
else {
    $skillNames = $fallbackSkillNames
}

foreach ($name in $skillNames) {
    $target = Join-Path $skillsDir $name
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
        Write-Host "Removed skill $name"
    }
}

if (Test-Path -LiteralPath $runtimeDir) {
    Remove-Item -LiteralPath $runtimeDir -Recurse -Force
    Write-Host "Removed runtime $runtimeDir"
}
