---
name: vault-index
description: Refresh the generic Obsidian vault search cache and human index. Use before ingest, meeting preparation, research, or any task that needs candidate retrieval across configured knowledge and meeting folders.
---

# Vault Index

Resolve `ENGINE` to the installed engine at `${CODEX_HOME:-$HOME/.codex}/obsidian-knowledge-skills/scripts/vault_engine.py`. If working from a repository checkout, local `scripts/vault_engine.py` is also valid.

Run:

```bash
python "$ENGINE" index --vault "/path/to/vault"
```

For candidate search:

```bash
python "$ENGINE" search --vault "/path/to/vault" --query "query" --all
```

Search results are candidates only. The LLM must still decide type, target, relevance, and summary.
