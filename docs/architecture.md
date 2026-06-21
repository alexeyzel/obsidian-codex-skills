# Architecture

The system has two layers.

## Deterministic Engine

`scripts/vault_engine.py` performs file mechanics only:

- parse Markdown tables from `Config.md`;
- create configured folders and templates;
- scan Markdown files and build a rebuildable cache;
- generate universal source JSON tasks for LLM planning;
- apply JSON plans safely;
- insert text into configured placeholders or sections;
- update summary state, queue state, logs, and index files.

The engine does not classify real-world entities, infer note types, decide whether notes are duplicates, or write summaries on its own.

In production, installers copy this engine to `$CODEX_HOME/obsidian-knowledge-skills/scripts/vault_engine.py`. The repository checkout is the update source; the installed runtime path is what Codex skills and automation jobs should call.

## LLM Skills

Codex skills perform semantic work:

- inspect a source note's full text, filename topic, and wikilinks;
- decide which topics have useful transferable knowledge;
- decide whether each topic updates an existing note, creates a new note, uses fallback, or is skipped;
- choose a configured knowledge type when a template/frontmatter type did not specify one;
- write one-paragraph summaries from full updated note context;
- prepare future meeting notes from recent relevant context.

## Configuration

`Config.md` is the vault configuration contract. It is intentionally Markdown, not YAML. The default file groups user-facing labels under `Language and Labels`, and the engine reads tables by heading:

- `Folders`;
- `Knowledge Types`;
- `Note Sections`;
- `Meeting Sections`;
- `Language Policy`;
- `Templates`;
- `Processing Limits`;
- `Operating Rules`.

Users may change paths, templates, section headings, limits, and knowledge types without editing Python.

## Service State

The service folder is configured in `Config.md`. The engine creates internal subfolders:

```text
Service/
  Templates/
  cache/
  log/
  state/
```

Files under `cache/` are rebuildable. Files under `state/` track queue and summary completion.

## Source Policies

Queue notes and meeting notes use the same ingest plan shape. They differ only by source policy:

- `delete_after_success`: queue source; delete only after full coverage and current summaries for all target notes.
- `keep_and_mark_processed`: meeting source; never delete or rename, fill the meeting summary placeholder when present, then set `agent_processed: true`.
