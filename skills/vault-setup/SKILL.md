---
name: vault-setup
description: Initialize a new Obsidian vault from the Markdown configuration in Config.md. Use when the user wants to create vault folders, service state, templates, or prepare a vault for Codex CLI/n8n maintenance.
---

# Vault Setup

Use vault `Config.md` as the configuration source.

Resolve `ENGINE` to the installed engine at `${CODEX_HOME:-$HOME/.codex}/obsidian-knowledge-skills/scripts/vault_engine.py`. If working from a repository checkout, local `scripts/vault_engine.py` is also valid.

Procedure:

1. Resolve the vault path.
2. Run:

   ```bash
   python "$ENGINE" init --vault "/path/to/vault"
   ```

3. Build the index:

   ```bash
   python "$ENGINE" index --vault "/path/to/vault"
   ```

4. Report created folders, templates, and service state.

Do not overwrite templates unless the user explicitly asks; then pass `--overwrite-templates`.
