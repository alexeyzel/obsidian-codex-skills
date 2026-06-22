# Codex Obsidian Knowledge Skills

A small, portable skill suite for maintaining an Obsidian knowledge vault with Codex.

The project is built around one principle: the vault stays human-readable, while the agent handles repetitive filing, retrieval, and summarization. Semantic decisions are made by an LLM through Codex skills. File operations are handled by a deterministic Python engine.

## What It Does

- Initializes a vault from a human-readable `Config.md` contract.
- Processes inbox queue notes and meeting notes through one universal source-ingest flow.
- Creates preparation notes for future meetings from recent relevant context.
- Provides an optional host-side runner for n8n or cron to call the ingest flow through Codex CLI.
- Keeps summaries short, useful, and editable.
- Keeps agent state in service files instead of polluting note bodies.

## What It Does Not Do

- It does not hardcode private folder names, entities, projects, or domains.
- It does not decide note meaning inside Python.
- It does not rewrite user-authored meeting notes.
- It does not create relationship links automatically, but it preserves wikilinks that already existed in source text.
- It does not delete queue notes until all target notes have been updated, summarized, logged, and indexed.

## Core Idea

`Config.md` is the vault contract. It is Markdown, not YAML, so a human can read and edit it comfortably.

The engine reads tables from `Config.md`:

- `Folders`: required folder roles and their paths.
- `Knowledge Types`: user-defined knowledge categories.
- `Note Sections`: section headings and placeholders managed by the agent.
- `Meeting Sections`: headings used when generating the default meeting template.
- `Language Policy`: generated prose and summary language.
- `Templates`: template files for new notes.
- `Processing Limits`: safeguards for context size and batch size.

Paths are intentionally parent-aware so a human does not have to repeat root folder names:

- `queue` is relative to `inbox`;
- `fallback` is relative to `knowledge`;
- knowledge type folders are relative to `knowledge`;
- knowledge type templates are relative to the directory that contains `knowledge_default`;
- template paths are relative to `service`.

For example, changing `knowledge` from `Knowledge` to `KnowledgeBase` automatically makes `Folder = People` resolve to `KnowledgeBase/People`.

The Python engine only performs mechanics:

- scan files;
- build a rebuildable cache;
- prepare JSON tasks for Codex or another LLM runner;
- apply JSON plans;
- insert content into configured sections;
- update frontmatter, logs, state, and indexes.

The LLM performs semantic work:

- inspect a source note's full text, filename topic, and wikilinks;
- decide which topics have useful transferable knowledge;
- resolve each topic to an existing note, new note, fallback, or skip;
- choose a knowledge type when the source template/frontmatter does not specify one;
- follow the configured language policy for generated prose and summaries;
- write one-paragraph summaries from full updated note context;
- draft meeting-prep summaries from recent relevant notes.

## Repository Layout

```text
AGENTS.md                 # repository development instructions
Config.md                 # default vault contract and schema
scripts/
  vault_engine.py         # deterministic file engine
skills/
  vault-rules/            # shared operating rules for the suite
  vault-setup/            # initialize a vault
  vault-index/            # rebuild cache and search index
  vault-ingest/           # queue + meeting ingest workflow
  meeting-prep/           # create future meeting notes
  internet-research/      # placeholder for the later research workflow
docs/
  architecture.md
  method.md
  operations.md
  schema.md
host-runner/
  obsidian-process-queue.py  # optional n8n/cron wrapper around Codex CLI + engine
evals/
  evals.json
install.sh
install.ps1
uninstall.sh
uninstall.ps1
```

## Vault Method

Primary sources:

- inbox queue notes;
- meeting notes.

Rules:

- user-authored source material is preserved as knowledge, not silently discarded;
- meeting notes are never deleted or renamed;
- queue notes are deleted only after full source coverage and current summaries for every target note;
- knowledge notes are the normal write surface for the agent;
- unclear but meaningful notes go to the configured fallback folder;
- truly unprocessable queue notes remain in queue with a compact `Agent note` explaining why.
- source wikilinks are preserved when source-authored text is transferred into knowledge notes.

Knowledge notes use two agent-managed areas:

- a summary section, normally `## Summary`;
- a user-notes section, normally `## My notes`.

Templates mark insertion points with:

```text
{agent_summary}
{user_notes}
```

Existing notes do not need to keep those placeholders. After first write, the engine finds sections by the headings configured in `Config.md`.

Templates also include a manual related section by default. It has no placeholder, so the agent does not populate it automatically.

## Basic Usage

Install first. The installer copies both the skills and the deterministic runtime into `CODEX_HOME`, so a production server does not need commands to run from the repository checkout.

Installed runtime paths:

- macOS/Linux: `${CODEX_HOME:-$HOME/.codex}/obsidian-knowledge-skills/scripts/vault_engine.py`
- Windows: `$env:CODEX_HOME\obsidian-knowledge-skills\scripts\vault_engine.py`, or `$HOME\.codex\obsidian-knowledge-skills\scripts\vault_engine.py` when `CODEX_HOME` is not set.

For local development from this repository, `scripts/vault_engine.py` is also valid.

Set the engine path once per shell session.

macOS or Linux:

```bash
ENGINE="${CODEX_HOME:-$HOME/.codex}/obsidian-knowledge-skills/scripts/vault_engine.py"
```

Windows PowerShell:

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$engine = Join-Path $codexHome "obsidian-knowledge-skills\scripts\vault_engine.py"
```

Initialize a vault:

```bash
cp Config.md /path/to/vault/Config.md
# Edit /path/to/vault/Config.md before init if you want different language, folders, sections, or knowledge types.
python "$ENGINE" init --vault /path/to/vault
```

Rebuild cache and index:

```bash
python "$ENGINE" index --vault /path/to/vault
```

Generate queue ingest tasks:

```bash
python "$ENGINE" queue-tasks --vault /path/to/vault --limit 20 > queue-tasks.json
```

Apply an LLM ingest plan:

```bash
python "$ENGINE" apply-plan --vault /path/to/vault --input ingest-plan.json
```

Generate and apply summary tasks:

```bash
python "$ENGINE" summary-tasks --vault /path/to/vault --limit 50 > summary-tasks.json
python "$ENGINE" apply-summaries --vault /path/to/vault --input summaries.json
```

Finalize processed queue notes:

```bash
python "$ENGINE" finalize-queue --vault /path/to/vault
```

Generate meeting ingest tasks:

```bash
python "$ENGINE" meeting-tasks --vault /path/to/vault --limit 20 > meeting-tasks.json
```

Create a future meeting note:

```bash
python "$ENGINE" meeting-prep-task --vault /path/to/vault --calendar-title "Weekly sync" --date 2026-06-22 > meeting-prep-task.json
python "$ENGINE" apply-meeting-prep --vault /path/to/vault --input meeting-prep-plan.json
```

## Installing Skills

macOS or Linux:

```bash
./install.sh
```

Windows PowerShell:

```powershell
.\install.ps1
```

If local execution policy blocks scripts:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

The installer copies:

- skill directories into `$CODEX_HOME/skills`;
- runtime files into `$CODEX_HOME/obsidian-knowledge-skills`.
- the optional host runner into `$CODEX_HOME/obsidian-knowledge-skills/host-runner`.

It does not modify an existing production vault. Vault configuration lives in that vault's own `Config.md`.

## n8n Host Runner

For unattended n8n or cron execution, expose the installed host runner as one command on the machine that has the synced Markdown vault:

```bash
mkdir -p "$HOME/.local/bin"
install -m 700 \
  "${CODEX_HOME:-$HOME/.codex}/obsidian-knowledge-skills/host-runner/obsidian-process-queue.py" \
  "$HOME/.local/bin/obsidian-process-queue"
```

Then n8n can call only this SSH command:

```bash
OBSIDIAN_VAULT="/path/to/obsidian/vault" "$HOME/.local/bin/obsidian-process-queue"
```

The runner prints one JSON object to stdout with `status`, `summary_uk`, counts, changed notes, skipped items, and errors. See `host-runner/README.md` for the full contract.

## Updating

On a server or another machine, keep a clone of this repository only as the update source:

```bash
git pull --ff-only
./install.sh
```

On Windows:

```powershell
git pull --ff-only
.\install.ps1
```

After reinstalling, Codex skills and n8n jobs keep using the same installed runtime path under `CODEX_HOME`.

## Uninstalling

macOS or Linux:

```bash
./uninstall.sh
```

Windows PowerShell:

```powershell
.\uninstall.ps1
```

If local execution policy blocks scripts:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
```

Uninstall removes only this suite's installed skill folders and `$CODEX_HOME/obsidian-knowledge-skills`. It does not remove vaults or vault notes.

## Documentation

- `docs/architecture.md`: engine and skill responsibilities.
- `docs/method.md`: human-first vault method.
- `docs/schema.md`: `Config.md` table contract and JSON plan shapes.
- `docs/operations.md`: practical command sequences.
