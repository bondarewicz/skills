# skills

My personal skills and hooks for Claude Code (and Codex).

## Contents

| Path | What it is |
|---|---|
| `skills/experiment-loop/` | `/experiment-loop <goal>`: Karpathy-style autoresearch loop for any repo. Locked scorer, test gate, noise-aware keep-or-undo judge, budget. Manual-only. |
| `hooks/confirm-git.py` | Before the first file change in a git repo, Claude must ask how commits are authored: **Me only, GPG signed** or **Me + Claude, unsigned**. The answer is recorded by the hook itself, and every commit is checked against it. Commit messages must be [Conventional Commits](https://www.conventionalcommits.org): the check is delegated to `hooks/conventional-commits.py` when it is installed beside this file, else a built-in subset applies (a breaking change needs both `!` in the header and a `BREAKING CHANGE:` footer). Every `git commit` / `git push` shows a confirmation prompt (repo, branch, remote, author, message, local vs push, and why), even in auto mode. |
| `skills/cognitive-complexity/` | SonarSource's [Cognitive Complexity](https://www.sonarsource.com/docs/CognitiveComplexity.pdf) (Sonar rule S3776): the rules, how to lower a score, and `scripts/cogc.py`, a zero-dependency scorer. Python exact via the AST; JS/TS, Java, C#, Go, Rust, C/C++, Kotlin, Swift, PHP, Dart, Scala, Groovy via a tokenizer, verified against the paper's worked examples (`scripts/test_cogc.py`). `python3 scripts/cogc.py --explain file.ts` shows every increment; a directory lists only functions over 15 and exits 1. |
| `hooks/cognitive-complexity.py` | Symlink to the scorer above. PreToolUse on `Edit\|Write\|MultiEdit` snapshots each function's score, PostToolUse reports functions over 15 that the edit created or made worse, with the old score. Advisory only (never blocks), silent otherwise, skips test files. Limit: `COGNITIVE_COMPLEXITY_LIMIT`. |
| `skills/code-comments/` | When a comment earns its place (the why the code cannot show) and when it does not, with the refactorings that replace a comment (Fowler's "Comments" smell, Ousterhout's level-of-detail rule) and `scripts/comments.py`, a zero-dependency checker that flags comments restating the next line, change narration, commented-out code, banners, end markers and doc comments that only repeat the signature. C-family languages, Python (exact via `tokenize`, docstrings included), shell/Ruby. `python3 scripts/comments.py src/` lists them and exits 1. Tests: `scripts/test_comments.py` (TS, C#, Python). |
| `hooks/code-comments.py` | Symlink to the checker above. PreToolUse on `Edit\|Write\|MultiEdit`: applies the edit in memory, judges only the comment lines the edit adds, and **denies** the edit with the list as the reason, so the agent resubmits without them. Moved or unchanged comments are never flagged; comment density alone is advisory. `CODE_COMMENTS_MODE=warn` makes it advisory, `off` disables; `CODE_COMMENTS_MAX_RATIO` sets the density limit (0.3). Guards the edit tools only: a file written through Bash bypasses it. Register it after `install.sh` has copied the script, because a missing hook script blocks every edit. |
| `skills/conventional-commits/` | [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/): the structure, the types and what they mean for SemVer, how to write the description, body and footers, breaking changes, fixing a wrong type, plus the full specification and FAQ in `reference.md`. House rules on top: lowercase type from a fixed list, and a breaking change carries both `!` and a `BREAKING CHANGE:` footer. `scripts/cc.py` validates one message (`-m`), a message file, or a range (`--range origin/main..HEAD`); `--spec` checks the specification alone. Tests: `scripts/test_cc.py`, including the spec's own examples. |
| `hooks/conventional-commits.py` | Symlink to the validator above. Two uses: `hooks/confirm-git.py` imports it to check every `git commit` Claude runs; and it is a git `commit-msg` hook for everyone else, human or agent, in any tool: `ln -s ~/.claude/hooks/conventional-commits.py .git/hooks/commit-msg` in a repo. A rejected message stays in `.git/COMMIT_EDITMSG`. |
| `skills/estimates/` | Estimates for work Claude does itself, from measured turns instead of human units. `scripts/estimates.py` splits every transcript in `~/.claude/projects` into turns (one per prompt) and records active and idle minutes, lines written (edit tools and Bash heredocs), tool calls and test runs in `~/.claude/state/estimates/ledger.jsonl`, then prints a pace table by size class (XS to XL by lines written: median and p90 active minutes). The skill fixes the estimate line: Claude's minutes as the class's median to p90 with n, the user's minutes separately. `--recent` shows actuals, `--check` runs the detector. Tests: `scripts/test_estimates.py`. |
| `hooks/estimates.py` | Symlink to the script above. SessionStart prints the pace table and the rule, seeding the ledger from past transcripts on first run. Stop logs the finished turn, then scans the reply for an estimate in human units (hours, `2h`, days, half a day, an afternoon, weeks, sprints) next to an estimate word and **blocks**, with the table and the exact line shape as the reason, so the reply continues with the corrected estimate in measured minutes. A correction that carries no number is blocked once more, then the hook lets go. Past tense, timeouts and schedules, and sentences naming a human doer pass. `ESTIMATES_MODE=warn` shows the user a notice instead, `off` only logs. |
| `skills/ddd/` | Domain-Driven Design in C#: the tactical rules Claude applies in a `Domain` folder or `*.Domain` project (dependency rule, aggregate rules, value objects, domain events, repositories, a refuse list), `reference.md` for the strategic side (subdomains, context maps, balancing coupling, sources), and `scripts/ddd.py`, a zero-dependency scanner: `python3 scripts/ddd.py src/` lists every forbidden `using` in domain code and exits 1. |
| `hooks/ddd.py` | Symlink to the scanner above. SessionStart loads the skill's rules when the repo has a `Domain` folder or `*.Domain` project, silent otherwise. PreToolUse on `Edit\|Write\|MultiEdit` applies the edit in memory and **denies** it when it adds a `using` the domain layer must not depend on (EF Core, AspNetCore, Microsoft.Extensions, MediatR, AutoMapper, System.IO, another layer's namespace, ...); usings already in the file never block. `DDD_MODE=warn` makes it advisory, `off` disables; `DDD_ALLOW=MediatR,System.IO` allowlists. |
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
      { "matcher": "Edit|Write|MultiEdit", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/cognitive-complexity.py" }] },
      { "matcher": "Edit|Write|MultiEdit", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/code-comments.py" }] },
      { "matcher": "Edit|Write|MultiEdit", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/ddd.py" }] }
    ],
    "PostToolUse": [
      { "matcher": "AskUserQuestion", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/confirm-git.py" }] },
      { "matcher": "Edit|Write|MultiEdit", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/cognitive-complexity.py" }] }
    ],
    "SessionStart": [
      { "matcher": "startup|resume|clear|compact", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/adhd-mode.py", "timeout": 300 }] },
      { "matcher": "startup|resume|clear|compact", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/estimates.py" }] },
      { "matcher": "startup|resume|clear|compact", "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/ddd.py" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/estimates.py" }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "python3 -I ~/.claude/hooks/adhd-mode.py" }] }
    ]
  }
}
```

Start a new session after installing.
