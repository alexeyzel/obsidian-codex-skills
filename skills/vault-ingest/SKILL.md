---
name: vault-ingest
description: Process Obsidian queue notes and unprocessed meeting notes into configured knowledge notes. Use when the user asks to ingest, process Inbox/Queue, process new meetings, update the knowledge base, or run the n8n/Codex maintenance job.
---

# Vault Ingest

Read `AGENTS.md` and `skills/vault-rules/SKILL.md`.

Resolve `ENGINE` to the installed engine at `${CODEX_HOME:-$HOME/.codex}/obsidian-knowledge-skills/scripts/vault_engine.py`. If working from a repository checkout, local `scripts/vault_engine.py` is also valid.

## Universal Source Flow

Queue notes and meeting notes use the same JSON action shape. The commands differ only in which source folder they scan and which source policy they assign.

For every task:

- read the full `source_text`;
- follow `language_policy` for generated prose and summaries;
- follow `operating_rules` for target titles;
- inspect the filename topic and all wikilinks in `topic_candidates`;
- decide which topics have useful transferable knowledge;
- resolve each target as existing, new, fallback, or skipped;
- return one `updates[]` item per useful topic;
- set `coverage: complete` only when all useful source content is represented in updates or explicitly ignored as non-durable knowledge;
- do not invent relationship links.

For every target update:

- preserve useful Markdown structure;
- shorten or paraphrase only when it makes the target note cleaner;
- preserve proper names, official titles, acronyms, emails, and established mixed-language names;
- use fallback when the topic is meaningful but no configured type fits.

## Queue Sources

1. Generate tasks:

   ```bash
   python "$ENGINE" queue-tasks --vault "/path/to/vault" --limit 20 > queue-tasks.json
   ```

2. As the LLM, produce `ingest-plan.json`:
   - return actions with `kind: source`;
   - keep `source_policy: delete_after_success`;
   - use `template_type` for the filename topic when it becomes a new note;
   - choose existing target only when identity is clear;
   - return `updates[]`;
   - set `coverage` accurately.

3. Apply:

   ```bash
   python "$ENGINE" apply-plan --vault "/path/to/vault" --input ingest-plan.json
   ```

4. Generate and apply one-paragraph summaries:

   ```bash
   python "$ENGINE" summary-tasks --vault "/path/to/vault" --limit 50 > summary-tasks.json
   python "$ENGINE" apply-summaries --vault "/path/to/vault" --input summaries.json
   ```

5. Finalize queue:

   ```bash
   python "$ENGINE" finalize-queue --vault "/path/to/vault"
   ```

Queue notes are deleted only after all target summaries are current.

## Meeting Sources

1. Generate tasks:

   ```bash
   python "$ENGINE" meeting-tasks --vault "/path/to/vault" --limit 20 > meeting-tasks.json
   ```

2. As the LLM, produce `meeting-plan.json`:
   - return actions with `kind: source`;
   - keep `source_policy: keep_and_mark_processed`;
   - if `has_summary_placeholder` is true, provide `source_summary` as one useful paragraph;
   - return `updates[]` only for topics with clearly relevant text;
   - set `coverage` accurately.

3. Apply the plan, then run the same summary pass as above.

Meeting notes are never deleted or renamed.
