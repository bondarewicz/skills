# skills

My personal skills and hooks for Claude Code (and Codex).

## Contents

| Path | What it is |
|---|---|
| `skills/experiment-loop/` | `/experiment-loop <goal>`: Karpathy-style autoresearch loop for any repo. Locked scorer, test gate, noise-aware keep-or-undo judge, budget. Manual-only. |
| `hooks/confirm-git.py` | `PreToolUse` hook: every `git commit` / `git push` shows a confirmation prompt (repo, branch, remote, message, local vs push, and why), even in auto mode. |
| `install.sh` | Copies skills into `~/.claude/skills` (and/or Codex's `~/.agents/skills`) and hooks into `~/.claude/hooks`. |

## Install

```bash
./install.sh            # Claude Code: skills + hooks
./install.sh --both     # also Codex (~/.agents/skills)
./install.sh --dry-run  # preview
./install.sh --uninstall
```

Only folders the script installed (marked with `.installed-from`) are ever overwritten or removed.

Hooks also need a one-time entry in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/confirm-git.py" }] }
    ]
  }
}
```

Start a new session after installing.
