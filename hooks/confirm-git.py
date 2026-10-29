#!/usr/bin/env python3
"""
Hook: Claude never commits or pushes without you knowing, and never with the wrong author.

1. Git author choice (once per session, per repo work):
   - PreToolUse Edit|Write|NotebookEdit on a file inside a git repo, with no choice yet:
     blocked, and Claude is told to ask you the "Git author" question.
   - PostToolUse AskUserQuestion: your answer is read from the tool result and saved,
     so Claude cannot record a choice you didn't make.
     "Me only, GPG signed"  -> solo:     no Claude co-author line, normal (signed) commit
     "Me + Claude, unsigned" -> coauthor: Co-Authored-By: Claude line, unsigned commit
2. PreToolUse Bash with `git commit` / `git push`:
   - a commit that doesn't match the choice (or has no choice) is blocked with the reason;
   - a commit message that isn't a Conventional Commit is blocked; breaking changes need both
     `!` in the header and a `BREAKING CHANGE:` footer;
   - otherwise a permission prompt (even in auto mode) shows what, where, why,
     and whether anything leaves the machine.

Register in ~/.claude/settings.json:
    PreToolUse  matcher "Bash|Edit|Write|NotebookEdit": python3 -I ~/.claude/hooks/confirm-git.py
    PostToolUse matcher "AskUserQuestion":              python3 -I ~/.claude/hooks/confirm-git.py
"""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")"}
# git global options that take a separate value: `git -C dir commit`, `git -c k=v push`
VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
STATE_DIR = Path(os.environ.get("CONFIRM_GIT_STATE", Path.home() / ".claude" / "state" / "git-author"))
HEADER = "Git author"
LABELS = {"Me only, GPG signed": "solo", "Me + Claude, unsigned": "coauthor"}
ASK_INSTRUCTIONS = (
    "Before changing files in a git repo, ask the user how commits should be authored. "
    f"Use AskUserQuestion with header \"{HEADER}\" and exactly these two option labels: "
    "\"Me only, GPG signed\" (no Co-Authored-By line, commit signed as usual) and "
    "\"Me + Claude, unsigned\" (add the Co-Authored-By: Claude trailer, commit with -c commit.gpgsign=false). "
    "The hook records the answer; then retry."
)


def git(cwd, *args):
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def mode_file(session_id):
    return STATE_DIR / re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")


def get_mode(session_id):
    try:
        return mode_file(session_id).read_text().strip()
    except OSError:
        return ""


def emit(event, decision=None, reason=None, context=None):
    out = {"hookEventName": event}
    if decision:
        out["permissionDecision"] = decision
        out["permissionDecisionReason"] = reason
    if context:
        out["additionalContext"] = context
    print(json.dumps({"hookSpecificOutput": out}))


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


def unheredoc(text):
    """`$(cat <<'EOF' ... EOF)` -> the text inside; anything else unchanged."""
    m = re.match(r"^\$\(cat <<-?'?(\w+)'?\n(.*?)\n\s*\1\s*\)$", text.strip(), re.S)
    return m.group(2) if m else text


def full_message(args, cwd):
    """Whole commit message from -m/--message (several join as paragraphs) or -F, else None."""
    parts = []
    for i, a in enumerate(args):
        if a in ("-m", "--message") and i + 1 < len(args):
            parts.append(args[i + 1])
        elif a.startswith("--message="):
            parts.append(a.split("=", 1)[1])
        elif a.startswith("-m") and len(a) > 2 and not a.startswith("--"):
            parts.append(a[2:])
        elif a in ("-F", "--file") and i + 1 < len(args):
            try:
                parts.append(Path(cwd, args[i + 1]).read_text())
            except OSError:
                return None
    return "\n\n".join(unheredoc(p).strip() for p in parts) if parts else None


def message_of(args, cwd="."):
    msg = full_message(args, cwd)
    if msg is not None:
        return msg
    if "--amend" in args and "--no-edit" in args:
        return "(keeps the previous commit message)"
    return "(no -m given: an editor or a file supplies it)"


CC_TYPES = "feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert"
CC_HEADER = re.compile(rf"^(?:{CC_TYPES})(?:\([\w./-]+\))?(!)?: \S")
CC_FOOTER = re.compile(r"^BREAKING[ -]CHANGE: \S", re.M)


def is_breaking(msg):
    m = CC_HEADER.match(msg)
    return bool((m and m.group(1)) or CC_FOOTER.search(msg))


def conventional_problem(args, cwd):
    """Why this commit message isn't a proper Conventional Commit, or ''."""
    if "--amend" in args and "--no-edit" in args:
        return ""  # keeps a message that was checked when it was first made
    msg = full_message(args, cwd)
    if msg is None:
        return "Give the commit message with -m (or -F <file>) so it can be checked as a Conventional Commit."
    header = msg.splitlines()[0] if msg else ""
    m = CC_HEADER.match(header)
    if not m:
        return (f"Commit header \"{header[:100]}\" is not a Conventional Commit. Use "
                f"`type(scope): description` with type one of {CC_TYPES.replace('|', ', ')}; "
                "add `!` before the colon for a breaking change.")
    bang, footer = bool(m.group(1)), bool(CC_FOOTER.search(msg))
    if bang and not footer:
        return "Header marks a breaking change (`!`) but there is no `BREAKING CHANGE: <what breaks and how to migrate>` footer. Add it."
    if footer and not bang:
        return "Message has a BREAKING CHANGE footer but the header has no `!` (e.g. `feat(api)!: ...`). Add it."
    body = "\n".join(msg.splitlines()[1:])  # a header may describe breaking changes as a topic
    if not footer and re.search(r"breaking[ -]?change", body, re.I):
        return ("Message mentions a breaking change informally. If it breaks something, use `!` in the header and a "
                "`BREAKING CHANGE: ...` footer (exact capitals); otherwise reword.")
    return ""


def author_problem(mode, command):
    """Why this commit command breaks the chosen author mode, or '' if it's fine."""
    coauthored = re.search(r"co-authored-by:\s*claude", command, re.I)
    unsigned = re.search(r"commit\.gpgsign=false|--no-gpg-sign", command)
    if not mode:
        return "No git author choice yet for this session. " + ASK_INSTRUCTIONS
    if mode == "solo" and (coauthored or unsigned):
        return ("The user chose \"Me only, GPG signed\": remove the Co-Authored-By: Claude line "
                "and any commit.gpgsign=false / --no-gpg-sign, then retry.")
    if mode == "coauthor" and not (coauthored and unsigned):
        return ("The user chose \"Me + Claude, unsigned\": the message needs a "
                "'Co-Authored-By: Claude ...' trailer and the commit needs -c commit.gpgsign=false. Retry with both.")
    return ""


def describe(action, args, d, mode):
    root = git(d, "rev-parse", "--show-toplevel") or d
    branch = git(d, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    upstream = git(d, "rev-parse", "--abbrev-ref", "@{u}")
    lines = [f"Repo:    {root}", f"Branch:  {branch}"]

    if action == "commit":
        lines.insert(0, "LOCAL COMMIT ONLY - nothing is sent to a remote.")
        lines.append("Author:  " + {"solo": "you only, GPG signed", "coauthor": "you + Claude, unsigned"}.get(mode, "?"))
        flags = [f for f in ("--amend", "--no-verify", "-a", "--all") if f in args]
        if flags:
            lines.append("Flags:   " + " ".join(flags) + ("  (rewrites the last commit)" if "--amend" in args else ""))
        msg = message_of(args, d).strip()
        lines.append("Message: " + (msg.splitlines()[0][:200] if msg else "(empty)"))
        lines.append("Breaking: " + ("YES - check that it really breaks something" if is_breaking(msg) else "no"))
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


def on_bash(data):
    command = data.get("tool_input", {}).get("command", "")
    why = data.get("tool_input", {}).get("description", "") or "(no description given)"
    cwd = data.get("cwd") or os.getcwd()
    if not re.search(r"\bgit\b[^\n]*\b(commit|push)\b", command):
        return  # fast path: most commands never get parsed
    mode = get_mode(data.get("session_id"))

    try:
        actions = find_actions(command, cwd)
    except ValueError:
        actions = None
    if actions == []:
        return
    if actions is None:
        body = f"Could not parse the command; review it below.\nWorking dir: {cwd}"
    else:
        for action, args, d in actions:
            if action == "commit":
                problem = author_problem(mode, command) or conventional_problem(args, d)
                if problem:
                    return emit("PreToolUse", "deny", problem)
        body = "\n\n".join(describe(*a, mode) for a in actions)

    emit("PreToolUse", "ask", f"Claude wants to run git:\n\n{body}\n\nWhy (Claude's description): {why}\n\n"
                              f"Full command:\n{command[:800]}")


def on_edit(data):
    if get_mode(data.get("session_id")):
        return
    path = data.get("tool_input", {}).get("file_path") or data.get("tool_input", {}).get("notebook_path") or ""
    folder = os.path.dirname(path) or data.get("cwd") or "."
    while folder and not os.path.isdir(folder):  # new file in a new folder: check the nearest existing one
        folder = os.path.dirname(folder)
    if folder and git(folder, "rev-parse", "--is-inside-work-tree") == "true":
        emit("PreToolUse", "deny", f"{path} is in a git repo. " + ASK_INSTRUCTIONS)


def on_question(data):
    """Record the user's git author answer from the AskUserQuestion result."""
    tool_input = data.get("tool_input", {})
    questions = [q for q in tool_input.get("questions", []) if q.get("header") == HEADER]
    if not questions:
        return
    answers = tool_input.get("answers") or {}
    picked = [answers.get(q.get("question"), "") for q in questions]
    blob = " ".join(picked) or json.dumps(data.get("tool_response", ""))  # fallback: search the result text
    found = {mode for label, mode in LABELS.items() if label in blob}
    if len(found) != 1:
        return emit("PostToolUse", context="Git author answer not recognised; nothing recorded. Ask again if needed.")
    mode = found.pop()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    mode_file(data.get("session_id")).write_text(mode + "\n")
    emit("PostToolUse", context=f"Git author recorded for this session: {mode}.")


def main():
    data = json.load(sys.stdin)
    tool = data.get("tool_name")
    if tool == "Bash":
        on_bash(data)
    elif tool in ("Edit", "Write", "NotebookEdit"):
        on_edit(data)
    elif tool == "AskUserQuestion" and data.get("hook_event_name") == "PostToolUse":
        on_question(data)


if __name__ == "__main__":
    main()
