#!/usr/bin/env python3
"""SessionStart on the compact matcher: put the working state back after compaction.

Prints the files this session edited (newest first, read from the transcript) and the
uncommitted changes. SessionStart stdout is added to context, so Claude resumes on the
same files. PostCompact output is not, which is why this is not a PostCompact hook.

Never blocks: any failure exits 0.
"""
import json
import subprocess
import sys

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
MAX_FILES = 15
MAX_STATUS_LINES = 20


def edit_paths(line):
    try:
        content = json.loads(line).get("message", {}).get("content")
    except (ValueError, AttributeError):
        return
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") in EDIT_TOOLS:
            yield block.get("input", {}).get("file_path") or block.get("input", {}).get("notebook_path")


def edited_files(transcript_path):
    files = {}  # insertion order = order of last edit
    with open(transcript_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            for path in edit_paths(line) if '"tool_use"' in line else ():
                if path:
                    files.pop(path, None)
                    files[path] = True
    return list(files)[::-1]


def main():
    data = json.load(sys.stdin)
    if data.get("hook_event_name") != "SessionStart" or data.get("source") != "compact":
        return
    out = []
    try:
        files = edited_files(data["transcript_path"])
    except (OSError, KeyError):
        files = []
    if files:
        more = f" (and {len(files) - MAX_FILES} older)" if len(files) > MAX_FILES else ""
        out.append(f"Files edited in this session before compaction, newest first{more}:\n"
                   + "\n".join(f"  {f}" for f in files[:MAX_FILES]))
    try:
        status = subprocess.run(["git", "-C", data.get("cwd") or ".", "status", "--short", "--branch"],
                                capture_output=True, text=True, timeout=10).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        status = []
    if len(status) > 1:
        out.append("Uncommitted changes:\n" + "\n".join(f"  {s}" for s in status[:MAX_STATUS_LINES]))
    if out:
        print("WORKING STATE (compact-state hook). The conversation was just compacted; re-read a file below "
              "before editing it.\n\n" + "\n\n".join(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
