#!/bin/bash
# Copy skills from ./skills into Claude Code (~/.claude/skills) and/or Codex (~/.agents/skills).
#
#   ./install.sh                     install every skill, Claude only
#   ./install.sh pdf xlsx            install only these
#   ./install.sh --codex             Codex only;  --both for Claude and Codex
#   ./install.sh --dry-run           show what would happen
#   ./install.sh --uninstall         remove everything this script installed
#
# Each installed skill gets a .installed-from marker. Only marked folders are ever
# overwritten or removed, so skills installed by anything else are left alone.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
SRC="$REPO/skills"
MARKER=".installed-from"
CLAUDE_DIR="$HOME/.claude/skills"
CODEX_DIR="$HOME/.agents/skills"

targets=("$CLAUDE_DIR")
dry=0
uninstall=0
names=()
for arg in "$@"; do
  case "$arg" in
    --claude) targets=("$CLAUDE_DIR") ;;
    --codex) targets=("$CODEX_DIR") ;;
    --both) targets=("$CLAUDE_DIR" "$CODEX_DIR") ;;
    --dry-run) dry=1 ;;
    --uninstall) uninstall=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    -*) echo "unknown option: $arg" >&2; exit 1 ;;
    *) names+=("$arg") ;;
  esac
done

run() { if [ "$dry" = 1 ]; then echo "  [dry-run] $*"; else "$@"; fi; }
ours() { [ -f "$1/$MARKER" ] && [ "$(cat "$1/$MARKER")" = "$REPO" ]; }

if [ ${#names[@]} -eq 0 ]; then
  for d in "$SRC"/*/; do [ -f "$d/SKILL.md" ] && names+=("$(basename "$d")"); done
fi

for dest in "${targets[@]}"; do
  echo "== $dest"
  run mkdir -p "$dest"

  # Remove installed skills that are gone from the repo (or everything, on --uninstall).
  for d in "$dest"/*/; do
    [ -d "$d" ] || continue
    d="${d%/}"
    ours "$d" || continue
    if [ "$uninstall" = 1 ] || [ ! -f "$SRC/$(basename "$d")/SKILL.md" ]; then
      echo "  - $(basename "$d")"
      run rm -rf "$d"
    fi
  done
  [ "$uninstall" = 1 ] && continue

  for name in "${names[@]}"; do
    from="$SRC/$name"
    to="$dest/$name"
    if [ ! -f "$from/SKILL.md" ]; then
      echo "  ! $name: no skills/$name/SKILL.md, skipped" >&2
      continue
    fi
    if [ -e "$to" ] && ! ours "$to"; then
      echo "  ! $name: already exists and was not installed by this repo, skipped" >&2
      continue
    fi
    echo "  + $name"
    run rm -rf "$to"
    run cp -R "$from" "$to"
    if [ "$dry" = 0 ]; then echo "$REPO" > "$to/$MARKER"; fi
  done
done

# Hooks are Claude Code only. Registering them in ~/.claude/settings.json is a one-time step (see README).
if [ "$uninstall" = 0 ] && [ -d "$REPO/hooks" ] && [[ " ${targets[*]} " == *" $CLAUDE_DIR "* ]]; then
  echo "== $HOME/.claude/hooks"
  run mkdir -p "$HOME/.claude/hooks"
  for h in "$REPO"/hooks/*; do echo "  + $(basename "$h")"; run cp "$h" "$HOME/.claude/hooks/"; done
fi

[ "$dry" = 1 ] || echo "Done. Start a new Claude Code / Codex session to load the skills."
