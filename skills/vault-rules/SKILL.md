---
name: vault-rules
description: Shared rules for the generic Obsidian vault maintainer. Use when any vault skill needs the configured folder roles, knowledge types, note sections, template placeholders, source preservation rules, queue deletion rules, or meeting safety rules.
---

# Vault Rules

Read `AGENTS.md` first. Treat it as the vault contract.

Core rules:

- Use folder roles and paths from `AGENTS.md`; do not hardcode folder names.
- Use configured knowledge types from `AGENTS.md`; do not hardcode type names.
- Follow configured `Language Policy` for generated prose and summaries.
- Follow configured `Operating Rules` for new note titles.
- Preserve proper names, official names, acronyms, emails, and established mixed-language names.
- Manage only configured section roles: `summary` and `user_notes`.
- Do not manage related links or relationship sections.
- Use one universal source ingest flow for queue notes and meeting notes.
- Inspect the full source text, filename topic, and wikilinks before deciding updates.
- A source may produce zero, one, or many target updates.
- Queue notes may be deleted only after full source coverage and current summary state for all target notes.
- Meeting notes are never deleted or renamed.
- Process only meetings where `agent_processed` is missing or false.
- If a meeting still contains the configured summary placeholder, write one paragraph into it.
- Set `agent_processed: true` only after meeting ingest succeeds.
- If a queue note cannot be processed, leave it in queue and append a compact `Agent note`.
- If a note is meaningful but no configured type fits, use the configured fallback folder.
- Summaries are one paragraph written from the full updated target note.

Use the deterministic engine for file mechanics.

Before running engine commands, resolve `ENGINE` to the installed runtime path. Preferred path after install:

```text
${CODEX_HOME:-$HOME/.codex}/obsidian-knowledge-skills/scripts/vault_engine.py
```

If working from a repository checkout, local `scripts/vault_engine.py` is also valid.
