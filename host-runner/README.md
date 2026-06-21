# Obsidian Process Queue Host Runner

This runner lets n8n call the Codex Obsidian skills through one stable host-side command.

n8n should not contain vault-ingest logic. It should call the runner over SSH, parse the single JSON object printed to stdout, and notify based on `status`.

## What It Does

- Reads the vault `Config.md`.
- Builds queue and meeting ingest tasks with the deterministic vault engine.
- Calls Codex CLI in non-interactive mode to produce JSON ingest plans and summaries.
- Applies plans and summaries with the deterministic engine.
- Finalizes queue note deletion only after target summaries are current.
- Writes run artifacts under a local state directory.
- Prints one JSON result to stdout.

## Requirements

- Python 3 on the host.
- Codex CLI installed and authenticated for the host user.
- This skill suite installed with `install.sh` or `install.ps1`.
- A synced local Markdown Obsidian vault with `Config.md` at the vault root.

## Install On A Linux Host

After installing this skill suite, expose the runner as a host command:

```bash
mkdir -p "$HOME/.local/bin"
install -m 700 \
  "${CODEX_HOME:-$HOME/.codex}/obsidian-knowledge-skills/host-runner/obsidian-process-queue.py" \
  "$HOME/.local/bin/obsidian-process-queue"
```

Set the vault path if it is not `~/obsidian/vault`:

```bash
export OBSIDIAN_VAULT="/path/to/obsidian/vault"
```

Optional overrides:

```bash
export CODEX_BIN="$HOME/.local/bin/codex"
export CODEX_ARGS='exec --skip-git-repo-check --sandbox read-only'
export QUEUE_LIMIT=20
export MEETING_LIMIT=20
export SUMMARY_LIMIT=50
export MAX_CODEX_PROMPT_CHARS=120000
export RUNNER_STEP_TIMEOUT=1800
```

## Smoke Test

```bash
OBSIDIAN_VAULT="/path/to/obsidian/vault" "$HOME/.local/bin/obsidian-process-queue"
```

Expected stdout is one JSON object with `status: "success"`, `"busy"`, or `"error"`.

Run artifacts are written to:

```text
~/.local/state/obsidian-process-queue/runs/
```

## n8n Workflow Contract

Give the n8n workflow agent this instruction:

> Create a workflow that calls the host command `$HOME/.local/bin/obsidian-process-queue` over SSH. Set `OBSIDIAN_VAULT` to the synced vault path. Treat stdout as JSON. If `status` is `success`, use `summary_uk` and `counts` for the notification. If `status` is `busy`, send a low-priority skipped notification or do nothing. If `status` is `error`, send an error notification with `summary_uk`, `log_path`, and the first item from `errors`. Do not implement vault logic inside n8n; the runner is the only execution boundary.

Example SSH command:

```bash
OBSIDIAN_VAULT="/path/to/obsidian/vault" "$HOME/.local/bin/obsidian-process-queue"
```
