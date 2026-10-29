#!/usr/bin/env python3
"""Fixtures per language plus hook events.   python3 test_comments.py"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from comments import check, hook, judge, scan

TS = '''// Copyright 2026 Example Corp. Licensed under MIT.
import { db } from "./db";

// ---------------- helpers ----------------
export class RateLimiter {
  /** Creates a new rate limiter. */
  constructor(private limit: number, private windowMs: number) {}

  /**
   * Tries to acquire a slot.
   * @param key the key
   * @returns the result
   */
  tryAcquire(key: string, now = Date.now()): boolean {
    // Get the timestamps for this key
    const stamps = this.hits.get(key) ?? [];
    // Remove expired timestamps
    const fresh = stamps.filter((t) => t > now - this.windowMs);
    // Check if we are over the limit
    if (fresh.length >= this.limit) {
      return false; // return false
    }
    // Stripe rounds to cents, so compare in integers (see #412)
    const cents = Math.round(amount * 100);
    const url = "http://example.com//double"; // keep the double slash: the CDN needs it
    // Updated to use the new Map API
    fresh.push(now);
    // const old = this.hits.get(key);
    // Here we store the fresh list back
    this.hits.set(key, fresh);
    return true;
  } // end of tryAcquire
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private hits = new Map<string, number[]>();
  // TODO(lb): make the window configurable per key
}
'''

CS = '''using System;

namespace Shop
{
    #region totals
    public static class OrderTotals
    {
        /// <summary>
        /// Gets or sets the name.
        /// </summary>
        public static string Name { get; set; }

        /// <summary>
        /// Computes the total for an order.
        /// </summary>
        /// <param name="lines">The lines.</param>
        /// <returns>The result.</returns>
        public static decimal Compute(IReadOnlyList<OrderLine> lines, decimal taxRate)
        {
            // Arrange
            var path = @"C:\\temp\\file.txt"; // Windows only: the service account has no home directory
            // Calculate the subtotal
            var subtotal = lines.Sum(l => l.Quantity * l.UnitPrice);
            // Round to 2 decimals using banker's rounding
            return Math.Round(subtotal * (1 + taxRate), 2, MidpointRounding.ToEven);
        }

        /// <summary>
        /// Half-to-even, because the ledger export in Finance rounds the same way and the two must agree.
        /// </summary>
        public static decimal Round(decimal value) => Math.Round(value, 2, MidpointRounding.ToEven);
    }
    #endregion
}
'''

PY = '''#!/usr/bin/env python3
"""Order totals."""
import math  # noqa: F401


def total(lines):
    """Return the total."""
    # Loop over the lines
    for line in lines:
        # increment the counter
        count += 1
    s = "# not a comment"
    # retry once: the upstream API drops the first request after idle
    return count


def round_half_even(value):
    """Half-to-even so the figure matches the ledger export."""
    return round(value, 2)
'''


def kinds(text, name):
    flagged, _, _ = check("", text, name, 0.3)
    return {n: kind for n, kind, _ in flagged}


class TypeScript(unittest.TestCase):
    def setUp(self):
        self.k = kinds(TS, "a.ts")

    def test_flags(self):
        self.assertEqual(self.k.get(4), "banner")
        self.assertEqual(self.k.get(6), "restating")       # Creates a new rate limiter
        self.assertEqual(self.k.get(10), "restating")      # Tries to acquire a slot
        self.assertEqual(self.k.get(11), "restating")      # @param key the key
        self.assertEqual(self.k.get(12), "restating")      # @returns the result
        self.assertEqual(self.k.get(15), "restating")      # Get the timestamps for this key
        self.assertEqual(self.k.get(17), "restating")      # Remove expired timestamps
        self.assertEqual(self.k.get(19), "restating")      # Check if we are over the limit
        self.assertEqual(self.k.get(21), "restating")      # return false (inline)
        self.assertEqual(self.k.get(26), "narration")      # Updated to use
        self.assertEqual(self.k.get(28), "commented-out code")
        self.assertEqual(self.k.get(29), "narration")      # Here we store
        self.assertEqual(self.k.get(32), "end marker")

    def test_keeps(self):
        for line in (1, 23, 25, 33, 35):
            self.assertNotIn(line, self.k, f"line {line} should pass")

    def test_string_is_not_a_comment(self):
        rows = scan(TS, "a.ts")
        self.assertEqual(rows[24].comment, "keep the double slash: the CDN needs it")
        self.assertIn('"http://example.com//double"', rows[24].code)


class CSharp(unittest.TestCase):
    def setUp(self):
        self.k = kinds(CS, "a.cs")

    def test_flags(self):
        self.assertEqual(self.k.get(9), "restating")       # Gets or sets the name
        self.assertEqual(self.k.get(14), "restating")      # Computes the total for an order
        self.assertEqual(self.k.get(16), "restating")      # <param name="lines">The lines.</param>
        self.assertEqual(self.k.get(17), "restating")      # <returns>The result.</returns>
        self.assertEqual(self.k.get(22), "restating")      # Calculate the subtotal

    def test_keeps(self):
        for line in (5, 20, 21, 24, 29, 33):
            self.assertNotIn(line, self.k, f"line {line} should pass")

    def test_verbatim_string(self):
        rows = scan(CS, "a.cs")
        self.assertEqual(rows[20].comment, "Windows only: the service account has no home directory")


class Python(unittest.TestCase):
    def setUp(self):
        self.k = kinds(PY, "a.py")

    def test_flags(self):
        self.assertEqual(self.k.get(7), "restating")       # Return the total
        self.assertEqual(self.k.get(8), "restating")       # Loop over the lines
        self.assertEqual(self.k.get(10), "restating")      # increment the counter

    def test_keeps(self):
        for line in (1, 2, 3, 13, 18):
            self.assertNotIn(line, self.k, f"line {line} should pass")

    def test_string_is_not_a_comment(self):
        self.assertIsNone(scan(PY, "a.py")[11].comment)


class ReturnsTags(unittest.TestCase):
    def test_echoing_the_return_type_is_restating(self):
        self.assertEqual(judge("<returns>The invoice.</returns>", False, "public Invoice? Get(Guid id)", True), "restating")
        self.assertEqual(judge("@returns the user", False, "getUser(id: string): Promise<User> {", True), "restating")

    def test_saying_more_passes(self):
        self.assertIsNone(judge("<returns>The invoice, or null when the id is unknown.</returns>", False, "public Invoice? Get(Guid id)", True))
        self.assertIsNone(judge("@returns the user, or null if the token has expired", False, "getUser(id: string): Promise<User> {", True))


class Judge(unittest.TestCase):
    def test_why_comments_pass(self):
        for text, code in [
            ("Stripe rounds to cents, so compare in integers", "const diff = Math.round(a * 100) - Math.round(b * 100);"),
            ("Retry once: the upstream API drops the first request after idle", "for (let attempt = 0; attempt < 2; attempt++) {"),
            ("userId is a string here because the legacy API sends it quoted", "const userId: string = raw.id;"),
            ("Idempotent.", "export function applyMigration(id: string) {"),
            ("Not thread-safe", "public void Add(Item item)"),
            ("use a Map for O(1) lookup", "const seen = new Map<string, number>();"),
            ("return early when the list is empty (see above)", "if (!items.length) return;"),
            ("Why this commit message isn't a proper Conventional Commit, or ''.", "def reject_reason(msg):"),
            ("fixed so a verdict is reproducible", "SEED = 1234"),
            ("`else if` was counted at the else", "if val == \"if\" and prev == \"else\":"),
            ("we need to flush before close because the OS buffers writes", "stream.flush();"),
        ]:
            self.assertIsNone(judge(text, True, code, False), text)

    def test_what_comments_fail(self):
        for text, code, kind in [
            ("Validate the input", "if (!input) throw new Error('missing');", "restating"),
            ("Fetch the user from the database", "const user = await db.users.find(id);", "restating"),
            ("Reconnect", "reconnect();", "restating"),
            ("Added null check", "if (x == null) return;", "narration"),
            ("In this PR we moved the parser out", "import { parse } from './parse';", "narration"),
            ("This function handles the request", "function handle(req) {", "narration"),
            ("return user;", "", "commented-out code"),
            ("foo.bar(x)", "", "commented-out code"),
            ("const old = compute(x);", "", "commented-out code"),
            ("=====================", "", "banner"),
            ("end if", "}", "end marker"),
            ("end of class Foo", "}", "end marker"),
        ]:
            self.assertEqual(judge(text, True, code, False), kind, text)


class Hook(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "x.ts")
        with open(self.path, "w") as f:
            f.write("export function add(a: number, b: number) {\n  return a + b;\n}\n")

    def run_hook(self, tool, tool_input, env=None):
        event = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": self.dir}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=False), mock.patch("sys.stdin", io.StringIO(json.dumps(event))), redirect_stdout(out):
            hook()
        return json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue() else None

    def test_edit_with_restating_comment_is_denied(self):
        res = self.run_hook("Edit", {"file_path": self.path, "old_string": "  return a + b;",
                                     "new_string": "  // return the sum of a and b\n  return a + b;"})
        self.assertEqual(res["permissionDecision"], "deny")
        self.assertIn("x.ts:2  restating  return the sum of a and b", res["permissionDecisionReason"])

    def test_clean_edit_is_silent(self):
        res = self.run_hook("Edit", {"file_path": self.path, "old_string": "  return a + b;",
                                     "new_string": "  // ints only: callers pass cents, floats would drift\n  return a + b;"})
        self.assertIsNone(res)

    def test_moving_an_existing_comment_is_silent(self):
        with open(self.path, "w") as f:
            f.write("// return the sum of a and b\nexport function add(a: number, b: number) {\n  return a + b;\n}\n")
        res = self.run_hook("Write", {"file_path": self.path,
                                      "content": "export function add(a: number, b: number) {\n  // return the sum of a and b\n  return a + b;\n}\n"})
        self.assertIsNone(res)

    def test_write_new_file_with_density_only_is_advisory(self):
        res = self.run_hook("Write", {"file_path": os.path.join(self.dir, "new.ts"),
                                      "content": "// why one\nconst a = 1;\n// why two\nconst b = 2;\n// why three\nconst c = 3;\n"})
        self.assertNotIn("permissionDecision", res)
        self.assertIn("3 comment lines for 3 lines of code", res["additionalContext"])

    def test_multiedit_and_warn_mode(self):
        res = self.run_hook("MultiEdit", {"file_path": self.path, "edits": [
            {"old_string": "  return a + b;", "new_string": "  // return the sum\n  return a + b;"}]}, {"CODE_COMMENTS_MODE": "warn"})
        self.assertNotIn("permissionDecision", res)
        self.assertIn("restating", res["additionalContext"])

    def test_off_and_other_files(self):
        self.assertIsNone(self.run_hook("Edit", {"file_path": self.path, "old_string": "  return a + b;",
                                                 "new_string": "  // return the sum\n  return a + b;"}, {"CODE_COMMENTS_MODE": "off"}))
        self.assertIsNone(self.run_hook("Write", {"file_path": os.path.join(self.dir, "notes.md"), "content": "// return the sum"}))


if __name__ == "__main__":
    unittest.main(verbosity=1)
