# Code comments: sources and the wider guard

## Where the rules come from

- John Ousterhout, *A Philosophy of Software Design*, ch. 13 "Comments Should Describe Things
  that Aren't Obvious from the Code": a comment at the same level of detail as the code is noise;
  write at a higher level (intent, invariants) or a lower one (units, bounds, nullability).
  Red flag "Comment repeats code". Ch. 15 argues for writing interface comments first as a design
  tool, which is the one case where a doc comment is worth more than the signature.
- Martin Fowler and Kent Beck, *Refactoring*, the "Comments" smell: "when you feel the need to
  write a comment, first try to refactor the code so that any comment becomes superfluous".
  Remedies: Extract Function, Extract Variable, Introduce Assertion, Rename.
- Robert C. Martin, *Clean Code*, ch. 4. Good: legal, informative, explanation of intent,
  clarification, warning of consequences, TODO, amplification, public API docs. Bad: redundant,
  misleading, mandated, journal, noise, position markers, closing-brace comments, attributions,
  commented-out code, nonlocal information, too much information.
- Jeff Atwood, "Code Tells You How, Comments Tell You Why" (2006). Kernighan and Plauger,
  *The Elements of Programming Style*: "Don't comment bad code, rewrite it."
- PEP 257: a docstring summary is one line, imperative mood, and says what the function does
  for the caller, not how. Google style guides (C++, Java, Go): no comment that only restates.

## Lint rules that already exist

| Tool | Rule | Catches |
|---|---|---|
| Ruff / eradicate (Python) | `ERA001` | commented-out code |
| SonarQube / SonarLint (all languages) | `S125` | commented-out code |
| SonarQube | `S1135`, `S1134` | TODO and FIXME tracking |
| ESLint | `no-warning-comments`, `no-inline-comments`, `multiline-comment-style`, `capitalized-comments` | TODO spam, trailing comments, style |
| eslint-plugin-jsdoc | `require-description`, `no-blank-blocks` | empty or tag-only JSDoc |
| Pylint | `W0511` | TODO and FIXME |
| golangci-lint `godot`, `misspell` | | doc comment hygiene |

None of these catches a comment that restates the next line; that is what `scripts/comments.py` adds.

## Guarding other agents and other entry points

- CLAUDE.md or AGENTS.md, one line: *Do not add comments that say what the code does. Comment only
  a why the code cannot show. No changelog comments, no commented-out code, no section banners.*
- Pre-commit or CI: `python3 scripts/comments.py $(git diff --cached --name-only --diff-filter=AM)`
  fails the commit when a staged file has a flagged comment.
- PR review prompt: "list every comment in the diff that paraphrases the line below it".
- Claude Code: the `hooks/code-comments.py` PreToolUse hook in this repo; it applies to subagents too.
