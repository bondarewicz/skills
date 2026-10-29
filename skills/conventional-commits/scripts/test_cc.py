#!/usr/bin/env python3
"""The spec's own examples, the house rules, the file and range modes.   python3 test_cc.py"""
import os
import subprocess
import tempfile
import unittest

from cc import main, message_file, parse, validate

SPEC_EXAMPLES = [
    "feat: allow provided config object to extend other configs\n\nBREAKING CHANGE: `extends` key in config file is now used for extending other config files",
    "feat!: send an email to the customer when a product is shipped",
    "feat(api)!: send an email to the customer when a product is shipped",
    "chore!: drop support for Node 6\n\nBREAKING CHANGE: use JavaScript features not available in Node 6.",
    "docs: correct spelling of CHANGELOG",
    "feat(lang): add Polish language",
    "fix: prevent racing of requests\n\nIntroduce a request id and a reference to latest request. Dismiss\n"
    "incoming responses other than from latest request.\n\nRemove timeouts which were used to mitigate the racing issue but are\n"
    "obsolete now.\n\nReviewed-by: Z\nRefs: #123",
]


class SpecExamples(unittest.TestCase):
    def test_all_pass_the_specification(self):
        for msg in SPEC_EXAMPLES:
            self.assertEqual(validate(msg, house=False), [], msg.splitlines()[0])

    def test_parse(self):
        p = parse(SPEC_EXAMPLES[-1])
        self.assertEqual((p["type"], p["scope"], p["breaking"]), ("fix", None, False))
        self.assertEqual(p["description"], "prevent racing of requests")
        self.assertEqual(len(p["body"]), 2)
        self.assertEqual(p["footers"], [("Reviewed-by", "Z"), ("Refs", "#123")])
        self.assertTrue(parse(SPEC_EXAMPLES[0])["breaking"])
        self.assertTrue(parse("feat(x)!: y")["breaking"])
        self.assertEqual(parse("feat(x)!: y")["scope"], "x")
        self.assertIsNone(parse("no header here"))


class Specification(unittest.TestCase):
    def problems(self, msg):
        return validate(msg, house=False)

    def test_header_shape(self):
        self.assertIn("must be `type(scope)!: description`", self.problems("update stuff")[0])
        self.assertIn("exactly one space", self.problems("feat:no space")[0])
        self.assertIn("empty", self.problems("feat(): x")[0])
        self.assertIn("description after the colon is empty", self.problems("feat: ")[0])
        self.assertEqual(self.problems("Feat: any case is fine for the spec"), [])
        self.assertEqual(self.problems("deploy: types outside the common list are allowed by the spec"), [])

    def test_blank_line_before_body(self):
        self.assertIn("line 2 must be blank", self.problems("fix: x\nbody right away")[0])
        self.assertEqual(self.problems("fix: x\n\nbody"), [])

    def test_breaking_change_footer_case_and_synonym(self):
        self.assertIn("uppercase", self.problems("fix: x\n\nbreaking change: y")[0])
        self.assertIn("uppercase", self.problems("fix: x\n\nBreaking-Change: y")[0])
        self.assertIn("needs a description", self.problems("fix!: x\n\nBREAKING CHANGE:")[0])
        self.assertEqual(self.problems("fix!: x\n\nBREAKING-CHANGE: y"), [])

    def test_footer_tokens_use_hyphens(self):
        self.assertIn("`Reviewed by` must use `-`", self.problems("fix: x\n\nbody\n\nReviewed by: Z\nRefs: #1")[0])
        self.assertEqual(self.problems("fix: x\n\nNote: this sentence in the body is not a footer problem\n\nRefs: #1"), [])
        self.assertEqual(self.problems("fix: x\n\nThis fixes the race: see the issue"), [])
        self.assertEqual(self.problems("fix: x\n\nAcked-by: A\nFixes #12\nCo-Authored-By: B <b@b>"), [])


class HouseRules(unittest.TestCase):
    def test_type_list_and_case(self):
        self.assertIn("must be lowercase and one of", validate("Feat: x")[0])
        self.assertIn("must be lowercase and one of", validate("deploy: x")[0])
        self.assertEqual(validate("chore(deps): bump"), [])

    def test_breaking_needs_both_signals(self):
        self.assertIn("no `BREAKING CHANGE", validate("feat!: x")[0])
        self.assertIn("header has no `!`", validate("feat: x\n\nBREAKING CHANGE: y")[0])
        self.assertEqual(validate("feat(api)!: x\n\nBREAKING CHANGE: y"), [])
        self.assertIn("informally", validate("feat: x\n\nthis is a breaking change for callers")[0])
        self.assertEqual(validate("feat!: x\n\nBREAKING CHANGE: callers must pass a config object"), [])

    def test_reports_every_problem(self):
        self.assertEqual(len(validate("Deploy:x\nno blank")), 3)


class FileAndRange(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *a],
                                             cwd=self.dir, check=True, capture_output=True)
        self.git("init", "-q", "-b", "main")
        self.cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self):
        os.chdir(self.cwd)

    def test_message_file_drops_git_comments(self):
        path = os.path.join(self.dir, "COMMIT_EDITMSG")
        with open(path, "w") as f:
            f.write("fix: x\n\nRefs: #1\n# Please enter the commit message\n# ------------------------ >8 ------------------------\ndiff --git a b\n")
        self.assertEqual(message_file(path).strip(), "fix: x\n\nRefs: #1")
        self.assertEqual(main([path]), 0)
        with open(path, "w") as f:
            f.write("wip\n")
        self.assertEqual(main([path]), 1)

    def test_range_mode_flags_only_bad_commits(self):
        open(os.path.join(self.dir, "a"), "w").close()
        self.git("add", "a")
        self.git("commit", "-q", "-m", "feat: good one")
        open(os.path.join(self.dir, "b"), "w").close()
        self.git("add", "b")
        self.git("commit", "-q", "-m", "fixed the thing")
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--range", "HEAD"])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue().count("\n"), 1)
        self.assertIn("fixed the thing", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=1)
