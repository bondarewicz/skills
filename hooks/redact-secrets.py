#!/usr/bin/env python3
"""PreToolUse on Bash: swap a live-looking secret in the command for a placeholder.

The command is rewritten with updatedInput, not denied, and no permission decision is
returned, so the rewritten command still goes through the normal permission flow. In
auto mode Claude Code may refuse a call a hook rewrote; that is the safe outcome.

Only prefixed token formats are matched, so a search for the bare prefix
(`grep -r sk_live_ .`) is left alone. Never blocks: any failure exits 0.
"""
import json
import re
import sys

PLACEHOLDER = "<REDACTED_SECRET>"
SECRET = re.compile(r"""
      \b[sr]k_live_[A-Za-z0-9]{16,}                 # Stripe secret / restricted key
    | \bsk-ant-[A-Za-z0-9_-]{20,}                   # Anthropic
    | \bsk-(?:proj-)?[A-Za-z0-9_-]{32,}             # OpenAI
    | \bgh[pousr]_[A-Za-z0-9]{36,}                  # GitHub token
    | \bgithub_pat_[A-Za-z0-9_]{40,}
    | \bxox[abprs]-[A-Za-z0-9-]{20,}                # Slack
    | \b(?:AKIA|ASIA)[A-Z0-9]{16}\b                 # AWS access key id
    | \bAIza[A-Za-z0-9_-]{35}                       # Google API key
""", re.X)


def main():
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command")
    if data.get("tool_name") != "Bash" or not isinstance(command, str):
        return
    redacted, n = SECRET.subn(PLACEHOLDER, command)
    if not n:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        # updatedInput replaces the whole input, so every other field is echoed back.
        "updatedInput": {**tool_input, "command": redacted},
        "additionalContext": f"redact-secrets hook: {n} live-looking secret(s) in this command were replaced with "
                             f"{PLACEHOLDER} before it ran. Read the value from an environment variable or a file "
                             "instead of writing it in the command, and tell the user the secret appeared in this "
                             "session so they can rotate it.",
    }}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
