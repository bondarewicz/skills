#!/usr/bin/env python3
"""Runs the hooks that have no skill of their own as subprocesses, the way Claude Code does.

    python3 tests/test_hooks.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"

# Built by concatenation so no scanner (or the hook under test) sees a secret in this file.
STRIPE = "sk_" + "live_" + "a1B2" * 6
GITHUB = "gh" + "p_" + "x9" * 18
AWS = "AK" + "IA" + "ABCDEFGHIJKLMNOP"


def run(hook, payload, env=None):
    p = subprocess.run([sys.executable, "-I", str(HOOKS / hook)], input=json.dumps(payload), capture_output=True,
                       text=True, env={**os.environ, **(env or {})})
    return p.returncode, p.stdout, p.stderr


class RedactSecrets(unittest.TestCase):
    def bash(self, command, **extra):
        code, out, _ = run("redact-secrets.py", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                                 "tool_input": {"command": command, **extra}})
        self.assertEqual(code, 0)
        return json.loads(out)["hookSpecificOutput"] if out else None

    def test_redacts_and_keeps_other_fields(self):
        out = self.bash(f"curl -u {STRIPE}: https://x && gh auth login --with-token {GITHUB}", description="d", timeout=5)
        self.assertEqual(out["updatedInput"], {"command": "curl -u <REDACTED_SECRET>: https://x && gh auth login "
                                                          "--with-token <REDACTED_SECRET>", "description": "d", "timeout": 5})
        self.assertNotIn("permissionDecision", out)
        self.assertIn("2 live-looking", out["additionalContext"])

    def test_aws(self):
        self.assertEqual(self.bash(f"export AWS_ACCESS_KEY_ID={AWS}")["updatedInput"]["command"],
                         "export AWS_ACCESS_KEY_ID=<REDACTED_SECRET>")

    def test_leaves_alone(self):
        for cmd in ("grep -rn sk_live_ src/", "echo sk_test_" + "a" * 24, "git log --oneline", "ls task-force-skills"):
            self.assertIsNone(self.bash(cmd), cmd)

    def test_other_tool_and_garbage(self):
        self.assertEqual(run("redact-secrets.py", {"tool_name": "Write", "tool_input": {"content": STRIPE}})[:2], (0, ""))
        p = subprocess.run([sys.executable, str(HOOKS / "redact-secrets.py")], input="not json", capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, ""))


class StopGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.repo, self.claude = base / "repo", base / "claude"
        self.repo.mkdir()
        self.claude.mkdir()
        for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                                      "commit", "-q", "--allow-empty", "-m", "init"]):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def configure(self, command):
        (self.claude / "stop-gate.json").write_text(json.dumps({str(self.repo): command}))

    def stop(self, **extra):
        return run("stop-gate.py", {"hook_event_name": "Stop", "cwd": str(self.repo), **extra},
                   {"CLAUDE_CONFIG_DIR": str(self.claude)})

    def test_no_entry_never_gates(self):
        self.assertEqual(self.stop()[0], 0)
        (self.claude / "stop-gate.json").write_text(json.dumps({"/somewhere/else": "exit 1"}))
        self.assertEqual(self.stop()[0], 0)

    def test_fail_blocks_once_per_tree_state(self):
        self.configure("echo boom-out; echo boom-err >&2; exit 3")
        code, _, err = self.stop()
        self.assertEqual(code, 2)
        self.assertIn("exit 3", err)
        self.assertIn("boom-out", err)
        self.assertIn("boom-err", err)
        self.assertEqual(self.stop()[0], 0, "same tree: let go")
        (self.repo / "new.txt").write_text("x")
        self.assertEqual(self.stop()[0], 2, "tree changed: checked again")

    def test_pass_then_skipped_until_change(self):
        self.configure("echo ran >> ../runs; test ! -f broken")
        self.assertEqual(self.stop()[0], 0)
        self.assertEqual(self.stop()[0], 0)
        self.assertEqual((self.repo.parent / "runs").read_text(), "ran\n", "unchanged tree ran the command once")
        (self.repo / "broken").write_text("x")
        self.assertEqual(self.stop()[0], 2)

    def test_background_tasks_and_timeout_do_not_block(self):
        self.configure("exit 1")
        self.assertEqual(self.stop(background_tasks=[{"id": "t"}])[0], 0)
        self.configure("sleep 5")
        code, out, _ = run("stop-gate.py", {"cwd": str(self.repo)},
                           {"CLAUDE_CONFIG_DIR": str(self.claude), "STOP_GATE_TIMEOUT": "1"})
        self.assertEqual(code, 0)
        self.assertIn("not verified", json.loads(out)["systemMessage"])

    def test_session_start_reminds_until_repo_has_an_entry(self):
        code, out, _ = self.stop(hook_event_name="SessionStart", source="startup")
        self.assertEqual(code, 0)
        self.assertIn(str(self.repo), json.loads(out)["systemMessage"])
        for command in ("", "exit 1"):
            self.configure(command)
            self.assertEqual(self.stop(hook_event_name="SessionStart", source="startup")[:2], (0, ""), repr(command))
        self.configure("")
        self.assertEqual(self.stop()[0], 0, "empty entry never gates")

    def test_outside_git_and_bad_config(self):
        self.assertEqual(run("stop-gate.py", {"cwd": self.tmp.name}, {"CLAUDE_CONFIG_DIR": str(self.claude)})[0], 0)
        (self.claude / "stop-gate.json").write_text("{not json")
        self.assertEqual(self.stop()[0], 0)


class CompactState(unittest.TestCase):
    def transcript(self, d, edits):
        path = Path(d) / "t.jsonl"
        lines = [json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": name, "input": {"file_path": f}}]}}) for name, f in edits]
        path.write_text("\n".join(["garbage tool_use line", json.dumps({"type": "user", "message": {"content": "hi"}}), *lines]))
        return str(path)

    def test_lists_edited_files_newest_first(self):
        with tempfile.TemporaryDirectory() as d:
            t = self.transcript(d, [("Edit", "/r/a.ts"), ("Read", "/r/read-only.ts"), ("Write", "/r/B.cs"), ("Edit", "/r/a.ts")])
            code, out, _ = run("compact-state.py", {"hook_event_name": "SessionStart", "source": "compact",
                                                    "transcript_path": t, "cwd": d})
            self.assertEqual(code, 0)
            self.assertIn("newest first:\n  /r/a.ts\n  /r/B.cs", out)
            self.assertNotIn("read-only", out)

    def test_silent_on_other_sources_and_missing_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            t = self.transcript(d, [("Edit", "/r/a.ts")])
            base = {"hook_event_name": "SessionStart", "transcript_path": t, "cwd": d}
            self.assertEqual(run("compact-state.py", {**base, "source": "startup"})[:2], (0, ""))
            self.assertEqual(run("compact-state.py", {**base, "source": "compact", "transcript_path": d + "/none"})[:2], (0, ""))


if __name__ == "__main__":
    unittest.main()
