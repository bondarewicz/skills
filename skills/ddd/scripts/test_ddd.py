#!/usr/bin/env python3
"""Fixtures for the ddd hook: domain-path detection, using extraction, forbidden matching.

    python3 test_ddd.py
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import ddd
from ddd import find_domain_dir, forbidden, is_domain_path, parse_allow, pre_tool_use, session_start, usings

HERE = os.path.dirname(os.path.abspath(__file__))


def event(tool, path, **ti):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": "/repo", "tool_input": {"file_path": path, **ti}}


class DomainPath(unittest.TestCase):
    def test_yes(self):
        for p in ("src/Orders/Domain/Order.cs", "Acme.Orders.Domain/Order.cs", "domain/x.cs", "/abs/ACME.DOMAIN/A.cs",
                  "Orders.Domain/Contest.cs", "Orders.Domain/Latest.cs"):
            self.assertTrue(is_domain_path(p), p)

    def test_no(self):
        for p in ("Acme.Orders.Api/C.cs", "Acme.DomainEvents/X.cs", "src/Orders/Domain/Order.ts", "Orders.Domain/OrderTests.cs",
                  "Orders.Domain/OrderTest.cs", "Orders.Domain/tests/X.cs", "Orders.Domain/Test/X.cs"):
            self.assertFalse(is_domain_path(p), p)


class Usings(unittest.TestCase):
    SRC = '''global using Microsoft.EntityFrameworkCore;
using static Acme.Helpers;
using EF = Microsoft.EntityFrameworkCore.EF;
using Acme.Orders.Domain;
// using Dapper;
namespace Acme.Orders.Domain;
using System.IO;
class A { void M() { using var s = File.Open(""); using (var t = new T()) { } } }
'''

    def test_extracts(self):
        self.assertEqual(usings(self.SRC), [(1, "Microsoft.EntityFrameworkCore"), (2, "Acme.Helpers"),
                                            (3, "Microsoft.EntityFrameworkCore.EF"), (4, "Acme.Orders.Domain"), (7, "System.IO")])


class Forbidden(unittest.TestCase):
    def test_groups(self):
        src = "\n".join(f"using {ns};" for ns in ("Microsoft.EntityFrameworkCore", "Microsoft.AspNetCore.Mvc",
                                                   "Microsoft.Extensions.Logging", "MassTransit", "MediatR",
                                                   "System.IO.Abstractions", "Acme.Orders.Infrastructure"))
        self.assertEqual([g for _, _, g in forbidden(src)], ["data", "web", "hosting", "messaging/cloud", "glue", "io", "layer"])

    def test_not_flagged(self):
        src = "using Acme.Orders.Domain;\nusing System.Net.Mail;\nusing Microsoft.ExtensionsX;\nusing FluentValidation;\n"
        self.assertEqual(forbidden(src), [])

    def test_allow(self):
        src = "using MediatR;\nusing System.IO;\nusing Dapper;\n"
        self.assertEqual([ns for _, ns, _ in forbidden(src, parse_allow("MediatR, System.IO,"))], ["Dapper"])


class PreToolUse(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.f = os.path.join(self.d, "Acme.Orders.Domain", "Order.cs")
        os.makedirs(os.path.dirname(self.f))

    def test_write_denies(self):
        out = pre_tool_use(event("Write", self.f, content="using Dapper;\nclass A {}\n"), {})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("Order.cs:1  using Dapper;  (data)", out["permissionDecisionReason"])

    def test_edit_adding_denies_but_legacy_passes(self):
        Path(self.f).write_text("using Dapper;\nclass A {}\n")
        self.assertIsNone(pre_tool_use(event("Edit", self.f, old_string="class A {}", new_string="class A { int X; }"), {}))
        out = pre_tool_use(event("Edit", self.f, old_string="class A {}", new_string="using MediatR;\nclass A {}"), {})
        self.assertIn("MediatR", out["permissionDecisionReason"])

    def test_edit_replace_all(self):
        Path(self.f).write_text("// a\n// a\n")
        out = pre_tool_use(event("Edit", self.f, old_string="// a", new_string="using Npgsql;", replace_all=True), {})
        self.assertEqual(out["permissionDecisionReason"].count("using Npgsql;"), 2)

    def test_missing_old_string_passes(self):
        Path(self.f).write_text("class A {}\n")
        self.assertIsNone(pre_tool_use(event("Edit", self.f, old_string="nope", new_string="using Dapper;"), {}))

    def test_multiedit_folds(self):
        Path(self.f).write_text("class A {}\n")
        out = pre_tool_use(event("MultiEdit", self.f, edits=[{"old_string": "class A {}", "new_string": "class B {}"},
                                                              {"old_string": "class B {}", "new_string": "using Dapper;\nclass B {}"}]), {})
        self.assertEqual(out["permissionDecision"], "deny")

    def test_non_domain_passes(self):
        self.assertIsNone(pre_tool_use(event("Write", os.path.join(self.d, "Acme.Api", "C.cs"), content="using Dapper;"), {}))

    def test_modes(self):
        ev = event("Write", self.f, content="using Dapper;")
        self.assertIn("additionalContext", pre_tool_use(ev, {"DDD_MODE": "warn"}))
        self.assertIsNone(pre_tool_use(ev, {"DDD_MODE": "off"}))

    def test_hook_swallows_bad_stdin(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ddd.py")], input="not json", capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))


class SessionStart(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cfg = os.path.join(self.d, "cfg")
        os.makedirs(os.path.join(self.cfg, "skills", "ddd"))
        Path(self.cfg, "skills", "ddd", "SKILL.md").write_text("---\nname: ddd\n---\n# DDD\nRULE ONE\n")
        self.env = {"CLAUDE_CONFIG_DIR": self.cfg}
        self.saved, ddd.SKILL_NEXT_TO_SCRIPT = ddd.SKILL_NEXT_TO_SCRIPT, Path(self.d, "absent.md")

    def tearDown(self):
        ddd.SKILL_NEXT_TO_SCRIPT = self.saved

    def test_finds_domain_dir(self):
        os.makedirs(os.path.join(self.d, "src", "Aaa", "domain"))
        Path(self.d, "src", "Aaa", "domain", "user.ts").write_text("")
        os.makedirs(os.path.join(self.d, "src", "Acme.Orders.Domain", "Orders"))
        Path(self.d, "src", "Acme.Orders.Domain", "Orders", "Order.cs").write_text("")
        os.makedirs(os.path.join(self.d, "node_modules", "x", "domain"))
        Path(self.d, "node_modules", "x", "domain", "X.cs").write_text("")
        self.assertEqual(find_domain_dir(self.d), os.path.join("src", "Acme.Orders.Domain"))

    def test_ignores_domain_dirs_without_cs(self):
        os.makedirs(os.path.join(self.d, "src", "domain"))
        Path(self.d, "src", "domain", "user.ts").write_text("")
        self.assertIsNone(find_domain_dir(self.d))

    def test_emits_rules_from_installed_skill(self):
        os.makedirs(os.path.join(self.d, "X.Domain"))
        Path(self.d, "X.Domain", "X.cs").write_text("")
        out = session_start({"hook_event_name": "SessionStart", "cwd": self.d}, self.env)
        ctx = out["additionalContext"]
        self.assertTrue(ctx.startswith("DDD mode: domain code at X.Domain."), ctx[:60])
        self.assertIn("RULE ONE", ctx)
        self.assertNotIn("name: ddd", ctx)

    def test_silent_without_domain_or_skill(self):
        self.assertIsNone(session_start({"hook_event_name": "SessionStart", "cwd": self.d}, self.env))
        os.makedirs(os.path.join(self.d, "X.Domain"))
        Path(self.d, "X.Domain", "X.cs").write_text("")
        self.assertIsNone(session_start({"hook_event_name": "SessionStart", "cwd": self.d}, {"CLAUDE_CONFIG_DIR": self.d}))
        self.assertIsNone(session_start({"hook_event_name": "SessionStart", "cwd": self.d}, {**self.env, "DDD_MODE": "off"}))


class Cli(unittest.TestCase):
    def test_tree(self):
        d = tempfile.mkdtemp()
        dom = os.path.join(d, "A.Domain")
        os.makedirs(dom)
        os.makedirs(os.path.join(d, "A.Api"))
        Path(dom, "Bad.cs").write_text("using Dapper;\n")
        Path(dom, "Ok.cs").write_text("using A.Domain;\n")
        Path(d, "A.Api", "C.cs").write_text("using Dapper;\n")
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ddd.py"), d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.strip(), f"{os.path.join(dom, 'Bad.cs')}:1  using Dapper;  (data)")
        Path(dom, "Bad.cs").write_text("using A.Domain;\n")
        self.assertEqual(subprocess.run([sys.executable, "-I", os.path.join(HERE, "ddd.py"), d], capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
