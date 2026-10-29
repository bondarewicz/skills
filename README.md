# skills

My personal skills and hooks for Claude Code (and Codex).

## Contents

| Path | What it is |
|---|---|
| `skills/experiment-loop/` | `/experiment-loop <goal>`: Karpathy-style autoresearch loop for any repo. Locked scorer, test gate, noise-aware keep-or-undo judge, budget. Manual-only. |
| `hooks/confirm-git.py` | Before the first file change in a git repo, Claude must ask how commits are authored: **Me only, GPG signed** or **Me + Claude, unsigned**. The answer is recorded by the hook itself, and every commit is checked against it. Commit messages must be [Conventional Commits](https://www.conventionalcommits.org); a breaking change needs both `!` in the header and a `BREAKING CHANGE:` footer. Every `git commit` / `git push` shows a confirmation prompt (repo, branch, remote, author, message, local vs push, and why), even in auto mode. |
| `hooks/adhd-mode.py` | Keeps the [i-have-adhd](https://github.com/ayghri/i-have-adhd) skill on in every session. At session start it installs the plugin if missing and loads its rules; each prompt gets a one-line reminder. A message of just `stop adhd mode` (or `normal mode`) turns it off for all sessions; `start adhd mode` or `/i-have-adhd` turns it back on. |
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
      { "matcher": "Bash|Edit|Write|NotebookEdit", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/confirm-git.py" }] }
    ],
    "PostToolUse": [
      { "matcher": "AskUserQuestion", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/confirm-git.py" }] }
    ],
    "SessionStart": [
      { "matcher": "startup|resume|clear|compact", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/adhd-mode.py", "timeout": 300 }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/adhd-mode.py" }] }
    ]
  }
}
```

Start a new session after installing.
