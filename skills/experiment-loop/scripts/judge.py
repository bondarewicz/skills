#!/usr/bin/env python3
"""
judge.py - significance-gated keep/discard for an autonomous experiment loop.

Generalised from autoresearch-mlx's rigor.py. It never edits code or touches git;
it only measures and decides. Config and ledger live next to this file.

    judge.py init --measure "./measure.sh" --gate "dotnet test" --direction lower
    judge.py run "use a dictionary for area lookup"   # gate, measure N times, decide
    judge.py best                                     # current best
    judge.py log                                      # every scored attempt

The measure command must print a line `METRIC: <number>`; the last one wins.
The gate command must exit 0 or the attempt is discarded without measuring.
Exit code of `run`: 0 = keep, 1 = discard, 2 = gate failed or crash.
"""

import argparse
import json
import random
import re
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "experiment.json"
LEDGER = HERE / "ledger.jsonl"
METRIC_RE = re.compile(r"^METRIC[:=]\s*(-?[\d.]+(?:[eE][-+]?\d+)?)\s*$", re.M)


def sh(cmd, quiet):
    """Run a shell command from the repo root; return (exit code, output)."""
    proc = subprocess.run(cmd, shell=True, cwd=HERE.parent, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if not quiet:
        sys.stdout.write(proc.stdout)
    return proc.returncode, proc.stdout


def parse_metric(output):
    found = METRIC_RE.findall(output)
    return float(found[-1]) if found else None


def load_ledger():
    if not LEDGER.exists():
        return []
    return [json.loads(x) for x in LEDGER.read_text().splitlines() if x.strip()]


def record(desc, samples, status, p, commit):
    entry = {"commit": commit, "desc": desc, "samples": samples,
             "mean": statistics.mean(samples) if samples else None,
             "std": statistics.pstdev(samples) if len(samples) > 1 else 0.0,
             "status": status, "p_better": round(p, 4)}
    with LEDGER.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def better(a, b, direction):
    return a < b if direction == "lower" else a > b


def best_entry(ledger, direction):
    keeps = [e for e in ledger if e["status"] in ("keep", "baseline")]
    if not keeps:
        return None
    pick = min if direction == "lower" else max
    return pick(keeps, key=lambda e: e["mean"])


def prob_improvement(best, cand, direction, trials=20000):
    """Bootstrap P(candidate mean beats best mean)."""
    rng = random.Random(1234)  # fixed so a verdict is reproducible
    nb, nc = len(best), len(cand)
    wins = 0
    for _ in range(trials):
        b = sum(best[rng.randrange(nb)] for _ in range(nb)) / nb
        c = sum(cand[rng.randrange(nc)] for _ in range(nc)) / nc
        wins += better(c, b, direction)
    return wins / trials


def head_commit():
    code, out = sh("git rev-parse --short HEAD", quiet=True)
    return out.strip() if code == 0 else "-"


def cmd_init(a):
    cfg = {"measure": a.measure, "gate": a.gate, "direction": a.direction,
           "runs": a.runs, "baseline_runs": a.baseline_runs, "confidence": a.confidence}
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"wrote {CONFIG}")


def cmd_run(a):
    cfg = json.loads(CONFIG.read_text())
    direction = cfg["direction"]
    ledger = load_ledger()
    best = best_entry(ledger, direction)
    commit = head_commit()

    if cfg.get("gate"):
        code, out = sh(cfg["gate"], quiet=True)
        if code != 0:
            record(a.desc, [], "gate-fail", 0.0, commit)
            print(out[-3000:])
            print(f"\nGATE FAILED {commit}: '{cfg['gate']}' exited {code}. Discard this change.")
            return 2

    runs = cfg["baseline_runs"] if best is None else cfg["runs"]
    samples = []
    for i in range(runs):
        code, out = sh(cfg["measure"], quiet=a.quiet)
        v = parse_metric(out)
        if code != 0 or v is None:
            record(a.desc, samples, "crash", 0.0, commit)
            print(out[-3000:])
            print(f"\nCRASH {commit}: measure exited {code} or printed no 'METRIC: <number>' line.")
            return 2
        samples.append(v)
        print(f"  run {i + 1}/{runs}: {v:g}")
        if best and i == 0 and not better(v, best["mean"], direction):
            record(a.desc, samples, "discard", 0.0, commit)  # clear loser, save the other runs
            print(f"\nDISCARD {commit}: first run {v:g} does not beat best mean {best['mean']:g}.")
            return 1

    if best is None:
        e = record(a.desc, samples, "baseline", 1.0, commit)
        noise = e["std"] / e["mean"] * 100 if e["mean"] else 0.0
        print(f"\nBASELINE {commit}: {e['mean']:g} +/- {e['std']:g} ({noise:.1f}% noise, {runs} runs)")
        return 0

    p = prob_improvement(best["samples"], samples, direction)
    status = "keep" if p >= cfg["confidence"] else "discard"
    e = record(a.desc, samples, status, p, commit)
    change = (e["mean"] - best["mean"]) / best["mean"] * 100 if best["mean"] else 0.0
    print(f"\n{status.upper()} {commit}: mean {e['mean']:g} vs best {best['mean']:g} "
          f"({change:+.2f}%), P(better)={p:.2f}, need >={cfg['confidence']:.2f}")
    return 0 if status == "keep" else 1


def cmd_best(a):
    cfg = json.loads(CONFIG.read_text())
    b = best_entry(load_ledger(), cfg["direction"])
    print(f"best {b['commit']}: {b['mean']:g} +/- {b['std']:g} - {b['desc']}" if b else "no baseline yet")


def cmd_log(a):
    for e in load_ledger():
        mean = f"{e['mean']:g}" if e["mean"] is not None else "-"
        print(f"{e['commit']}\t{mean}\t{e['status']}\tp={e['p_better']:.2f}\t{e['desc']}")


def main():
    ap = argparse.ArgumentParser(description="significance-gated keep/discard for experiment loops")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="write experiment.json")
    i.add_argument("--measure", required=True, help="shell command that prints 'METRIC: <number>'")
    i.add_argument("--gate", default="", help="shell command that must exit 0 (e.g. the test suite)")
    i.add_argument("--direction", choices=["lower", "higher"], default="lower")
    i.add_argument("--runs", type=int, default=3, help="measurements per experiment")
    i.add_argument("--baseline-runs", type=int, default=5, help="measurements for the baseline")
    i.add_argument("--confidence", type=float, default=0.95, help="P(better) needed to keep")
    r = sub.add_parser("run", help="gate, measure and decide for the current code")
    r.add_argument("desc", help="short description of the change")
    r.add_argument("--quiet", action="store_true", help="hide measure output")
    sub.add_parser("best", help="show the current best")
    sub.add_parser("log", help="show every scored attempt")
    a = ap.parse_args()
    sys.exit({"init": cmd_init, "run": cmd_run, "best": cmd_best, "log": cmd_log}[a.cmd](a) or 0)


if __name__ == "__main__":
    main()
