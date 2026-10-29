---
name: experiment-loop
description: Set up and run an autonomous keep-or-undo experiment loop (autoresearch style) on any repo with a measurable number - benchmark time, allocations, build time, test runtime. Sets up a locked scorer, a test gate, a noise-aware judge and a budget, then iterates one change at a time on its own branch.
argument-hint: "[goal, e.g. make the order lookup faster]"
disable-model-invocation: true
---

# Experiment loop

Karpathy's autoresearch pattern, for any codebase: the agent changes one thing, a fixed
scorer measures it, and the change is kept only if it is better than the noise. Goal for
this run: **$ARGUMENTS**

Files in this skill:
- `scripts/judge.py`: gates, measures N times, decides keep/discard with a bootstrap test. Never edits code or git.
- `templates/program.md`: the loop rules you fill in for this repo.

Work in two phases. **Phase 1 is interactive. Phase 2 runs without asking.**

## Phase 1: setup (with the user)

Agree on each item below. Propose concrete values from reading the repo; ask only about
what you can't work out yourself.

1. **Metric:** one number, and whether lower or higher is better.
2. **Measure command:** prints `METRIC: <number>`. Usually you write a small
   `.experiment/measure.sh` that runs the benchmark and extracts one value. For
   BenchmarkDotNet: run one benchmark with `--filter`, export JSON with `--exporters json`,
   and read `Statistics.Mean` (or `Memory.BytesAllocatedPerOperation`) from
   `BenchmarkDotNet.Artifacts/results/*.json`. Keep a single measurement under about two minutes
   (e.g. `--job short`).
3. **Gate command:** the tests that must stay green, e.g. `dotnet test <project>`. Use the
   narrowest test project that covers the scope, to keep experiments fast.
4. **Scope:** the files or folders the agent may edit. **Locked:** benchmarks, tests,
   test data, the measure script, anything else that defines the score.
5. **Behaviour rule:** how we know outputs didn't change. The gate usually covers this. For
   money or pricing logic, also add a golden-output check (fixed inputs, outputs saved
   before the run, compared in the gate).
6. **Budget:** max experiments and max hours. Default: 20 experiments, 4 hours.

Then do these steps:

1. Check that `git status` is clean. Create branch `experiment/<short-goal>-<date>` from the current branch.
2. `mkdir .experiment`, add `.experiment/` to `.git/info/exclude` (local only, never
   committed; it survives `git reset --hard`), copy `scripts/judge.py` from this skill
   into `.experiment/`, and write `.experiment/measure.sh` if needed.
3. **Block pushing for this clone.** Save the current push URL, then run
   `git remote set-url --push origin DISABLED` for every remote. Tell the user how to undo it.
   **Agree commit authorship** (the user's confirm-git hook enforces it, if installed): ask
   "Me only, GPG signed" or "Me + Claude, unsigned". Fill the template's `{{COMMIT_CMD}}` to match:
   `git commit` (no Co-Authored-By line) or `git -c commit.gpgsign=false commit` (with the
   `Co-Authored-By: Claude` trailer). With signing on, warn that each experiment commit may wait
   on a GPG passphrase prompt unless gpg-agent caches it for the whole run.
   Also warn: a hook that asks before every commit will stall an unattended loop, so the user
   decides whether to stay nearby or relax that hook for the experiment branch.
4. Write `.experiment/program.md` from `templates/program.md`, with every `{{...}}` filled in
   (`{{COMMIT_CMD}}` comes from the authorship choice in step 3).
5. `python3 .experiment/judge.py init --measure "<cmd>" --gate "<cmd>" --direction <lower|higher>`
6. Run the measure command once by hand, so the user can see it works and how long it takes.
7. **Baseline:** `python3 .experiment/judge.py run "baseline"`. This measures 5 times and
   prints the noise %. If noise is above about 5%, say so: small wins will be impossible to
   prove. Suggest a longer benchmark job or a steadier machine before going further.
8. Show the user a summary: metric, baseline, noise, time per experiment, how many
   experiments fit in the budget, scope, and locked files. **Wait for their go.**

## Phase 2: the loop (autonomous)

Read `.experiment/program.md` and follow it exactly until the budget is used up. Do not
ask whether to continue. The user may be away. The judge decides; you don't overrule it.

Things that make a run good:
- **Ideas from evidence:** read the code under test, profile when possible, and prefer
  algorithmic wins (allocations, lookups, LINQ in hot paths, boxing, repeated work) over
  micro-tweaks.
- **One idea per experiment,** so every verdict is clear.
- **Keep context small:** run the judge with `--quiet`, read only its verdict line, and
  look at `.experiment/notes.md` instead of trying to remember everything.

## After the run

Point the user to `.experiment/report.md` and the branch. Remind them:
- Re-run `judge.py run "final check"` on the final best commit to confirm the gain holds.
- Review the kept commits like any other pull request before merging.
- Restore pushing with the URL saved in setup step 3.
