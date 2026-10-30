#!/usr/bin/env python3
"""Detector fixtures, turn parsing, ledger, table and both hook events.   python3 test_estimates.py"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from estimates import find_estimates, hook, main, read_ledger, size_class, table, turns

HERE = Path(__file__).resolve().parent
T0 = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)

HUMAN_SCALE = [
    "Estimate: about half a day for me. Your review: ten minutes on the spec.",
    "Effort: 2h.",
    "This will take 3 hours.",
    "I'd budget a couple of days for the migration.",
    "ETA: 1-2 days.",
    "That is about two to three weeks of work.",
    "This is roughly one sprint.",
    "Plan on an afternoon for the rewrite.",
    "- Estimate: all day, mostly tests.",
    "The migration will take about a month.",
    'The screen is 6" wide, and this will take about 3 hours.\nThen "done".',
]

NOT_AN_ESTIMATE = [
    "The tests took 2 hours.",
    "Set the timeout to 2 hours.",
    "Claude: about 15 minutes active. You: 5 minutes.",
    "For a human developer this is about a day of work.",
    "It would take you about 3 hours to review.",
    "It runs every 6 hours.",
    "```\nsleep 3600  # 1 hour\n```\nEstimate: 4 minutes.",
    "Pass `--max-age 2h` to keep an hour of history.",
    "We met for 2 hours yesterday.",
    "The 2-hour meeting is at noon.",
    "I estimate 40 minutes for this turn.",
    "Redis on its own Fly machine costs about $2.50 to $4 a month.",
    "- **Fixed plans** start at $10 a month for 250 MB.",
    "Redis costs about two fifty to four dollars a month, a bit more in Frankfurt.",
    "That saves about a dollar or two a month for a small site.",
    "Backups run about twice a day.",
    'Real estimates like "the migration will take about a month" are still caught.',
    "The hook flagged “this will take about two days” in the reply.",
]


def line(kind, t, content, **extra):
    d = {"type": kind, "timestamp": (T0 + timedelta(seconds=t)).isoformat().replace("+00:00", "Z"),
         "isSidechain": False, "message": {"role": kind, "content": content}, "cwd": "/repo"}
    d.update(extra)
    return json.dumps(d)


def tool_use(name, inp):
    return [{"type": "tool_use", "id": "t1", "name": name, "input": inp}]


def tool_result(text="ok"):
    return [{"type": "tool_result", "tool_use_id": "t1", "content": text}]


TRANSCRIPT = "\n".join([
    "not json at all",
    json.dumps({"type": "summary", "summary": "x"}),
    line("user", 0, "write the thing"),
    line("user", 1, "<system-reminder>hook text</system-reminder>", isMeta=True),
    line("assistant", 10, tool_use("Write", {"file_path": "a.py", "content": "\n".join(["x = 1"] * 30)})),
    line("user", 15, tool_result()),
    line("assistant", 20, tool_use("Bash", {"command": "python3 -m pytest tests/"})),
    line("user", 25, tool_result("1 passed")),
    line("assistant", 27, tool_use("Read", {"file_path": "side.py"}), isSidechain=True),
    json.dumps({"type": "assistant", "message": {"content": []}}),
    line("assistant", 30, [{"type": "text", "text": "done"}]),
    line("user", 1000, [{"type": "text", "text": "now ask me something"}]),
    line("assistant", 1005, tool_use("AskUserQuestion", {"questions": []})),
    line("user", 2000, tool_result("Me only")),
    line("assistant", 2005, [{"type": "text", "text": "ok"}]),
]) + "\n"


class Detector(unittest.TestCase):
    def test_human_scale_estimates_are_found(self):
        for text in HUMAN_SCALE:
            self.assertTrue(find_estimates(text), text)

    def test_actuals_schedules_minutes_humans_and_code_pass(self):
        for text in NOT_AN_ESTIMATE:
            self.assertEqual(find_estimates(text), [], text)

    def test_hit_carries_the_phrase_and_its_sentence(self):
        hits = find_estimates("Lots of context first. Estimate: about half a day for me. Then more.")
        self.assertEqual(len(hits), 1)
        phrase, sentence = hits[0]
        self.assertEqual(phrase.lower(), "half a day")
        self.assertIn("for me", sentence)
        self.assertNotIn("Lots of context", sentence)


class Turns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name, "abc.jsonl")
        self.path.write_text(TRANSCRIPT)

    def tearDown(self):
        self.tmp.cleanup()

    def test_splits_at_real_prompts_only(self):
        rows = turns(self.path)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["session"] for r in rows], ["abc", "abc"])
        self.assertEqual(rows[0]["start"], "2026-10-29T12:00:00Z")
        self.assertEqual(rows[0]["cwd"], "/repo")

    def test_counts_tools_lines_tests_and_active_seconds(self):
        first = turns(self.path)[0]
        self.assertEqual((first["tools"], first["edits"], first["lines"], first["tests"], first["asks"]), (2, 1, 30, 1, 0))
        self.assertEqual((first["active_s"], first["idle_s"]), (30, 0))

    def test_gap_over_ten_minutes_is_idle_not_active(self):
        second = turns(self.path)[1]
        self.assertEqual(second["asks"], 1)
        self.assertEqual(second["active_s"], 10)
        self.assertEqual(second["idle_s"], 995)

    def test_bash_heredocs_count_as_lines_written(self):
        cmd = "cat > f.py <<'EOF'\nx = 1\ny = 2\nz = 3\nEOF\npython3 - <<PY\nprint(1)\nPY\necho done"
        self.path.write_text("\n".join([line("user", 0, "write via bash"),
                                        line("assistant", 5, tool_use("Bash", {"command": cmd}))]) + "\n")
        row = turns(self.path)[0]
        self.assertEqual((row["lines"], row["bash"], row["edits"]), (4, 1, 0))

    def test_missing_file_gives_no_rows(self):
        self.assertEqual(turns(Path(self.tmp.name, "nope.jsonl")), [])


class SizeClass(unittest.TestCase):
    def test_edges(self):
        for lines, cls in ((0, "XS"), (19, "XS"), (20, "S"), (99, "S"), (100, "M"), (399, "M"),
                           (400, "L"), (1199, "L"), (1200, "XL"), (5000, "XL")):
            self.assertEqual(size_class(lines), cls, lines)


class Env(unittest.TestCase):
    """Each test gets its own CLAUDE_CONFIG_DIR with one project transcript."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        proj = self.home / "projects" / "-repo"
        proj.mkdir(parents=True)
        (proj / "sub").mkdir()
        (proj / "abc.jsonl").write_text(TRANSCRIPT)
        (proj / "sub" / "agent.jsonl").write_text(TRANSCRIPT)
        self.transcript = proj / "abc.jsonl"
        self.ledger = self.home / "state" / "estimates" / "ledger.jsonl"
        self.old = dict(os.environ)
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.home)
        os.environ.pop("ESTIMATES_MODE", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old)
        self.tmp.cleanup()

    def stop(self, message, active=False):
        return hook({"hook_event_name": "Stop", "session_id": "abc", "transcript_path": str(self.transcript),
                     "stop_hook_active": active, "last_assistant_message": message})


class Ledger(Env):
    def test_rebuild_scans_top_level_transcripts_only(self):
        self.assertEqual(main(["--rebuild"]), 0)
        rows = read_ledger()
        self.assertEqual(len(rows), 2)
        self.assertTrue(self.ledger.is_file())

    def test_same_turn_logged_twice_keeps_the_last_row(self):
        self.stop("done")
        self.stop("done, again")
        rows = read_ledger()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["start"], "2026-10-29T12:16:40Z")
        self.assertEqual(len(self.ledger.read_text().splitlines()), 2)

    def test_table_on_empty_ledger_says_so(self):
        out = table([])
        self.assertIn("No measured turns", out)

    def test_table_groups_by_class_and_skips_turns_without_tools(self):
        rows = [{"lines": 50, "tools": 14, "active_s": 180}, {"lines": 50, "tools": 14, "active_s": 240},
                {"lines": 0, "tools": 0, "active_s": 9000}]
        out = table(rows)
        self.assertIn("S ", out)
        self.assertRegex(out, r"S\s+<100\s+2\s+3\.5")
        self.assertNotIn("9000", out)
        self.assertNotIn("XS", out)


class StopHook(Env):
    def test_blocks_a_human_scale_estimate_with_a_recipe_for_the_corrected_line(self):
        out = json.loads(self.stop("Estimate: about half a day for me."))
        self.assertEqual(out["decision"], "block")
        self.assertIn("half a day", out["reason"])
        self.assertIn("Claude: <median> to <p90> min", out["reason"])
        self.assertIn("nothing else", out["reason"])

    def test_correction_without_a_number_is_blocked_once_more_then_let_go(self):
        self.stop("This will take one to two hours.")
        again = json.loads(self.stop("Correction: that estimate should have been in measured minutes.", active=True))
        self.assertEqual(again["decision"], "block")
        self.assertIn("no number", again["reason"])
        self.assertIsNone(self.stop("Still no number here.", active=True))

    def test_correction_with_minutes_ends_the_follow_up(self):
        self.stop("This will take one to two hours.")
        self.assertIsNone(self.stop("Claude: 4 to 9 min (M, ~200 lines, n=154). You: ~2 min.", active=True))
        self.assertIsNone(self.stop("Another hook made me continue; no numbers here.", active=True))

    def test_continuation_caused_by_another_hook_is_not_judged(self):
        self.assertIsNone(self.stop("No estimate was flagged this turn.", active=True))

    def test_logs_the_turn_even_when_already_continuing(self):
        self.stop("fine", active=True)
        self.assertEqual(len(read_ledger()), 1)

    def test_clean_message_passes(self):
        self.assertIsNone(self.stop("Claude: 10 to 25 min (L, ~500 lines, n=20). You: ~5 min."))

    def test_warn_mode_tells_the_user_only(self):
        os.environ["ESTIMATES_MODE"] = "warn"
        out = json.loads(self.stop("This will take 3 hours."))
        self.assertNotIn("decision", out)
        self.assertIn("3 hours", out["systemMessage"])

    def test_off_mode_still_logs_but_never_speaks(self):
        os.environ["ESTIMATES_MODE"] = "off"
        self.assertIsNone(self.stop("This will take 3 hours."))
        self.assertEqual(len(read_ledger()), 1)


class SessionStartHook(Env):
    def test_seeds_the_ledger_from_past_transcripts_on_first_run(self):
        out = hook({"hook_event_name": "SessionStart", "session_id": "new"})
        self.assertTrue(self.ledger.is_file())
        self.assertEqual(len(read_ledger()), 2)
        self.assertIn("ESTIMATES", out)
        self.assertIn("S ", out)
        self.assertIn("estimates skill", out)

    def test_existing_ledger_is_not_rescanned(self):
        self.ledger.parent.mkdir(parents=True)
        self.ledger.write_text("")
        out = hook({"hook_event_name": "SessionStart", "session_id": "new"})
        self.assertEqual(read_ledger(), [])
        self.assertIn("No measured turns", out)

    def test_unknown_event_is_silent(self):
        self.assertIsNone(hook({"hook_event_name": "PreToolUse"}))


class Cli(Env):
    def test_check_exits_one_with_the_phrase(self):
        self.assertEqual(main(["--check", "Estimate: about half a day for me."]), 1)
        self.assertEqual(main(["--check", "Claude: 12 minutes."]), 0)

    def test_table_and_recent(self):
        main(["--rebuild"])
        self.assertEqual(main([]), 0)
        self.assertEqual(main(["--recent", "1"]), 0)

    def test_no_args_and_empty_stdin_prints_the_table(self):
        env = dict(os.environ, PYTHONPATH="")
        r = subprocess.run([sys.executable, "-I", str(HERE / "estimates.py")], input="",
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)
        self.assertIn("No measured turns", r.stdout)

    def test_idle_open_stdin_pipe_prints_the_table_within_seconds(self):
        env = dict(os.environ, PYTHONPATH="")
        t0 = time.monotonic()
        p = subprocess.Popen([sys.executable, "-I", str(HERE / "estimates.py")], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True, env=env)
        out = p.stdout.read()
        p.wait(timeout=5)
        p.stdin.close()
        self.assertLess(time.monotonic() - t0, 5)
        self.assertIn("No measured turns", out)

    def test_malformed_stdin_exits_zero_silently(self):
        env = dict(os.environ, PYTHONPATH="")
        r = subprocess.run([sys.executable, "-I", str(HERE / "estimates.py")], input="{not json",
                           capture_output=True, text=True, env=env)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
