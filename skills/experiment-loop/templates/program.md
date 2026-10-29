# Experiment program: {{GOAL}}

You are running an autonomous experiment loop in this repository. One change at a
time: edit, commit, let the judge decide, keep or undo. The judge's verdict is the
only thing that counts. Your own sense that a change "should be faster" is not evidence.

## Rules

- **Goal:** {{DIRECTION}} `{{METRIC_NAME}}`, as printed by `{{MEASURE_CMD}}`.
- **You may edit only:** {{SCOPE}}
- **Never edit:** {{LOCKED}}, `.experiment/`, and anything the measure or gate commands read
  to score you. Changing the scorer is cheating, even by accident.
- **Gate:** `{{GATE_CMD}}` must pass. The judge runs it before every measurement.
- **Behaviour must not change.** {{BEHAVIOUR_RULE}}
- **No new dependencies** unless this file says otherwise.
- **Never push**, never touch other branches, never run `git add -A`. Stage only files in scope.
- **Budget:** stop after {{MAX_EXPERIMENTS}} experiments or {{MAX_HOURS}} hours, whichever comes first.
  Within the budget, do not stop to ask whether to continue.
- **Simplicity:** a tiny gain that adds ugly code is not worth it. Equal results with less code is a win.

## The loop

Branch: `{{BRANCH}}`. Best kept commit starts as the baseline commit.

1. Pick one idea. Read `python3 .experiment/judge.py log` first, so you don't repeat a
   discarded idea and can build on near-misses.
2. Make the change, only inside the allowed scope.
3. `git add <files in scope> && {{COMMIT_CMD}} -m "experiment: <short description>"`
4. `python3 .experiment/judge.py run "<short description>" --quiet`
5. Exit code 0 (KEEP): this commit becomes the new best. Continue from it.
   Exit code 1 or 2 (DISCARD, GATE FAILED, CRASH): `git reset --hard <best kept commit>`.
   If it was a trivial mistake (typo, missing using), fix it and run again once. Otherwise move on.
6. Every 5 experiments, add a short entry to `.experiment/notes.md`: what you tried, what
   you learned, and what you will try next.
7. Repeat until the budget is used up.

## When the budget is used up

Write `.experiment/report.md`:
- Baseline vs final best (`judge.py best`), with the noise level from the baseline.
- Each kept change: commit, gain, one sentence on why it works.
- Ideas that failed, grouped, so nobody retries them.
- Anything suspicious: gains close to the noise, changes that feel like they bend a rule.

Then stop. Leave the branch for the human to review. Do not merge, push, or clean up.
