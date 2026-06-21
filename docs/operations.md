# Operations

## Install

Install copies both the Codex skills and the runtime engine into `CODEX_HOME`.

macOS or Linux:

```bash
./install.sh
ENGINE="${CODEX_HOME:-$HOME/.codex}/obsidian-knowledge-skills/scripts/vault_engine.py"
```

Windows PowerShell:

```powershell
.\install.ps1
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$engine = Join-Path $codexHome "obsidian-knowledge-skills\scripts\vault_engine.py"
```

If local execution policy blocks scripts, run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1`.

For local development from the repository checkout, `scripts/vault_engine.py` is also valid.

## Update

Use the repository clone as the update source, then reinstall:

```bash
git pull --ff-only
./install.sh
```

Windows PowerShell:

```powershell
git pull --ff-only
.\install.ps1
```

The installer replaces the installed skill/runtime copy. It does not modify existing vaults.

## Uninstall

```bash
./uninstall.sh
```

Windows PowerShell:

```powershell
.\uninstall.ps1
```

If local execution policy blocks scripts, run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1`.

Uninstall removes only this suite's installed skill folders and installed runtime under `CODEX_HOME`.

## Setup

```bash
cp Config.md /path/to/vault/Config.md
# Edit /path/to/vault/Config.md before init if needed.
python "$ENGINE" init --vault /path/to/vault
python "$ENGINE" index --vault /path/to/vault
```

## Source Ingest

Queue notes and meeting notes share the same plan schema. The entrypoint commands below only choose the source folder and policy.

### Queue Sources

Generate tasks:

```bash
python "$ENGINE" queue-tasks --vault /path/to/vault --limit 20 > queue-tasks.json
```

Codex reads `queue-tasks.json`, makes semantic decisions, and writes `ingest-plan.json` with `kind: source`, `source_policy: delete_after_success`, and `updates[]`.

Apply:

```bash
python "$ENGINE" apply-plan --vault /path/to/vault --input ingest-plan.json
```

Summarize updated notes:

```bash
python "$ENGINE" summary-tasks --vault /path/to/vault --limit 50 > summary-tasks.json
python "$ENGINE" apply-summaries --vault /path/to/vault --input summaries.json
```

Finalize queue:

```bash
python "$ENGINE" finalize-queue --vault /path/to/vault
```

`finalize-queue` deletes a source only when every target note exists and each current summary source hash is recorded in `Service/state/summaries.json`.

For multi-target queue sources, every target must have a current summary before deletion.

### Meeting Sources

```bash
python "$ENGINE" meeting-tasks --vault /path/to/vault --limit 20 > meeting-tasks.json
python "$ENGINE" apply-plan --vault /path/to/vault --input meeting-plan.json
python "$ENGINE" summary-tasks --vault /path/to/vault --limit 50 > summary-tasks.json
python "$ENGINE" apply-summaries --vault /path/to/vault --input summaries.json
```

Codex writes `kind: source`, `source_policy: keep_and_mark_processed`, optional `source_summary`, and `updates[]`.

Only meetings with missing or false `agent_processed` are processed. If a meeting still contains the configured summary placeholder, the plan must provide `source_summary` before the engine marks it processed.

## Meeting Preparation

```bash
python "$ENGINE" meeting-prep-task --vault /path/to/vault --calendar-title "Calendar title" --date 2026-06-22 > meeting-prep-task.json
python "$ENGINE" apply-meeting-prep --vault /path/to/vault --input meeting-prep-plan.json
```
