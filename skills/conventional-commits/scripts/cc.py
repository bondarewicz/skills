#!/usr/bin/env python3
"""Conventional Commits 1.0.0 validator (conventionalcommits.org/en/v1.0.0). No dependencies.

CLI        python3 cc.py -m "feat(api): add rate limit"     one message
           python3 cc.py .git/COMMIT_EDITMSG                 a message file; git's comment lines are ignored
           python3 cc.py --range origin/main..HEAD           every commit in a range, `sha  problem` per line
           --spec checks the specification only, without the house rules below.
           One line per problem; exit 1 if any.
Git hook   ln -s ~/.claude/hooks/conventional-commits.py .git/hooks/commit-msg   (per repo)
Claude     confirm-git.py imports validate() from this file when both sit in ~/.claude/hooks, so a
           `git commit` by Claude is checked with the same rules before it runs.

House rules on top of the spec: the type is lowercase and one of feat fix docs style refactor perf
test build ci chore revert; a breaking change needs both `!` in the header and a `BREAKING CHANGE:`
footer; a message that mentions a breaking change informally must use them.
"""
import os
import re
import subprocess
import sys

TYPES = "feat fix docs style refactor perf test build ci chore revert".split()
HEADER = re.compile(r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^()]*)\))?(?P<bang>!)?(?P<colon>:\s*)(?P<desc>.*)$")
FOOTER = re.compile(r"^(?P<token>BREAKING[ -]CHANGE|[A-Za-z][\w-]*)(?P<sep>: | #)(?P<value>.*)$")
SPACED_TOKEN = re.compile(r"^(?!BREAKING CHANGE)([A-Za-z][\w]*(?: [\w]+)+)(: | #)")
BREAKING_ANY = re.compile(r"^\s*breaking[ -]change\s*:", re.I | re.M)
BREAKING_OK = re.compile(r"^BREAKING[ -]CHANGE: \S", re.M)


def parse(msg):
    """type, scope, breaking, description, body (list of paragraphs), footers [(token, value)]. None if no header."""
    lines = msg.strip("\n").split("\n")
    m = HEADER.match(lines[0].rstrip())
    if not m:
        return None
    paras, cur = [], []
    for line in lines[1:]:
        if line.strip():
            cur.append(line)
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    footers, footer_lines = [], []
    if paras and (FOOTER.match(paras[-1][0]) or SPACED_TOKEN.match(paras[-1][0])):
        footer_lines = paras.pop()
        for line in footer_lines:
            f = FOOTER.match(line)
            if f:
                footers.append([f.group("token"), f.group("value")])
            elif footers:
                footers[-1][1] += "\n" + line  # a footer value may span lines
    return {"type": m.group("type"), "scope": m.group("scope"), "description": m.group("desc").strip(),
            "breaking": bool(m.group("bang")) or any(t.upper().replace("-", " ") == "BREAKING CHANGE" for t, _ in footers),
            "body": ["\n".join(p) for p in paras], "footers": [tuple(f) for f in footers], "footer_lines": footer_lines}


def validate(msg, house=True):
    """Problems with a commit message as a list of strings; empty when it conforms."""
    lines = msg.strip("\n").split("\n")
    header = lines[0]
    m = HEADER.match(header)
    if not m:
        return [f'header "{header.rstrip()[:80]}" must be `type(scope)!: description`; scope and ! are optional, the colon and space are not']
    problems = []
    t, scope, bang, colon, desc = m.group("type", "scope", "bang", "colon", "desc")
    if colon != ": ":
        problems.append("the colon after the type must be followed by exactly one space")
    if house and t not in TYPES:
        problems.append(f"type `{t}` must be lowercase and one of {', '.join(TYPES)}")
    if scope is not None and not scope.strip():
        problems.append("scope in parentheses is empty; drop the parentheses or name a section of the codebase")
    if not desc.strip():
        problems.append("description after the colon is empty")
    if len(lines) > 1 and lines[1].strip():
        problems.append("line 2 must be blank: the body starts one blank line after the description")
    rest = "\n".join(lines[1:])
    for bad in BREAKING_ANY.findall(rest):
        if not re.match(r"^BREAKING[ -]CHANGE:$", bad.strip()):
            problems.append(f"`{bad.strip()}` must be the uppercase `BREAKING CHANGE: ` (or `BREAKING-CHANGE: `) followed by what breaks")
    if re.search(r"^BREAKING[ -]CHANGE:\s*$", rest, re.M):
        problems.append("`BREAKING CHANGE:` needs a description of what breaks and how to migrate")
    parsed = parse(msg)
    if parsed and parsed["footers"]:  # a lone "Words words: x" paragraph is prose; next to a real footer it is a broken token
        for line in parsed["footer_lines"]:
            s = SPACED_TOKEN.match(line)
            if s:
                problems.append(f"footer token `{s.group(1)}` must use `-` instead of spaces, e.g. `{s.group(1).replace(' ', '-')}:`")
    if house:
        footer = bool(BREAKING_OK.search(rest))
        if bang and not footer:
            problems.append("header has `!` but there is no `BREAKING CHANGE: <what breaks and how to migrate>` footer; add it")
        if footer and not bang:
            problems.append("message has a BREAKING CHANGE footer but the header has no `!` (e.g. `feat(api)!: ...`); add it")
        if not footer and not bang and re.search(r"breaking[ -]?change", rest, re.I):
            problems.append("message mentions a breaking change informally; if it breaks something use `!` in the header and a "
                            "`BREAKING CHANGE: ...` footer, otherwise reword")
    return problems


def message_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    text = text.split("\n# ------------------------ >8 ------------------------")[0]  # git's scissors line
    return "\n".join(l for l in text.split("\n") if not l.startswith("#"))


def commits(rng):
    out = subprocess.check_output(["git", "log", "--format=%H%x1e%B%x1f", rng], text=True, encoding="utf-8", errors="replace")
    for rec in out.split("\x1f"):
        if rec.strip():
            sha, _, body = rec.strip("\n").partition("\x1e")
            yield sha.strip()[:7], body


def main(argv):
    house, msg, rng, path = True, None, None, None
    it = iter(argv)
    for a in it:
        if a in ("-m", "--message"):
            msg = next(it)
        elif a == "--range":
            rng = next(it)
        elif a == "--spec":
            house = False
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            path = a
    if rng:
        bad = False
        for sha, body in commits(rng):
            for p in validate(body, house):
                print(f"{sha}  {p}")
                bad = True
        return 1 if bad else 0
    if msg is None:
        if path is None:
            print(__doc__)
            return 2
        msg = message_file(path)
    problems = validate(msg, house)
    for p in problems:
        print(p, file=sys.stderr if path else sys.stdout)
    if problems and path:
        print(f"commit message rejected ({len(problems)} problem{'s' if len(problems) > 1 else ''}); "
              f"fix it with: git commit --edit --file={os.path.relpath(path)}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
