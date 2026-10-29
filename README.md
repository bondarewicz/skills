# skills

My personal skills and hooks for Claude Code (and Codex).

## Contents

| Path | What it is |
|---|---|
| `skills/experiment-loop/` | `/experiment-loop <goal>`: Karpathy-style autoresearch loop for any repo. Locked scorer, test gate, noise-aware keep-or-undo judge, budget. Manual-only. |
| `hooks/confirm-git.py` | Before the first file change in a git repo, Claude must ask how commits are authored: **Me only, GPG signed** or **Me + Claude, unsigned**. The answer is recorded by the hook itself, and every commit is checked against it. Commit messages must be [Conventional Commits](https://www.conventionalcommits.org); a breaking change needs both `!` in the header and a `BREAKING CHANGE:` footer. Every `git commit` / `git push` shows a confirmation prompt (repo, branch, remote, author, message, local vs push, and why), even in auto mode. |
| `skills/cognitive-complexity/` | SonarSource's [Cognitive Complexity](https://www.sonarsource.com/docs/CognitiveComplexity.pdf) (Sonar rule S3776): the rules, how to lower a score, and `scripts/cogc.py`, a zero-dependency scorer. Python exact via the AST; JS/TS, Java, C#, Go, Rust, C/C++, Kotlin, Swift, PHP, Dart, Scala, Groovy via a tokenizer, verified against the paper's worked examples (`scripts/test_cogc.py`). `python3 scripts/cogc.py --explain file.ts` shows every increment; a directory lists only functions over 15 and exits 1. |
| `hooks/cognitive-complexity.py` | Symlink to the scorer above. PreToolUse on `Edit\|Write\|MultiEdit` snapshots each function's score, PostToolUse reports functions over 15 that the edit created or made worse, with the old score. Advisory only (never blocks), silent otherwise, skips test files. Limit: `COGNITIVE_COMPLEXITY_LIMIT`. |
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
      { "matcher": "Bash|Edit|Write|NotebookEdit", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/confirm-git.py" }] },
      { "matcher": "Edit|Write|MultiEdit", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/cognitive-complexity.py" }] }
    ],
    "PostToolUse": [
      { "matcher": "AskUserQuestion", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/confirm-git.py" }] },
      { "matcher": "Edit|Write|MultiEdit", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/cognitive-complexity.py" }] }
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
