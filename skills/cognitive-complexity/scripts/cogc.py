#!/usr/bin/env python3
"""Cognitive Complexity (SonarSource white paper v1.7) per function. No dependencies.

CLI   python3 cogc.py [--limit N] [--explain] PATH...
      One line per function: `file:line  score  name`, "OVER" when above the limit (default 15).
      --explain adds every increment with its line. A directory is walked and only functions
      over the limit are printed. Exit code 1 if anything is over the limit.
Hook  python3 -I cogc.py < event.json
      Claude Code PreToolUse|PostToolUse on Edit|Write|MultiEdit. PreToolUse saves the file's
      scores; PostToolUse reports functions over the limit that the edit created or made worse.
      Never blocks, prints nothing when there is nothing to say, exits 0 on any failure.
      Test files (test_*.py, *.test.ts, *Tests.cs, ...) are skipped in hook mode.

Python is scored from the AST (exact). Brace languages (JS/TS, Java, C#, Go, Rust, C/C++, Kotlin,
Swift, PHP, Dart, Scala, Groovy) are scored from tokens: exact on the paper's examples, can be off
by one on exotic syntax. Known gaps: indirect recursion, preprocessor conditionals, the JavaScript
"declarative outer function" exception, trailing lambdas without parentheses (Kotlin/Swift/Groovy),
arrow functions without braces.
"""
import ast
import hashlib
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_LIMIT = 15
LANG = {".py": "py", ".pyi": "py", ".js": "js", ".mjs": "js", ".cjs": "js", ".jsx": "js",
        ".ts": "ts", ".tsx": "ts", ".mts": "ts", ".cts": "ts", ".java": "java", ".kt": "kt",
        ".kts": "kt", ".cs": "cs", ".go": "go", ".rs": "rs", ".c": "c", ".h": "c", ".cpp": "cpp",
        ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp", ".swift": "swift",
        ".php": "php", ".dart": "dart", ".scala": "scala", ".groovy": "groovy"}
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "target", "bin", "obj", ".venv",
             "venv", "__pycache__", ".next", "out"}
TEST_FILE = re.compile(r"(^test_|_test\.|\.test\.|\.spec\.|_spec\.|Tests?\.(cs|java|kt|swift)$)")
STATE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "state" / "cognitive-complexity"


class Fn:
    def __init__(self, name, line):
        self.name, self.line, self.incs, self.recursed, self.recv = name, line, [], False, None

    @property
    def score(self):
        return sum(a for _, a, _ in self.incs)

    def inc(self, line, amount, why):
        self.incs.append((line, amount, why))


def why(kind, nesting):
    return f"{kind} (nesting {nesting})" if nesting else kind


# ----------------------------------------------------------------------------- Python (AST)

MATCH = getattr(ast, "Match", None)
TRY = (ast.Try, getattr(ast, "TryStar", ast.Try))
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)
ELSE = re.compile(r"\s*else\s*:")


class PyScorer:
    def __init__(self, text):
        self.fns, self.fn, self.lines = [], None, text.splitlines()

    def else_line(self, first):
        # ast has no node for `else:`; it is the nearest `else:` at or above the branch's first statement
        for i in range(first.lineno - 1, -1, -1):
            if ELSE.match(self.lines[i]):
                return i + 1
        return first.lineno

    def run(self, tree):
        self.defs(tree.body)
        return self.fns

    def defs(self, stmts):
        for s in stmts:
            if isinstance(s, DEFS):
                self.fn = Fn(s.name, s.lineno)
                self.fns.append(self.fn)
                self.block(s.body, 0)
            elif isinstance(s, ast.ClassDef):
                self.defs(s.body)

    @staticmethod
    def is_decorator(stmts):
        """Appendix A: a body that is only a nested def and a return does not nest the inner def."""
        core = [x for x in stmts if not (isinstance(x, ast.Expr) and isinstance(x.value, ast.Constant))]
        return len(core) == 2 and isinstance(core[0], DEFS) and isinstance(core[1], ast.Return)

    def block(self, stmts, n):
        idiom = self.is_decorator(stmts)
        for s in stmts:
            self.stmt(s, n, idiom)

    def stmt(self, s, n, idiom=False):
        fn = self.fn
        if isinstance(s, ast.If):
            fn.inc(s.lineno, 1 + n, why("if", n))
            self.expr(s.test, n)
            self.block(s.body, n + 1)
            self.orelse(s, n)
        elif isinstance(s, (ast.For, ast.AsyncFor, ast.While)):
            fn.inc(s.lineno, 1 + n, why("while" if isinstance(s, ast.While) else "for", n))
            self.expr(s.test if isinstance(s, ast.While) else s.iter, n)
            self.block(s.body, n + 1)
            if s.orelse:
                fn.inc(self.else_line(s.orelse[0]), 1, "else")
                self.block(s.orelse, n + 1)
        elif isinstance(s, TRY):
            self.block(s.body, n)
            for h in s.handlers:
                fn.inc(h.lineno, 1 + n, why("except", n))
                self.block(h.body, n + 1)
            self.block(s.orelse, n)
            self.block(s.finalbody, n)
        elif MATCH is not None and isinstance(s, MATCH):
            fn.inc(s.lineno, 1 + n, why("match", n))
            self.expr(s.subject, n)
            for c in s.cases:
                self.expr(c.guard, n + 1)
                self.block(c.body, n + 1)
        elif isinstance(s, DEFS):
            self.block(s.body, n if idiom else n + 1)  # nested def: no increment, nesting +1
        elif isinstance(s, ast.ClassDef):
            self.block(s.body, n)
        elif isinstance(s, (ast.With, ast.AsyncWith)):
            for item in s.items:
                self.expr(item.context_expr, n)
            self.block(s.body, n)
        else:
            for child in ast.iter_child_nodes(s):
                self.expr(child, n)

    def orelse(self, s, n):
        if not s.orelse:
            return
        first = s.orelse[0]
        # `elif` is an If node in orelse at the same column; `else: if` is indented deeper.
        if len(s.orelse) == 1 and isinstance(first, ast.If) and first.col_offset == s.col_offset:
            self.fn.inc(first.lineno, 1, "elif")
            self.expr(first.test, n)
            self.block(first.body, n + 1)
            self.orelse(first, n)
        else:
            self.fn.inc(self.else_line(first), 1, "else")
            self.block(s.orelse, n + 1)

    def expr(self, e, n):
        if e is None:
            return
        fn = self.fn
        if isinstance(e, ast.BoolOp):
            fn.inc(e.lineno, 1, "and sequence" if isinstance(e.op, ast.And) else "or sequence")
            for v in e.values:
                self.expr(v, n)
        elif isinstance(e, ast.IfExp):
            fn.inc(e.lineno, 1 + n, why("ternary", n))
            self.expr(e.test, n)
            self.expr(e.body, n + 1)
            self.expr(e.orelse, n + 1)
        elif isinstance(e, ast.Lambda):
            self.expr(e.body, n + 1)
        else:
            if isinstance(e, ast.Call) and not fn.recursed:
                f = e.func
                name = f.id if isinstance(f, ast.Name) else (
                    f.attr if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                    and f.value.id in ("self", "cls") else None)
                if name == fn.name:
                    fn.recursed = True
                    fn.inc(e.lineno, 1, "recursion")
            for child in ast.iter_child_nodes(e):
                self.expr(child, n)


# ----------------------------------------------------------------------------- brace languages (tokens)

K, V, L, NL = 0, 1, 2, 3  # token fields: kind, value, line, first-on-line
OPS = ("?->", "...", "&&", "||", "=>", "->", "??", "?.", "?:", "::")
C_DIRECTIVE = {"c", "cpp", "cs"}
RS_CHAR = re.compile(r"'(?:\\(?:u\{[0-9a-fA-F]+\}|x[0-9a-fA-F]{2}|.)|[^'\\])'")
RS_RAW = re.compile(r'b?r(#*)"')
REGEX_PREV = {"return", "typeof", "case", "do", "else", "in", "of", "instanceof", "new", "delete",
              "void", "throw", "yield", "await"}


def tokenize(text, lang):
    toks, i, n, line, first = [], 0, len(text), 1, True

    def add(kind, val):
        nonlocal first
        toks.append((kind, val, line, first))
        first = False

    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            first = True
            continue
        if c.isspace():
            i += 1
            continue
        if c == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += text.count("\n", i, j)
            i = j
            continue
        if c == "#" and (lang == "php" or (lang in C_DIRECTIVE and first)):
            while True:  # comment, or a preprocessor line with backslash continuations
                j = text.find("\n", i)
                j = n if j < 0 else j
                if lang in C_DIRECTIVE and text[i:j].rstrip().endswith("\\") and j < n:
                    line += 1
                    i = j + 1
                    continue
                break
            i = j
            continue
        if lang == "rs" and c in "br" and RS_RAW.match(text, i):
            m = RS_RAW.match(text, i)
            end = '"' + m.group(1)
            j = text.find(end, m.end())
            j = n if j < 0 else j + len(end)
            line += text.count("\n", i, j)
            add("str", '""')
            i = j
            continue
        if c == "'" and lang == "rs" and not RS_CHAR.match(text, i):
            m = re.compile(r"'[A-Za-z_]\w*").match(text, i)  # lifetime or loop label
            add("op", m.group(0) if m else "'")
            i = m.end() if m else i + 1
            continue
        if c in "\"'`":
            if text.startswith(c * 3, i):
                j = text.find(c * 3, i + 3)
                j = n if j < 0 else j + 3
            elif c == '"' and lang == "cs" and "@" in text[max(0, i - 2):i]:
                j = i + 1
                while j < n:
                    if text[j] == '"':
                        if text.startswith('""', j):
                            j += 2
                            continue
                        break
                    j += 1
                j = min(j + 1, n)
            else:
                j = i + 1
                while j < n and text[j] != c:
                    if text[j] == "\\":
                        j += 1
                    elif text[j] == "\n" and c != "`":
                        break  # unterminated: give up at the line end
                    j += 1
                j = min(j + 1, n)
            line += text.count("\n", i, j)
            add("str", '""')
            i = j
            continue
        if c == "/" and lang in ("js", "ts"):  # regex literal?
            prev = toks[-1] if toks else None
            if prev is None or (prev[K] == "op" and prev[V] not in (")", "]", "}")) or \
                    (prev[K] == "id" and prev[V] in REGEX_PREV):
                j, in_class, closed = i + 1, False, False
                while j < n and text[j] != "\n":
                    ch = text[j]
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == "[":
                        in_class = True
                    elif ch == "]":
                        in_class = False
                    elif ch == "/" and not in_class:
                        closed = True
                        break
                    j += 1
                if closed:  # otherwise it was a division or a JSX closing tag `</div>`
                    j += 1
                    while j < n and text[j].isalpha():
                        j += 1
                    add("str", '""')
                    i = j
                    continue
        if c.isalpha() or c in "_$" or (c == "#" and lang in ("js", "ts")):
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] in "_$"):
                j += 1
            add("id", text[i:j])
            i = j
            continue
        if c.isdigit():
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] in "_."):
                j += 1
            add("num", text[i:j])
            i = j
            continue
        for op in OPS:
            if text.startswith(op, i):
                add("op", op)
                i += len(op)
                break
        else:
            if c in "{}()[];,?:!=&|<>.@*+-/%^~":
                add("op", c)
            i += 1
    return toks


CONTROL = {"if", "else", "elseif", "for", "while", "do", "switch", "catch", "try", "finally", "foreach"}
LANG_CONTROL = {"rs": {"loop", "match"}, "kt": {"when"}, "swift": {"guard", "repeat"},
                "go": {"select"}, "scala": {"match"}, "php": {"match"}}
LOOPS = {"for", "foreach", "while", "do", "loop", "repeat"}
SWITCHES = {"switch", "match", "when", "select"}
FN_KW = {"js": "function", "ts": "function", "php": "function", "rs": "fn", "go": "func",
         "swift": "func", "kt": "fun", "scala": "def", "groovy": "def"}
FAT_ARROW = {"js", "ts", "cs", "php", "dart", "scala"}
THIN_ARROW = {"java", "kt", "groovy", "scala"}
TERNARY = {"js", "ts", "java", "cs", "c", "cpp", "swift", "php", "dart", "groovy"}
NO_PAREN_COND = {"go", "rs", "swift"}  # bodies are always braced
BRACE_ELSE = {"rs", "swift"}  # `else` counts only after `}` (guard/let-else otherwise)
TRAILING_LAMBDA = {"kt", "swift", "groovy", "scala"}
DECL = {"class", "struct", "enum", "interface", "record", "object", "trait", "impl", "protocol",
        "extension", "actor", "data", "sealed", "namespace", "new"}
NOT_FN = CONTROL | SWITCHES | LOOPS | DECL | {
    "return", "throw", "typeof", "await", "yield", "case", "default", "sizeof", "delete", "void",
    "defer", "go", "in", "of", "with", "guard", "synchronized", "lock", "using", "fixed", "unless",
    "until", "repeat", "loop", "select", "when", "match", "constexpr", "and", "or", "not", "as",
    "is", "instanceof", "try", "if"}
NOT_OPERAND = NOT_FN | {"else", "do"}
STMT_KW = {"if", "for", "while", "return", "const", "let", "var", "switch", "try", "throw", "break",
           "continue", "do", "function", "class", "export", "import", "else", "foreach", "fn", "func",
           "fun", "val", "def", "match", "loop"}
MEMBER_PREV = {".", "?.", "::", "?->"}
NO_SEMI = {"go", "kt", "swift", "scala", "groovy", "js", "ts"}  # a newline can end a statement
CONTINUATION = {".", "?.", "&&", "||", "?", ":", "=", "+", "-", "*", "/", "%", "<", ">", "=>", "->",
                ",", ")", "]", "{", "?:", "??", "|", "&", "!", "else", "catch", "finally", "while",
                "where", "with", "throws", "extends", "implements", "in", "as", "is", "instanceof", "when"}


class BraceScorer:
    def __init__(self, lang):
        self.lang = lang
        self.fns = []
        self.top = Fn("<top-level>", 1)
        self.stack = []  # brace frames and pending (braceless / ternary) frames
        self.nesting = self.pdepth = 0
        self.head = []  # tokens since the last statement boundary
        self.logical = [None]  # last logical operator of the current sequence, per paren depth
        self.skip_while = self.go_header = False

    # -- helpers
    def cur(self):
        for f in reversed(self.stack):
            if f.get("fn"):
                return f["fn"]
        return self.top

    def push(self, frame):
        self.stack.append(frame)
        self.nesting += frame["bump"]

    def pop(self):
        f = self.stack.pop()
        self.nesting -= f["bump"]
        return f

    def pop_pending(self, pred):
        while self.stack and not self.stack[-1]["brace"] and pred(self.stack[-1]):
            self.pop()

    def structural(self, line, kind):
        self.cur().inc(line, 1 + self.nesting, why(kind, self.nesting))

    def tok(self, i):
        return self.toks[i] if 0 <= i < len(self.toks) else ("op", "", 0, False)

    def is_operand(self, i):
        t = self.tok(i)
        return t[K] in ("num", "str") or (t[K] == "id" and t[V] not in NOT_OPERAND) or t[V] in (")", "]")

    def in_fn(self):
        return any(f.get("fn") for f in self.stack)

    def top_brace_kind(self):
        for f in reversed(self.stack):
            if f["brace"]:
                return f["kind"]
        return None

    # -- main loop
    def run(self, toks):
        self.toks = toks
        for i, t in enumerate(toks):
            k, v = t[K], t[V]
            if t[NL]:
                self.newline(i, t)
            if k == "id":
                self.ident(i, t)
            elif v == "{":
                self.open(t[L])
                continue
            elif v == "}":
                self.close()
                continue
            elif v == ";":
                self.semicolon()
                continue
            elif v == "(":
                self.pdepth += 1
                call = self.is_operand(i - 1) or self.tok(i - 1)[V] == "!"
                self.logical.append(None if call else self.logical[-1])
            elif v == ")":
                self.pdepth -= 1
                if len(self.logical) > 1:
                    self.logical.pop()
                self.pop_pending(lambda f: f["pdepth"] > self.pdepth)
            elif v == ",":
                self.logical[-1] = None
                self.pop_pending(lambda f: f["kind"] == "ternary" and f["pdepth"] == self.pdepth)
            elif v in ("&&", "||"):
                self.logical_op(i, t)
            elif v == "?":
                self.question(i, t)
            elif v in (":", "=", "=>", "->"):
                self.logical[-1] = None
                if v == "=>" and self.lang == "cs":
                    self.cs_expression_member(t[L])
            self.head.append(t)
        return self.fns + ([self.top] if self.top.score else [])

    def newline(self, i, t):
        """Without semicolons, a line that ends in an operand ends the statement unless the next line
        continues it (go/kotlin/swift/scala, JS ASI)."""
        if self.lang not in NO_SEMI or not self.head or self.pdepth != self.enclosing_pdepth():
            return
        last = self.head[-1]
        ends = last[K] in ("id", "num", "str") or last[V] in (")", "]")
        if ends and t[V] not in CONTINUATION and not (t[K] == "id" and last[K] == "id" and t[V] not in STMT_KW and self.lang != "go"):
            self.statement_end(i)

    def ident(self, i, t):
        v, lang, line = t[V], self.lang, t[L]
        prev, nxt = self.tok(i - 1), self.tok(i + 1)
        if prev[V] in MEMBER_PREV or (prev[V] == "->" and lang in ("c", "cpp", "php")):
            self.recursion(i, t)  # member access, e.g. promise.catch( or this.walk(
            return
        if v in ("break", "continue"):
            labeled = nxt[L] == line and ((lang == "rs" and nxt[V].startswith("'")) or
                                          (lang != "rs" and (nxt[K] in ("id", "num") or nxt[V] == "@")))
            if labeled:
                self.cur().inc(line, 1, f"{v} to label")
            return
        if v == "goto":
            if lang == "cs":
                self.structural(line, "goto")  # sonar-dotnet adds nesting to goto, unlike the paper
            else:
                self.cur().inc(line, 1, "goto")
            return
        if lang == "php" and v in ("and", "or", "xor"):
            self.logical_op(i, ("op", v, line, False))
            return
        if lang == "cs" and v in ("and", "or") and nxt[V] not in ("=", ";", ")", ",", "."):
            self.logical_op(i, ("op", v, line, False))  # C# 9 pattern combinators: `is A or B`
            return
        if v not in CONTROL and v not in LANG_CONTROL.get(lang, ()):
            self.recursion(i, t)
            return
        if lang == "go" and v in ("if", "for", "switch", "select"):
            self.go_header = True
        self.expression_body(line)
        if v in ("if", "guard"):
            if lang in ("rs", "scala") and self.is_operand(i - 1) and self.top_brace_kind() == "switch":
                return  # match guard: `Some(x) if x > 0 =>`
            if prev[V] != "else":  # `else if` was counted at the else
                self.structural(line, v)
            self.braceless(i)
        elif v in ("else", "elseif"):
            if lang in BRACE_ELSE and prev[V] != "}":
                return  # swift guard-else, rust let-else
            if lang == "kt" and nxt[V] == "->":
                return  # `when` default arm
            self.cur().inc(line, 1, "else if" if v == "elseif" or nxt[V] == "if" else "else")
            if v == "else" and nxt[V] not in ("if", "{"):
                self.push({"kind": "braceless", "bump": 1, "brace": False, "pdepth": self.pdepth, "body": i + 1})
        elif v in LOOPS:
            if lang == "rs" and v == "for" and (nxt[V] == "<" or any(h[V] == "impl" for h in self.head)):
                return  # `impl Trait for Type`, `for<'a>`
            if v == "while" and self.skip_while:
                self.skip_while = False  # the while of a do-while
                return
            if v == "do" and lang == "swift":
                return  # swift `do {` is a plain block
            self.structural(line, v)
            self.braceless(i)
        elif v in SWITCHES:
            self.structural(line, v)
        elif v == "catch":
            self.structural(line, v)

    def braceless(self, i):
        """`if (x) stmt;` without braces: nest until the statement ends."""
        if self.lang in NO_PAREN_COND:
            return
        j = i + 1
        if self.tok(j)[V] == "constexpr":
            j += 1
        if self.tok(j)[V] == "(":
            depth = 0
            while j < len(self.toks):
                if self.toks[j][V] == "(":
                    depth += 1
                elif self.toks[j][V] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            j += 1
        if self.tok(j)[V] not in ("{", ""):
            self.push({"kind": "braceless", "bump": 1, "brace": False, "pdepth": self.pdepth, "body": j})

    def recursion(self, i, t):
        fn = self.cur()
        if fn.recursed or t[V] != fn.name or self.tok(i + 1)[V] != "(":
            return
        prev, prev2 = self.tok(i - 1)[V], self.tok(i - 2)[V]
        if prev in MEMBER_PREV or prev == "->":
            if prev2 not in ("this", "self", "Self", "$this", "cls", fn.recv):
                return
        elif prev in ("new", "function", "func", "fn", "fun", "def") or prev in DECL:
            return
        fn.recursed = True
        fn.inc(t[L], 1, "recursion")

    def logical_op(self, i, t):
        if not self.is_operand(i - 1):
            return  # rust `&&str`, closure `||`, etc.
        if self.logical[-1] != t[V]:
            self.cur().inc(t[L], 1, f"{t[V]} sequence")
            self.logical[-1] = t[V]

    def question(self, i, t):
        if self.lang not in TERNARY or not self.is_operand(i - 1):
            return
        n1, n2 = self.tok(i + 1), self.tok(i + 2)
        if n1[V] in (">", "extends", "super", "[", ")", ",", ";", "=", "{", "}", ""):
            return  # nullable type, generic wildcard
        if n1[K] == "id" and n2[V] in ("=", ",", ")", ";", ">", "[", "{", "}", ""):
            return  # `int? x = ...`
        if self.lang in ("swift", "cs", "dart") and n1[L] != t[L]:
            return  # `var x: String?` at the end of a line
        depth = 0
        for j in range(i + 1, len(self.toks)):  # a ternary has a `:` before its expression ends
            w, prev = self.toks[j][V], self.toks[j - 1]
            if self.lang in NO_SEMI and self.toks[j][NL] and w not in CONTINUATION and \
                    (prev[K] in ("id", "num", "str") or prev[V] in (")", "]")):
                return  # the statement ended at the line break
            if w in ("(", "[", "{"):
                depth += 1
            elif w in (")", "]", "}"):
                depth -= 1
                if depth < 0:
                    return
            elif depth == 0 and w == ":":
                break
            elif depth == 0 and w in (";", ","):
                return
        else:
            return
        self.structural(t[L], "ternary")
        self.push({"kind": "ternary", "bump": 1, "brace": False, "pdepth": self.pdepth, "body": i + 1})

    def enclosing_pdepth(self):
        for f in reversed(self.stack):
            if f["brace"]:
                return f["pdepth"]
        return 0

    def semicolon(self):
        if self.go_header:
            return  # `for i := 0; i < n; i++ {`
        if self.pdepth != self.enclosing_pdepth():
            return  # `for (;;)`
        self.statement_end(len(self.toks))

    def statement_end(self, i):
        self.pop_pending(lambda f: f["pdepth"] == self.pdepth and f.get("body", 0) < i)
        self.head = []
        self.logical[-1] = None

    def open(self, line):
        kind, name, bump = self.classify()
        words = [t[V] for t in self.head if t[K] == "id"]
        frame = {"kind": kind, "bump": bump, "brace": True, "pdepth": self.pdepth, "name": name or (words[-1] if words else ""),
                 "fn": None, "do": bool(self.head) and self.head[0][V] in ("do", "repeat")}
        if kind == "lambda" and self.lang == "cs" and "static" in words and "=>" not in [t[V] for t in self.head]:
            kind, bump = "fn", 0  # sonar-dotnet scores a static local function on its own, not in its parent
        if kind == "other" and self.pdepth > self.enclosing_pdepth():
            frame["head"] = self.head  # `{}` inside parens (object literal, default arg): the statement goes on after it
        if kind == "fn":
            frame["fn"] = Fn(name, line)
            frame["fn"].recv = self.receiver()
            frame["bump"] = -self.nesting  # a function starts at nesting 0
            self.fns.append(frame["fn"])
        self.push(frame)
        self.head = []
        self.logical[-1] = None
        self.skip_while = self.go_header = False

    def close(self):
        f = None
        while self.stack:
            f = self.pop()
            if f["brace"]:
                break
        self.skip_while = bool(f) and f["kind"] == "loop" and f["do"]
        self.head = f.get("head", []) if f else []
        self.logical[-1] = None
        self.pop_pending(lambda p: p["kind"] in ("braceless", "exprfn") and p["pdepth"] == self.pdepth)

    def expression_body(self, line):
        """kotlin/scala `fun f(x) = when (x) {`: the control structure is the whole function body."""
        kw = FN_KW.get(self.lang)
        vals = [t[V] for t in self.head]
        if self.lang not in ("kt", "scala") or kw not in vals or "=" not in vals[vals.index(kw):]:
            return
        if self.pdepth != self.enclosing_pdepth() or any(f["kind"] == "exprfn" for f in self.stack):
            return
        fn = Fn(self.keyword_name(vals, kw) or "<anonymous>", line)
        self.fns.append(fn)
        self.push({"kind": "exprfn", "bump": -self.nesting, "brace": False, "pdepth": self.pdepth, "fn": fn, "body": 0})

    def cs_expression_member(self, line):
        """C# `int F(int x) => ...;` or `int P => ...;` at class level: the expression up to `;` is the body."""
        vals = [t[V] for t in self.head]
        ids = [t[V] for t in self.head if t[K] == "id"]
        if self.in_fn() or not ids or "=" in vals or self.pdepth != self.enclosing_pdepth() \
                or self.top_brace_kind() == "switch" or any(f["kind"] == "exprfn" for f in self.stack):
            return
        before = vals[:vals.index("(")] if "(" in vals else vals
        name = before[-1] if before else ids[-1]
        if vals in (["get"], ["set"], ["init"]) and self.stack and self.stack[-1]["brace"]:
            name = f'{self.stack[-1]["name"]}.{name}'  # `int Q { get => ...; }`
        fn = Fn(name, line)
        self.fns.append(fn)
        self.push({"kind": "exprfn", "bump": -self.nesting, "brace": False, "pdepth": self.pdepth, "fn": fn, "body": 0})

    # -- what does this `{` open?
    def classify(self):
        lang, head = self.lang, self.head
        vals = [t[V] for t in head]
        opens = []
        for idx, v in enumerate(vals):
            if v in ("(", "["):
                opens.append(idx)
            elif v in (")", "]") and opens:
                opens.pop()
        if opens:  # inside an argument list or array literal
            sub = vals[opens[-1] + 1:]
            if self.lambda_like(sub):
                callee = vals[opens[-1] - 1] if opens[-1] > 0 and head[opens[-1] - 1][K] == "id" else ""
                return self.fn_or_lambda(self.name_from(sub) or (f"<callback in {callee}>" if callee else "<anonymous>"))
            return "other", "", 0
        if not vals:
            return "other", "", 0
        if vals[0] in ("case", "default"):
            return "other", "", 0
        if lang == "rs" and ("=>" in vals or "impl" in vals):
            return "other", "", 0  # match arm, `impl Trait for Type {`
        if lang == "kt" and "->" in vals and self.top_brace_kind() == "switch":
            return "other", "", 0  # when arm
        words = [t[V] for t in head if t[K] == "id"]
        for idx, t in enumerate(head):
            v = t[V]
            if t[K] != "id" or (idx and head[idx - 1][V] in MEMBER_PREV):
                continue
            if lang == "rs" and v == "for" and idx + 1 < len(head) and head[idx + 1][V] == "<":
                continue  # `for<'a> Fn(...)`
            if v in CONTROL or v in LANG_CONTROL.get(lang, ()):
                if v in ("else", "elseif"):
                    nxt = head[idx + 1][V] if idx + 1 < len(head) else ""
                    return ("elseif" if v == "elseif" or nxt == "if" else "else"), "", 1
                if v in ("if", "guard"):
                    return "if", "", 1
                if v in LOOPS:
                    return ("other" if v == "do" and lang == "swift" else "loop"), "", 1
                if v in SWITCHES:
                    return "switch", "", 1
                if v == "catch":
                    return "catch", "", 1
                return "other", "", 0  # try, finally
        if lang == "cs" and vals in (["get"], ["set"], ["init"], ["add"], ["remove"]):
            owner = self.stack[-1]["name"] if self.stack and self.stack[-1]["brace"] else ""
            return self.fn_or_lambda(f"{owner}.{vals[0]}" if owner else vals[0])
        kw = FN_KW.get(lang)
        if kw and kw in words:
            return self.fn_or_lambda(self.keyword_name(vals, kw) or self.name_from(vals) or "<anonymous>")
        if lang == "swift" and vals[0] == "init":
            return self.fn_or_lambda("init")
        if self.lambda_like(vals):
            return self.fn_or_lambda(self.name_from(vals) or "<anonymous>")
        if ")" in vals and lang not in ("go", "rs"):
            r = len(vals) - 1 - vals[::-1].index(")")
            depth, p = 0, r
            while p >= 0:
                depth += (vals[p] == ")") - (vals[p] == "(")
                if depth == 0:
                    break
                p -= 1
            before = vals[p - 1] if p > 0 else ""
            before_kind = head[p - 1][K] if p > 0 else ""
            if any(w in DECL for w in words[:max(0, p)]) or before in NOT_FN:
                return "other", "", 0
            if lang in TRAILING_LAMBDA:
                return ("lambda", "", 1) if self.in_fn() else ("other", "", 0)
            if before_kind == "id":
                return self.fn_or_lambda(before)
            if (lang == "dart" and before in ("(", ",", "=", ":", "return")) or (lang == "cpp" and before == "]"):
                return self.fn_or_lambda("<closure>")
        return "other", "", 0

    def lambda_like(self, vals):
        lang = self.lang
        if lang in FAT_ARROW and "=>" in vals:
            return True
        if lang in THIN_ARROW and "->" in vals:
            return True
        kw = FN_KW.get(lang)
        if kw and kw in vals:
            return True
        if lang == "cs" and "delegate" in vals:
            return True
        if lang == "rs" and ("|" in vals or "||" in vals):
            return True
        if lang == "cpp" and vals and vals[0] == "[":
            return True
        return bool(vals) and lang == "dart" and vals[0] == "(" and vals[-1] == ")"

    def fn_or_lambda(self, name):
        return ("lambda", name, 1) if self.in_fn() else ("fn", name, 0)

    @staticmethod
    def name_from(vals):
        """`const handler = async (req) =>` / `save: function (` -> the name before `=` or `:`."""
        if "(" in vals:
            vals = vals[:vals.index("(")]
        for idx in range(len(vals) - 1, 0, -1):
            if vals[idx] in ("=", ":") and vals[idx - 1] not in ("(", ")", ",", "=", ":"):
                return vals[idx - 1]
        return ""

    @staticmethod
    def keyword_name(vals, kw):
        idx = vals.index(kw) + 1
        if idx < len(vals) and vals[idx] == "*":
            idx += 1
        if idx < len(vals) and vals[idx] == "(" and kw == "func":  # go receiver: func (s *S) Name(
            depth = 0
            while idx < len(vals):
                depth += (vals[idx] == "(") - (vals[idx] == ")")
                idx += 1
                if depth == 0:
                    break
        if idx < len(vals) and vals[idx] not in ("(", "<", "|"):
            return vals[idx]
        return ""

    def receiver(self):
        vals = [t[V] for t in self.head]
        if self.lang == "go" and "func" in vals:
            i = vals.index("func")
            if len(vals) > i + 2 and vals[i + 1] == "(":
                return vals[i + 2]
        return None


# ----------------------------------------------------------------------------- API

def lang_of(path):
    return LANG.get(os.path.splitext(path)[1].lower())


def score_source(text, lang):
    """Return [Fn] for one file's text."""
    if lang == "py":
        return PyScorer(text).run(ast.parse(text))
    return BraceScorer(lang).run(tokenize(text, lang))


def score_file(path):
    lang = lang_of(path)
    if lang is None:
        return []
    return score_source(Path(path).read_text(encoding="utf-8", errors="replace"), lang)


def keyed(fns):
    """{name#n: score}; the n-th function of that name, so renames and moves still match."""
    seen, out = {}, {}
    for fn in fns:
        n = seen.get(fn.name, 0)
        seen[fn.name] = n + 1
        out[f"{fn.name}#{n}"] = fn.score
    return out


# ----------------------------------------------------------------------------- hook

def hook():
    data = json.load(sys.stdin)
    event = data.get("hook_event_name")
    path = (data.get("tool_input") or {}).get("file_path") or ""
    if not path or lang_of(path) is None or TEST_FILE.search(os.path.basename(path)):
        return
    limit = int(os.environ.get("COGNITIVE_COMPLEXITY_LIMIT", DEFAULT_LIMIT))
    state = STATE_DIR / (hashlib.sha1(os.path.abspath(path).encode()).hexdigest() + ".json")
    if event == "PreToolUse":
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            scores = keyed(score_file(path)) if os.path.exists(path) else {}
        except Exception:
            scores = {}
        state.write_text(json.dumps(scores))
        return
    if event != "PostToolUse":
        return
    try:
        before = json.loads(state.read_text())
    except (OSError, ValueError):
        before = {}
    state.unlink(missing_ok=True)
    rel = os.path.relpath(path, data.get("cwd") or os.getcwd())
    if rel.startswith(".."):
        rel = path  # outside the working directory: the absolute path reads better
    rows, fns = [], score_file(path)
    for key, fn in zip(keyed(fns), fns):
        was = before.get(key)
        if fn.score > limit and (was is None or fn.score > was):
            rows.append(f"  {rel}:{fn.line}  {fn.name}  {fn.score}" + (f" (was {was})" if was is not None else " (new)"))
    if not rows:
        return
    msg = (f"Cognitive complexity over {limit} after this edit (SonarSource rules; only functions this edit "
           f"created or made worse are listed):\n" + "\n".join(rows) +
           "\nLower it before moving on: extract the deepest nested block into its own function, return early "
           "instead of nesting, replace if/else-if chains over one value with a switch or a lookup. "
           f"Breakdown per line: python3 {sys.argv[0]} --explain {rel}. Rules: the cognitive-complexity skill.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))


# ----------------------------------------------------------------------------- CLI

def files_in(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for name in sorted(names):
                    f = os.path.join(root, name)
                    if lang_of(f):
                        yield f, True
        else:
            yield p, False


def main(argv):
    limit, explain, paths = DEFAULT_LIMIT, False, []
    it = iter(argv)
    for a in it:
        if a == "--limit":
            limit = int(next(it))
        elif a == "--explain":
            explain = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            paths.append(a)
    if not paths:
        if sys.stdin.isatty():
            print(__doc__)
            return 2
        hook()
        return 0
    over = False
    for path, from_dir in files_in(paths):
        try:
            fns = score_file(path)
        except (OSError, SyntaxError, ValueError) as e:
            print(f"{path}: {e}", file=sys.stderr)
            continue
        for fn in fns:
            if from_dir and fn.score <= limit:
                continue
            flag = "  OVER" if fn.score > limit else ""
            over = over or bool(flag)
            print(f"{path}:{fn.line}  {fn.score:>3}  {fn.name}{flag}")
            if explain:
                for line, amount, reason in fn.incs:
                    print(f"      {line:>5}  +{amount}  {reason}")
    return 1 if over else 0


if __name__ == "__main__":
    if sys.argv[1:]:
        sys.exit(main(sys.argv[1:]))
    try:
        main([])
    except Exception:
        pass
    sys.exit(0)
