---
name: conventional-commits
description: Use when writing or amending a git commit message, when the confirm-git hook or the conventional-commits commit-msg hook rejects one, when choosing a type or scope or deciding whether a change is breaking, when splitting work into commits, or when reading history for a changelog or a release. Conventional Commits 1.0.0 plus this repo's house rules.
---

# Conventional Commits

A commit message is a line a release tool can parse and a human can scan:

```
<type>[(scope)][!]: <description>

[body: why, one blank line after the description]

[footers: Token: value, one blank line after the body]
```

## Types, and what they mean for SemVer

| Type | Use for | Release |
|---|---|---|
| `feat` | a new capability for the user of the code | MINOR |
| `fix` | a bug fix | PATCH |
| `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert` | everything else, named by intent | none |
| any type with `!` and a `BREAKING CHANGE:` footer | an incompatible change | MAJOR |

A change that is both `feat` and `fix` is two commits. A `refactor` that changes behaviour is not
a refactor. `revert` takes the reverted header as description and `Refs: <sha>` as a footer.

## Writing one

- **Description:** imperative, what changed, no trailing period, fits in 72 columns.
  `fix(parser): accept trailing commas`, not `Fixed parser bug`.
- **Scope:** a noun for the part touched: `api`, `auth`, `deps`, a package name. Omit it when the
  change spans the codebase. Do not invent a new scope for one commit.
- **Body:** the why and the consequence, not a list of what the diff already shows. Starts one blank
  line after the description.
- **Footers:** git trailers after a blank line: `Refs: #123`, `Reviewed-by: name`,
  `Co-Authored-By: name <email>`. Tokens use `-` for spaces. A body sentence like `Note: ...` is
  fine; a footer section starts only after the last blank line.
- **Breaking change:** `!` before the colon **and** a footer `BREAKING CHANGE: what breaks and how
  to migrate` (uppercase, `BREAKING-CHANGE` is the synonym). The spec allows either; this repo
  requires both, so the header shows it and tools can read it.

## House rules on top of the spec

Lowercase type from the table above; the spec allows any noun in any case, and says be consistent.
Breaking changes carry both signals. A body that says "breaking change" without them is rejected.
`--spec` on the validator checks the specification alone.

## Fixing one

- Wrong type before push: `git commit --amend`, or `git rebase -i` for older ones.
- A rejected commit keeps its text in `.git/COMMIT_EDITMSG`; `git commit --edit --file=.git/COMMIT_EDITMSG` reopens it.
- Wrong type after push: leave it; rewriting shared history costs more than a mis-typed line.

## Check

`scripts/` is inside this skill's directory (the base directory announced when the skill loads,
normally `~/.claude/skills/conventional-commits/`); use that absolute path from anywhere.

```bash
python3 scripts/cc.py -m "feat(api)!: drop v1 routes"       # one message; exit 1 with each problem
python3 scripts/cc.py --range origin/main..HEAD              # a branch before a PR
python3 scripts/cc.py --spec -m "Deploy: anything"           # specification only
```

Full specification, the FAQ and the spec's examples: `reference.md`.

## Hooks

Two hooks share the validator in `scripts/cc.py`:

- **Claude Code:** `hooks/confirm-git.py` (PreToolUse on Bash) blocks a `git commit` whose message
  fails `validate()`, with the problems as the reason, before the command runs.
- **git itself:** `hooks/conventional-commits.py` is the same script as `scripts/cc.py` and works
  as a `commit-msg` hook for every committer, human or agent, in any tool:
  `ln -s ~/.claude/hooks/conventional-commits.py .git/hooks/commit-msg` in a repo.
