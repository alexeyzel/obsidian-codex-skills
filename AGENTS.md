# Codex Obsidian Knowledge Skills Development

This repository contains a portable Codex skill suite and deterministic helper engine for maintaining Obsidian knowledge vaults.

## Repository Rules

- Keep this repository generic and publishable.
- Do not add private names, private projects, private examples, or user-specific vault paths.
- Do not hardcode knowledge categories, folder names, section labels, or domain assumptions in Python or skills.
- Put the default vault-agent configuration in `Config.md`, not in this file.
- Treat `AGENTS.md` as the development contract for this repository only.
- Treat `Config.md` as the default vault contract copied into new vaults and installed runtime.
- Keep note bodies clean and human-readable; keep process state in service files.
- Prefer deterministic Python for file mechanics and LLM/Codex skills for semantic decisions.
- Preserve portability across Windows and Linux.

## Project Layout

| Path | Purpose |
|---|---|
| `Config.md` | Default configurable contract for the vault maintenance agent. |
| `scripts/vault_engine.py` | Deterministic engine for file mechanics, task generation, and plan application. |
| `skills/` | Codex skills that call the installed runtime and perform semantic LLM work. |
| `host-runner/` | Optional host-side wrappers for n8n, cron, or other schedulers. |
| `docs/` | Public documentation for architecture, schema, operations, and method. |
| `tests/` | Unit tests for the deterministic engine. |

## Development Rules

- Use `apply_patch` for manual file edits.
- Run tests after engine, config, installer, or skill changes.
- Keep installers copying both skills and runtime into `CODEX_HOME`.
- Keep `install.sh` and `uninstall.sh` valid POSIX shell.
- Keep `.sh` files LF and `.ps1` files CRLF via `.gitattributes`.
- Do not delete or rewrite user vault data from this repository tooling.
- If a config change affects generated vault structure, add or update tests.

## Validation

Run:

```bash
python -B -m unittest discover -s tests -v
python -m json.tool evals/evals.json
```

On Windows with Git Bash available, also run:

```bash
bash -n install.sh
bash -n uninstall.sh
```
