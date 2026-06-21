#!/usr/bin/env sh
set -eu

CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
SKILLS_DIR="$CODEX_HOME_DIR/skills"
RUNTIME_DIR="$CODEX_HOME_DIR/obsidian-knowledge-skills"
MANIFEST_PATH="$RUNTIME_DIR/install-manifest.json"

if [ -f "$MANIFEST_PATH" ]; then
  SKILL_NAMES=$(sed -n '/"skills"[[:space:]]*:/,/\]/{/^[[:space:]]*"/{ /":/d; s/^[[:space:]]*"\([^"]*\)".*/\1/p; }}' "$MANIFEST_PATH")
  if [ -z "$SKILL_NAMES" ]; then
    SKILL_NAMES="vault-setup
vault-index
vault-ingest
vault-rules
meeting-prep
internet-research"
  fi
else
  SKILL_NAMES="vault-setup
vault-index
vault-ingest
vault-rules
meeting-prep
internet-research"
fi

printf '%s\n' "$SKILL_NAMES" | while IFS= read -r name; do
  [ -n "$name" ] || continue
  if [ -d "$SKILLS_DIR/$name" ]; then
    rm -rf "$SKILLS_DIR/$name"
    echo "Removed skill $name"
  fi
done

if [ -d "$RUNTIME_DIR" ]; then
  rm -rf "$RUNTIME_DIR"
  echo "Removed runtime $RUNTIME_DIR"
fi
