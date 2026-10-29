---
name: cognitive-complexity
description: Use when a function is hard to follow, when Sonar or a linter says "Cognitive Complexity of this function is X which is greater than the 15 authorized" (rule S3776), when the cognitive-complexity hook reports a function over the limit after an edit, or when deciding during review or refactoring whether a function should be split and how. Scores by SonarSource's Cognitive Complexity rules, which are not cyclomatic complexity.
---

# Cognitive complexity

One number per function: how hard its control flow is to read. Methods are free, breaks in
linear flow cost 1, nesting costs 1 more per level. SonarQube's limit is 15 per function.
Do not confuse it with cyclomatic complexity, which counts paths (every `case`, every `&&`).

## Measure, don't estimate

`scripts/` is inside this skill's directory (the base directory announced when the skill loads,
normally `~/.claude/skills/cognitive-complexity/`); use that absolute path from anywhere.

```bash
python3 scripts/cogc.py --explain path/to/file.ts     # every function, every increment with its line
python3 scripts/cogc.py src/                          # whole tree, only functions over 15, exit 1 if any
python3 scripts/cogc.py --limit 10 file.py            # another threshold
```

Python is scored from the AST and is exact. JS/TS, Java, C#, Go, Rust, C/C++, Kotlin, Swift,
PHP, Dart, Scala, Groovy are scored from tokens: exact on the paper's examples, possibly off by
one on exotic syntax. `<top-level>` is code outside any function (scripts, module-level `if`).
When a hand count and the script disagree, check the line the script names against the table
below before trusting either.

## The rules in one table

| Score | Construct |
|---|---|
| +1 and +nesting, nests its body | `if`, ternary `?:`, `switch`/`match`/`when`, `for`/`foreach`, `while`/`do`, `catch` |
| +1, nests its body, no nesting penalty | `else if`/`elif`, `else` |
| +1, no nesting | each run of one boolean operator (`a && b && c` = 1, `a && b \|\| c` = 2), `goto`, `break label`, `continue label`, recursion (per function in the cycle) |
| free, but body is one level deeper | lambdas, nested functions, anonymous classes. Their score goes to the enclosing function, so a method registering six endpoint lambdas carries all six |
| free | the function itself, plain `break`/`continue`/`return`/`throw`, `try`/`finally`, `?.` `??` `?:`, `!` |

`switch` is +1 total whatever the number of cases. `catch` is +1 whatever it catches.
C# follows sonar-dotnet: pattern `and`/`or` count like `&&`/`||`, and `goto` takes nesting. See `reference.md`.
Full specification, language exceptions and the paper's worked examples: `reference.md`.

## Lowering a score: what moves the number

Ranked by points per change. Check with `--explain` before and after.

1. **Extract the deepest nested block into its own function.** Methods are free and nesting
   restarts at 0 inside the new one. Removes the nesting penalty from everything moved.
2. **Return or continue early** instead of wrapping the rest of the body in an `if`. Every
   structure that was inside loses one level.
3. **Replace an `if / else if` chain over one value with a `switch`, `match`, or a lookup
   table.** The chain costs 1 per branch; the switch costs 1.
4. **Move a mixed boolean condition into a named predicate function.** The operator sequences
   leave with it, and the condition gets a name.
5. **Use `?.` and `??`** instead of null-check `if`s.

Moves that do not lower it: splitting `a && b || c` into temporaries in the same function
(same sequences, same score), replacing a loop with recursion (+1), adding a labeled break (+1),
turning a `switch` into `if / else if` (+1 per branch).

## When reporting

- Give the score and the two or three lines that contribute most, then the one refactoring that
  removes the most points. Quote lines by number from `--explain`.
- The hook lists only functions an edit created or made worse. Fix those; leave other
  over-limit functions unless asked.
- A function at 16 that is one flat `switch` with many cases is fine. Nesting depth is the
  signal, not the raw number.

## Hook

`hooks/cognitive-complexity.py` in this repo is the same script. Registered as PreToolUse and
PostToolUse on `Edit|Write|MultiEdit`, it reports functions over 15 that an edit created or made
worse, with the old score. Advisory only; never blocks. Test files are skipped. The limit is
`COGNITIVE_COMPLEXITY_LIMIT` in the environment.
