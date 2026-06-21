#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
SKILLS_DIR="$CODEX_HOME_DIR/skills"
RUNTIME_DIR="$CODEX_HOME_DIR/obsidian-knowledge-skills"

mkdir -p "$SKILLS_DIR"
SKILL_NAMES=""
for skill in "$SCRIPT_DIR"/skills/*; do
  [ -d "$skill" ] || continue
  name=$(basename "$skill")
  SKILL_NAMES="${SKILL_NAMES}
$name"
  rm -rf "$SKILLS_DIR/$name"
  cp -R "$skill" "$SKILLS_DIR/"
done

rm -rf "$RUNTIME_DIR"
mkdir -p "$RUNTIME_DIR/scripts"
cp "$SCRIPT_DIR/scripts/vault_engine.py" "$RUNTIME_DIR/scripts/"
cp "$SCRIPT_DIR/Config.md" "$RUNTIME_DIR/"

{
  printf '{\n'
  printf '  "name": "codex-obsidian-knowledge-skills",\n'
  printf '  "installed_at": "%s",\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  printf '  "skills": [\n'
  first=1
  printf '%s\n' "$SKILL_NAMES" | while IFS= read -r name; do
    [ -n "$name" ] || continue
    if [ "$first" -eq 1 ]; then
      first=0
    else
      printf ',\n'
    fi
    printf '    "%s"' "$name"
  done
  printf '\n  ],\n'
  printf '  "runtime_dir": "%s"\n' "$RUNTIME_DIR"
  printf '}\n'
} > "$RUNTIME_DIR/install-manifest.json"

echo "Installed skills to $SKILLS_DIR"
echo "Installed runtime to $RUNTIME_DIR"
