#!/usr/bin/env python3
"""
PreToolUse hook: never let Claude commit or push without showing you first.

For any Bash call that runs `git commit` or `git push`, it forces a permission prompt
(even in auto mode) that says what, where, why, and whether anything leaves the machine.
Every other command passes through untouched.

Register in ~/.claude/settings.json under hooks.PreToolUse with matcher "Bash":
    python3 -I ~/.claude/hooks/confirm-git.py
"""

import json
import os
import re
import shlex
import subprocess
import sys

SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")"}
# git global options that take a separate value: `git -C dir commit`, `git -c k=v push`
VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def git(cwd, *args):
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def find_actions(command, cwd):
    """Return [(action, args, dir)] for each git commit/push, following `cd` and `-C`."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    tokens = list(lexer)  # raises ValueError on unbalanced quotes
    segments, cur = [], []
    for t in tokens:
        if t in SEPARATORS:
            segments.append(cur)
            cur = []
        else:
            cur.append(t)
    segments.append(cur)

    actions = []
    for seg in segments:
        if not seg:
            continue
        if seg[0] == "cd" and len(seg) > 1:
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(seg[1])))
            continue
        if os.path.basename(seg[0]) != "git":
            continue
        i, d = 1, cwd
        while i < len(seg) and seg[i].startswith("-"):
            if seg[i] == "-C" and i + 1 < len(seg):
                d = os.path.normpath(os.path.join(d, os.path.expanduser(seg[i + 1])))
            i += 2 if seg[i] in VALUE_OPTS else 1
        if i < len(seg) and seg[i] in ("commit", "push"):
            actions.append((seg[i], seg[i + 1:], d))
    return actions


def message_of(args):
    for i, a in enumerate(args):
        if a in ("-m", "--message") and i + 1 < len(args):
            return args[i + 1]
        if a.startswith("--message="):
            return a.split("=", 1)[1]
        if a.startswith("-m") and len(a) > 2:
            return a[2:]
    if "--amend" in args and "--no-edit" in args:
        return "(keeps the previous commit message)"
    return "(no -m given: an editor or a file supplies it)"


def describe(action, args, d):
    root = git(d, "rev-parse", "--show-toplevel") or d
    branch = git(d, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    upstream = git(d, "rev-parse", "--abbrev-ref", "@{u}")
    lines = [f"Repo:    {root}", f"Branch:  {branch}"]

    if action == "commit":
        lines.insert(0, "LOCAL COMMIT ONLY - nothing is sent to a remote.")
        flags = [f for f in ("--amend", "--no-verify", "-a", "--all") if f in args]
        if flags:
            lines.append("Flags:   " + " ".join(flags) + ("  (rewrites the last commit)" if "--amend" in args else ""))
        lines.append("Message: " + message_of(args).strip().splitlines()[0][:200])
        staged = git(d, "diff", "--cached", "--stat")
        lines.append("Staged now:\n" + ("\n".join(staged.splitlines()[-12:]) if staged else "  (nothing staged yet; an earlier step of this command may stage files)"))
    else:
        positional = [a for a in args if not a.startswith("-")]
        remote = positional[0] if positional else (upstream.split("/")[0] if upstream else "origin")
        url = git(d, "remote", "get-url", "--push", remote) or "(unknown remote)"
        force = [f for f in args if f in ("-f", "--force") or f.startswith("--force-with-lease")]
        lines.insert(0, "PUSH TO REMOTE - this leaves your machine." + ("  FORCE PUSH." if force else ""))
        lines.append(f"Remote:  {remote} -> {url}")
        lines.append("Target:  " + (" ".join(positional[1:]) or (upstream or f"{branch} (no upstream yet)")))
        if upstream:
            ahead = git(d, "log", "--oneline", "-15", "@{u}..HEAD")
            lines.append("Commits to push:\n" + (ahead or "  (none ahead of upstream)"))
    return "\n".join(lines)


def main():
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Bash":
        return
    command = data.get("tool_input", {}).get("command", "")
    why = data.get("tool_input", {}).get("description", "") or "(no description given)"
    cwd = data.get("cwd") or os.getcwd()
    if not re.search(r"\bgit\b[^\n]*\b(commit|push)\b", command):
        return  # fast path: most commands never get parsed

    try:
        actions = find_actions(command, cwd)
        body = "\n\n".join(describe(*a) for a in actions)
    except ValueError:
        actions, body = [None], f"Could not parse the command; review it below.\nWorking dir: {cwd}"
    if not actions:
        return

    reason = (f"Claude wants to run git:\n\n{body}\n\nWhy (Claude's description): {why}\n\n"
              f"Full command:\n{command[:800]}")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }}))


if __name__ == "__main__":
    main()
