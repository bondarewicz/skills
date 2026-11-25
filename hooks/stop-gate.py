#!/usr/bin/env python3
"""Stop hook: Claude cannot end a turn while the repo's own check command fails.

The command comes from ~/.claude/stop-gate.json, a map of repo root to shell command:

    {"/Users/me/code/app": "npm run typecheck && npm test"}

A repo with no entry is never gated. The file lives outside the repo on purpose: a
cloned repo must not be able to make this hook run its commands.

The command runs once per working-tree state. An unchanged tree is not re-checked, so
question-only turns cost nothing, and a failure Claude cannot fix blocks one time only.

Blocks with exit 2 and the tail of the output. Any other problem (no git, bad config,
timeout) lets the turn end.

Also registered on SessionStart (startup): in a git repo with no entry it shows the user
a one-line reminder to add one. An entry of "" means "no gate here" and silences it.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
CONFIG = CLAUDE_DIR / "stop-gate.json"
STATE_DIR = CLAUDE_DIR / "state" / "stop-gate"
TIMEOUT = int(os.environ.get("STOP_GATE_TIMEOUT", "540"))
TAIL_CHARS = 4000


def git(cwd, *args):
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=30).stdout


def fingerprint(root):
    h = hashlib.sha256()
    h.update(git(root, "rev-parse", "HEAD").encode())
    h.update(git(root, "diff", "HEAD").encode())
    for name in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if name:
            try:
                st = os.stat(os.path.join(root, name))
                h.update(f"{name}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
            except OSError:
                pass
    return h.hexdigest()


def main():
    data = json.load(sys.stdin)
    if data.get("background_tasks"):
        return 0  # paused on background work, not finished
    root = git(data.get("cwd") or os.getcwd(), "rev-parse", "--show-toplevel").strip()
    config = json.loads(CONFIG.read_text()) if CONFIG.is_file() else {}
    if data.get("hook_event_name") == "SessionStart":
        if root and root not in config:
            print(json.dumps({"systemMessage": f'stop-gate: no check command for this repo. Add "{root}": '
                                               f'"<test command>" to {CONFIG}, or "" to silence this.'}))
        return 0
    command = config.get(root) if root else None
    if not command:
        return 0

    seen_file = STATE_DIR / hashlib.sha256(root.encode()).hexdigest()[:16]
    if seen_file.is_file() and seen_file.read_text() == fingerprint(root):
        return 0
    try:
        run = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True, timeout=TIMEOUT,
                             stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        print(json.dumps({"systemMessage": f"stop-gate: `{command}` did not finish in {TIMEOUT}s; not verified."}))
        return 0
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    seen_file.write_text(fingerprint(root))  # after the run: the command may write untracked files
    if run.returncode == 0:
        return 0
    tail = (run.stdout + run.stderr).strip()[-TAIL_CHARS:]
    print(f"stop-gate: `{command}` failed (exit {run.returncode}) in {root}. Fix it before ending the turn, "
          f"or say plainly that it still fails and why.\n\n{tail}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        code = 0
    sys.exit(code)
