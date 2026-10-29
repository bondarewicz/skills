#!/usr/bin/env python3
"""Keep the i-have-adhd skill on in every session until the user turns it off.

SessionStart:     install the plugin if it is missing, then load its rules.
UserPromptSubmit: a message that is only "stop adhd mode" / "normal mode" turns it
                  off for all sessions; "start adhd mode" or "/i-have-adhd" turns it
                  back on. While on, every prompt gets a one-line reminder so the
                  rules don't fade in long sessions.

Never blocks: any failure exits 0.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PLUGIN = "i-have-adhd@i-have-adhd"
MARKETPLACE = "ayghri/i-have-adhd"
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
OFF_FLAG = CLAUDE_DIR / "state" / "adhd-mode-off"

# Whole message only, so "in normal mode the app..." doesn't switch it off.
OFF_RE = re.compile(r"^\s*(stop adhd mode|normal mode)\s*[.!]*\s*$", re.I)
ON_RE = re.compile(r"^\s*(start adhd mode|/i-have-adhd)\b", re.I)
FRONTMATTER = re.compile(r"\A---[^\n]*\n.*?\n---[^\n]*(\n|\Z)", re.S)

REMINDER = ('ADHD mode is on (i-have-adhd rules apply to this response). '
            'Only a message "stop adhd mode" turns it off.')


def skill_file():
    try:
        data = json.loads((CLAUDE_DIR / "plugins" / "installed_plugins.json").read_text())
        for entry in data.get("plugins", {}).get(PLUGIN, []):
            f = Path(entry["installPath"]) / "skills" / "i-have-adhd" / "SKILL.md"
            if f.is_file():
                return f
    except (OSError, ValueError, KeyError, TypeError):
        pass
    f = CLAUDE_DIR / "skills" / "i-have-adhd" / "SKILL.md"
    return f if f.is_file() else None


def install():
    # No -y: never auto-accept marketplace-declared commands.
    for args in (["plugin", "marketplace", "add", MARKETPLACE],
                 ["plugin", "install", PLUGIN, "--scope", "user"]):
        try:
            subprocess.run(["claude", *args], capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            return


def rules(header):
    f = skill_file()
    if f is None:
        install()
        f = skill_file()
    if f is None:
        return (f"{header}\nThe i-have-adhd plugin could not be installed automatically. "
                f"Tell the user to run: claude plugin marketplace add {MARKETPLACE} && "
                f"claude plugin install {PLUGIN}")
    body = FRONTMATTER.sub("", f.read_text(), count=1).strip()
    return f"{header}\n\n{body}"


def main():
    data = json.load(sys.stdin)
    event = data.get("hook_event_name")
    if event == "SessionStart":
        if not OFF_FLAG.exists():
            print(rules('ADHD MODE ACTIVE (adhd-mode hook). The rules below apply to every '
                        'response until the user sends "stop adhd mode".'))
    elif event == "UserPromptSubmit":
        prompt = data.get("prompt", "")
        if OFF_RE.match(prompt):
            OFF_FLAG.parent.mkdir(parents=True, exist_ok=True)
            OFF_FLAG.touch()
            print("The user turned ADHD mode off for all sessions. Confirm in one line "
                  'and return to the default style. "start adhd mode" turns it back on.')
        elif ON_RE.match(prompt):
            OFF_FLAG.unlink(missing_ok=True)
            print(rules("The user turned ADHD mode on for all sessions. Confirm in one line."))
        elif not OFF_FLAG.exists():
            print(REMINDER)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
