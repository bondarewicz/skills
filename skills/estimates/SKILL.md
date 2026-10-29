---
name: estimates
description: Use when asked how long something will take or how much effort it is, when writing an estimate, ETA, time budget or effort line into a plan, spec, design or reply, when the estimates Stop hook rejects a reply, or when comparing an estimate with what a turn actually took.
---

# Estimates

An estimate for work Claude does itself is a measurement from this install's own history, not a
guess in human units. The ledger (`~/.claude/state/estimates/ledger.jsonl`) holds every turn that
ran tools: active minutes, lines written (edit tools and Bash heredocs), tool calls, test runs. Those turns are the reference
class. "Half a day", "2h" and "a sprint" are the reference class of a person typing and thinking;
measured on this install (October 2026, 51 turns), a turn that writes 400 to 1200 lines takes
about seven minutes, 18 at the 90th percentile.

## The estimate line

Two clocks, never blended:

```
Claude: 10 to 25 min (L, ~500 lines in 5 files, n=20). You: ~5 min (read 70 lines, 1 decision).
```

1. **Size the work in things you can count now:** files to create or change, lines, test runs,
   external waits (CI, installs, deploys).
2. **Look up the class** in the pace table (printed at session start, or `python3 scripts/estimates.py`):
   XS under 20 lines, S under 100, M under 400, L under 1200, XL from 1200. Quote median to p90
   active minutes.
3. **Name the class and n.** Fewer than 5 turns in the class: say so and quote the next class up.
4. **External waits are their own numbers:** a 6-minute CI run is 6 minutes, not a class.
5. **The user's clock separately:** reading at about 100 lines a minute, one minute per decision or
   question, plus any manual test. Waiting while Claude works is not their time.

## What actually makes a turn slow

Not the typing. The long turns in the ledger are: an unknown codebase (reading before writing), a
long or flaky test suite run many times, a permission prompt or question left waiting (idle, not
active), a vague request that costs a round trip. Name the one that applies instead of padding
the number.

## When the hook blocks a reply

The Stop hook found hours, days, "half a day", an afternoon, weeks or sprints next to an estimate
word. Rewrite that sentence as the line above. Estimating a human's work (a hiring plan, a team's
sprint) is fine: say "for a human developer" in the same sentence and the hook lets it through.

## Check and inspect

`scripts/` is inside this skill's directory (the base directory announced when the skill loads,
normally `~/.claude/skills/estimates/`); use that absolute path from anywhere.

```bash
python3 scripts/estimates.py                                  # pace table from the ledger
python3 scripts/estimates.py --recent 20                      # last 20 turns: active, idle, lines, tools, tests
python3 scripts/estimates.py --rebuild                        # rescan every transcript in ~/.claude/projects
python3 scripts/estimates.py --check "Estimate: half a day"   # exit 1 with the phrase
```

After a turn, `--recent 1` is the actual. Compare it with what was said; a class that keeps
running over is the signal to size by tool calls instead of lines.

## Hook

`hooks/estimates.py` in this repo is the same script. SessionStart prints the table and the rule;
the first run seeds the ledger from past transcripts. Stop logs the finished turn, then scans the
reply and blocks once per turn with the table as the reason. `ESTIMATES_MODE=warn` shows the user
a notice instead, `off` only logs. Measured time includes waits on permission prompts shorter than
ten minutes, so the table errs long. Codex has no hooks; it gets the skill text only.

Background: Kahneman and Tversky's planning fallacy, and Flyvbjerg's reference class forecasting,
which replaces the inside view with the distribution of comparable past cases. Here the comparable
cases are this install's own turns.
