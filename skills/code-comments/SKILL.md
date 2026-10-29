---
name: code-comments
description: Use when writing or reviewing code comments, when the code-comments hook denies an edit, when a diff or codebase is full of comments that restate the code, narrate the change, or hold commented-out code, when asked to clean up or reduce comments, or when deciding whether a comment or doc comment earns its place.
---

# Code comments

A comment earns its place only when it says something the code cannot. The code already says
*what* and *how*; a comment is for the *why*, a constraint, a unit, a reference, a warning.
Ousterhout's test: a comment must sit at a different level than the code, higher (intent, a
domain rule) or lower (precision: units, bounds, null, thread-safety). A comment at the same
level repeats the code and rots the moment the code changes.

## What the hook flags

| Kind | Looks like | Do instead |
|---|---|---|
| restating | `// validate the input` above `if (!input) throw` | delete, or name the reason the input can be missing |
| restating doc | `/** Gets the name. */`, `<param name="id">The id.</param>` | say what the signature cannot: errors, side effects, units, null, ordering; or drop it |
| narration | `// updated to use the new API`, `// here we store the list` | delete; the commit message carries the change |
| commented-out code | `// const old = compute(x);` | delete; git has it |
| banner, end marker | `// ------ helpers ------`, `} // end if` | delete; split the file if it needs sections |
| density | more than 3 comment lines in 10 (advisory only) | keep the why lines, cut the what lines |

Always kept: license headers, tool directives (`eslint-disable`, `noqa`, `pragma`), `TODO`/`FIXME`
with an owner or ticket, URLs and ticket ids, `Arrange`/`Act`/`Assert`, `#region`, JSDoc tags
that carry text.

## Replace the comment with code

Fowler lists "Comments" as a smell, with the refactorings that remove the need:

- explains a block: **Extract Function**, the comment becomes the name
- explains an expression: **Extract Variable**, same
- states a precondition: **Introduce Assertion**, or a guard that throws
- gives a unit or range: the type (`Milliseconds`, an enum instead of `// 1 = active`) or the name (`timeoutMs`)
- explains a magic number: a named constant
- explains behaviour: a test whose name states it
- records a decision: the commit message, or an ADR when it crosses files

Stays a comment: a business rule the code only implements, a workaround with the bug it works
around, a non-obvious consequence ("closing this also flushes the queue"), why the obvious
alternative was not taken, a spec or ticket reference.

## When the hook denies an edit

Resubmit the same edit without the listed lines. Do not pad a *what* comment into longer prose:
the check scores word overlap with the next code line, so a genuine why passes once it names the
reason. A mandated doc comment (CS1591, `require-jsdoc`) passes when its summary says more than
the name.

## Review and cleanup

`scripts/` is inside this skill's directory (the base directory announced when the skill loads,
normally `~/.claude/skills/code-comments/`); use that absolute path from anywhere.

```bash
python3 scripts/comments.py src/               # flagged comments and files over 30% comment lines; exit 1 if any
python3 scripts/comments.py --ratio 0.2 file.ts
```

Delete what it lists, then read the rest once: anything paraphrasing the next line goes too.
Keep doc blocks that add information. Sources, existing lint rules (Ruff `ERA001`, Sonar `S125`,
ESLint `no-warning-comments`) and a CLAUDE.md line for other agents: `reference.md`.

## Hook

`hooks/code-comments.py` in this repo is the same script, PreToolUse on `Edit|Write|MultiEdit`.
It applies the edit in memory, judges only the comment lines the edit adds, and denies the edit
with the list as the reason. Moved or unchanged comments are never flagged; density alone is
advisory. `CODE_COMMENTS_MODE=warn` makes it advisory, `off` disables it; `CODE_COMMENTS_MAX_RATIO`
sets the density limit. It guards the edit tools only: a file written through Bash bypasses it. Codex has no
hooks; it gets the skill text only.
