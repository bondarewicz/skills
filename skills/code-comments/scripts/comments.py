#!/usr/bin/env python3
"""Flags comments that do not earn their place: restating the next line of code, narrating the change,
commented-out code, banners, end markers, doc comments that only repeat the signature. No dependencies.

CLI   python3 comments.py [--ratio R] PATH...
      One line per flagged comment: `file:line  kind  text`, then the comment density of each file
      above the ratio (default 0.3 of non-blank lines). Directories are walked. Exit 1 if anything
      is printed.
Hook  python3 -I comments.py < event.json
      Claude Code PreToolUse on Edit|Write|MultiEdit. Applies the edit in memory, looks only at the
      comment lines it adds, and denies the edit when any is flagged, with the list as the reason so
      the agent resubmits without them. Density alone is advisory. CODE_COMMENTS_MODE=warn makes
      everything advisory, off disables. CODE_COMMENTS_MAX_RATIO sets the density limit.
      Prints nothing and exits 0 when there is nothing to say or on any internal failure.

Languages: C-family (JS/TS, Java, C#, Go, Rust, C/C++, Objective-C, Kotlin, Swift, PHP, Dart, Scala,
Groovy) by a string-aware scanner; Python via tokenize (exact, docstrings count as doc comments);
shell, Ruby, Perl, R, PowerShell by a `#` scanner. Known gaps: `//` inside a JS regex literal,
heredocs, Ruby =begin blocks, PowerShell <# #> blocks, Python docstrings when the file does not tokenize.
"""
import io
import json
import os
import re
import sys
import tokenize
from collections import Counter

DEFAULT_RATIO = 0.3
C_EXT = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts", ".java", ".kt", ".kts", ".cs",
         ".go", ".rs", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".m", ".mm", ".swift",
         ".php", ".dart", ".scala", ".groovy"}
HASH_EXT = {".sh", ".bash", ".zsh", ".rb", ".pl", ".pm", ".r", ".ps1", ".psm1"}
PY_EXT = {".py", ".pyi"}
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "target", "bin", "obj", ".venv",
             "venv", "__pycache__", ".next", "out"}

# Comments that are instructions to tools, legal text, references or test-structure labels.
EXEMPT = re.compile(
    r"^(#!|eslint|prettier|biome|@ts-|ts-|noqa|type:\s*ignore|pylint|pyright|mypy|flake8|ruff|nolint|"
    r"istanbul|c8 |v8 |nosonar|sonar|pragma|noinspection|resharper|@formatter|checkstyle|nopmd|"
    r"@suppresswarnings|swiftlint|clang-format|go:|\+build|cspell|spell-checker|webpack|vite-ignore|"
    r"rubocop|fmt:|coding[:=]|-\*-|<reference|@flow|@jsx|@ts-check|region\b|endregion\b|mark:|"
    r"todo\b|fixme\b|hack\b|xxx\b|spdx|copyright|\(c\)\s*\d|licen[sc]e|https?://|www\.|#\d+\b|[A-Z]{2,}-\d+\b|"
    r"(arrange|act|assert|given|when|then|setup|teardown|cleanup)\s*[:.]?\s*$|@\w+|\{@)", re.I)
TAG_RESTATES = re.compile(
    r"^(@param\s+(\{[^}]*\}\s+)?\[?(?P<p>\w+)\]?\s*[-:]?\s*(the|a|an)?\s*(?P=p)\s*\.?$"
    r"|@returns?\s*:?\s*(the|a|an)?\s*(result|results|value|values|response|output|promise|task|boolean|bool|"
    r"string|number|int|integer|list|array|object|void|nothing|data|this|it)\s*\.?$"
    r"|<param\s+name=\"(?P<q>\w+)\"\s*>\s*(the|a|an)?\s*(?P=q)\s*\.?\s*</param>$"
    r"|<returns>\s*(the|a|an)?\s*(result|value|response|task|list|data|it)\s*\.?\s*</returns>$)", re.I)
NARRATION = re.compile(
    r"^(added|updated|changed|fixed|removed|moved|renamed|refactored|modified|replaced|introduced|implemented)\s+(?!so\b|at\b|for\b|in\b|by\b|point|size|width|height|length)\w"
    r"|\b(no longer|previously|used to be|was (changed|updated|moved|removed|added|renamed)|as requested|"
    r"now (uses|returns|handles|supports|takes|accepts|requires|checks|calls|includes|also)|"
    r"(new|old) (code|logic|implementation|version))\b|^(in |as part of |with )?this (change|edit|fix|pr|commit|update|refactor)\b"
    r"|\b(here,? we|this (function|method|class|block|section|code|line|loop|helper|hook|component|module|file) "
    r"(does|handles|checks|returns|creates|takes|loops|iterates|calls|gets|sets|uses|contains|defines|implements|"
    r"computes|calculates|performs|processes|wraps|validates|ensures|provides))\b"
    r"|^(first|then|next|now|finally|lastly|after that|at this point),?\s+(we|i)\b"
    r"|\b(we|i|let's)\s+(now|then|first|next|also|simply|just|can now|will now|are going to)\b"
    r"|^step \d", re.I)
END_MARKER = re.compile(
    r"^(end|ends|close|closing)(\s+of)?\s+(the\s+)?(if|else|for|foreach|while|do|switch|case|try|catch|finally|"
    r"function|fn|func|def|method|class|struct|interface|enum|namespace|module|block|loop|region|section|with|"
    r"match|when|begin|constructor|lambda|closure|scope|package|impl|trait|type|object|main|program|file|"
    r"\w+\(\))\b.{0,30}$|^(end|ends)(\s+of)?\s+\w+$|^end$", re.I)
BANNER = re.compile(r"([-=*#_~+/\\])\1{3,}")
KEYWORD_START = re.compile(
    r"^(import|from|using|package|export|const|let|var|val|def|fn|func|function|class|struct|enum|interface|"
    r"return|if|else|elif|for|foreach|while|switch|case|try|catch|except|finally|throw|raise|new|await|async|"
    r"public|private|protected|internal|static|override|print|console|System|self|this|super|namespace|module|"
    r"require|yield|break|continue|delete|typeof|instanceof|void|int|string|bool|boolean|double|float|long|char)\b")
SIGNATURE = re.compile(
    r"^(export\s+|pub(\(\w+\))?\s+|public\s+|private\s+|protected\s+|internal\s+|static\s+|async\s+|override\s+|"
    r"virtual\s+|abstract\s+|default\s+|final\s+|open\s+)*(def|fn|func|function|class|struct|interface|enum|"
    r"trait|impl|record|type|get|set|constructor|init|[A-Za-z_][\w<>\[\]?,.]*\s+[A-Za-z_]\w*\s*[(<{]|"
    r"[A-Za-z_]\w*\s*[(<]|[A-Za-z_]\w*\s*\{\s*get)")
STOP = set("the a an to of for and or is are it its this that we if then with in on by from as be will into "
           "at not no any all each every when so than also just only here there up out do does did has have "
           "had was were been can should would could may might must using use used via our your their my you "
           "which who whom whose what where how these those some such other another more most very".split())
IMPERATIVE = {"return", "get", "set", "create", "compute", "calculate", "check", "validate", "build", "make",
              "fetch", "load", "find", "parse", "convert", "handle", "process", "run", "execute", "initialize",
              "update", "delete", "remove", "add", "read", "write", "send", "apply", "determine", "retrieve",
              "generate", "perform", "construct", "render", "format", "resolve", "register", "prune", "clear",
              "reset", "count", "try", "ensure", "verify", "wrap", "call", "invoke", "emit", "dispatch", "test",
              "increment", "decrement", "iterate", "loop", "store", "save", "insert", "append", "push", "pop",
              "sort", "filter", "map", "merge", "copy", "clone", "start", "stop", "open", "close", "log", "print"}
# Comment verb or noun -> tokens that express it in code.
SYN = {"return": {"return", "=>"}, "loop": {"for", "while", "foreach", "each", "map", "loop"},
       "iterate": {"for", "while", "foreach", "each", "map", "iter"}, "increment": {"++", "+="},
       "decrement": {"--", "-="}, "check": {"if", "assert", "throw", "raise", "?", "expect", "is"},
       "verify": {"if", "assert", "throw", "raise", "expect"}, "ensure": {"if", "assert", "throw", "raise"},
       "validate": {"if", "assert", "throw", "raise", "valid"}, "guard": {"if", "throw", "raise", "return"},
       "call": {"("}, "invoke": {"("}, "create": {"new", "create", "make", "build", "("},
       "instantiate": {"new"}, "construct": {"new"}, "initialize": {"=", "new", "init"}, "init": {"=", "new"},
       "set": {"=", "set"}, "assign": {"="}, "store": {"=", "set", "put", "save", "store"},
       "define": {"const", "let", "var", "def", "function", "fn", "func", "class", "interface", "type", "val"},
       "declare": {"const", "let", "var", "def", "function", "fn", "func", "class", "interface", "type", "val"},
       "import": {"import", "using", "require", "from"}, "throw": {"throw", "raise"}, "raise": {"throw", "raise"},
       "log": {"log", "console", "print", "println", "logger", "debug", "info", "warn", "error"},
       "print": {"print", "println", "console", "log"}, "wait": {"await", "sleep", "delay"},
       "fetch": {"fetch", "get", "load", "find", "query", "select", "request", "http"},
       "get": {"get", "fetch", "load", "find", "read"}, "retrieve": {"get", "fetch", "load", "find", "read"},
       "load": {"load", "get", "fetch", "read"}, "read": {"read", "get", "load"},
       "update": {"update", "set", "=", "put", "patch"}, "delete": {"delete", "remove", "del", "drop"},
       "remove": {"delete", "remove", "del", "drop", "splice"}, "add": {"add", "push", "append", "insert", "+=", "+"},
       "append": {"add", "push", "append", "+="}, "push": {"push", "add", "append"},
       "convert": {"to", "parse", "as", "cast", "convert", "map"}, "parse": {"parse", "json", "int", "float"},
       "compute": {"=", "compute", "calc", "sum"}, "calculate": {"=", "compute", "calc", "sum"},
       "sort": {"sort", "order"}, "filter": {"filter", "where"}, "exit": {"return", "exit", "break", "continue"},
       "stop": {"return", "exit", "break", "stop"}, "skip": {"continue", "return", "if", "skip"},
       "handle": {"catch", "handle", "handler", "on"}, "catch": {"catch", "except"},
       "close": {"close", "dispose", "end"}, "start": {"start", "begin", "run"}, "run": {"run", "exec", "execute"},
       "execute": {"run", "exec", "execute"}, "send": {"send", "post", "emit", "publish", "dispatch"},
       "emit": {"emit", "dispatch", "send"}, "clear": {"clear", "reset", "null", "delete"},
       "reset": {"reset", "clear", "="}, "otherwise": {"else", "??", "||"}, "fallback": {"??", "||", "default", "else"},
       "default": {"default", "??", "||"}, "null": {"null", "none", "nil", "undefined"},
       "empty": {"empty", "length", "count", "size", "0", "[]", "any"}, "length": {"length", "len", "count", "size"},
       "count": {"count", "length", "len", "size"}, "size": {"size", "length", "len", "count"},
       "list": {"list", "array", "[]"}, "array": {"array", "list", "[]"}, "map": {"map", "dict", "dictionary", "record"},
       "dictionary": {"dict", "dictionary", "map"}, "function": {"function", "fn", "func", "def", "=>"},
       "method": {"def", "function", "public", "private", "static"}, "constructor": {"constructor", "init", "new"},
       "variable": {"const", "let", "var", "val"}, "constant": {"const", "static", "readonly", "final"},
       "error": {"error", "err", "exception", "throw", "catch", "raise"}, "exception": {"exception", "error", "throw", "catch"},
       "result": {"result", "res", "return", "ret"}, "callback": {"callback", "cb", "=>", "handler"},
       "promise": {"promise", "async", "await", "then", "task"}, "async": {"async", "await"},
       "total": {"total", "sum", "+="}, "sum": {"sum", "total", "+", "+="}, "round": {"round", "math", "floor", "ceil"},
       "compare": {"==", "===", "<", ">", "compare", "equal"}, "equal": {"==", "===", "equal"},
       "exist": {"if", "has", "exist", "in", "include", "contain"}, "contain": {"include", "contain", "has", "in"},
       "assert": {"assert", "expect", "should"}, "expect": {"expect", "assert"}, "export": {"export", "module"},
       "case": {"case", "switch", "when", "match"}, "switch": {"switch", "case", "match"},
       "condition": {"if", "?", "&&", "||"}, "index": {"index", "i", "idx", "["}, "element": {"item", "el", "element", "entry"},
       "item": {"item", "el", "element", "entry"}, "entry": {"entry", "item", "entries"}, "first": {"first", "0", "head"},
       "last": {"last", "pop", "-"}, "next": {"next", "++", "+"}, "copy": {"copy", "clone", "...", "slice"},
       "merge": {"merge", "...", "assign", "concat"}, "timestamp": {"time", "date", "now", "timestamp", "ts"},
       "time": {"time", "now", "date", "ms"}, "current": {"now", "current", "cur"}, "negative": {"<", "-"},
       "positive": {">", "+"}, "range": {"<", ">", "range", "for"}, "enable": {"true", "enable", "on"},
       "disable": {"false", "disable", "off"}, "expired": {"<", ">", "expire", "now", "time"},
       "old": {"<", "expire", "stale", "prev"}, "new": {"new", "create"}, "config": {"config", "cfg", "settings", "options", "opts"},
       "setting": {"setting", "config", "option"}, "option": {"option", "opts", "config"},
       "database": {"db", "database", "repo", "repository", "sql", "query", "prisma", "context"},
       "db": {"db", "database"}, "request": {"request", "req", "fetch", "http"}, "response": {"response", "res", "resp"},
       "input": {"input", "value", "field", "param", "arg", "args"}, "output": {"output", "return", "result", "out"},
       "user": {"user", "usr", "account"}, "id": {"id", "key"}, "key": {"key", "id"}, "window": {"window", "win"},
       "limit": {"limit", "max", "take"}, "maximum": {"max", "limit"}, "minimum": {"min"},
       "percent": {"100", "percent", "pct"}, "discount": {"discount", "percent", "-"}, "tax": {"tax", "rate"},
       "price": {"price", "amount", "cost", "unit"}, "quantity": {"quantity", "qty", "count"},
       "message": {"message", "msg", "text"}, "string": {"string", "str"}, "number": {"number", "int", "num"},
       "boolean": {"bool", "boolean"}, "object": {"object", "obj", "{"}, "class": {"class"}, "type": {"type", "interface", ":"},
       "property": {"get", "set", "prop"}, "field": {"private", "readonly", "field"}, "state": {"state", "store"},
       "event": {"event", "on", "emit", "listener", "handler", "e"}, "handler": {"handler", "on", "handle", "=>"},
       "flag": {"bool", "boolean", "true", "false", "is", "has"}, "cache": {"cache", "memo"}, "retry": {"retry", "attempt", "for", "while"},
       "lock": {"lock", "mutex"}, "thread": {"thread", "worker", "task"}, "file": {"file", "fs", "path", "read", "write"},
       "path": {"path", "route", "url", "dir", "file"}, "url": {"url", "uri", "href", "path"},
       "dispose": {"dispose", "close", "using"}, "cleanup": {"dispose", "close", "clear", "delete", "clean"},
       "prune": {"delete", "remove", "filter", "prune", "splice"}, "drop": {"delete", "remove", "drop", "splice"},
       "apply": {"apply", "*", "-", "+", "="}, "accumulate": {"+=", "sum", "total"}, "multiply": {"*"},
       "divide": {"/"}, "subtract": {"-"}, "exist": {"if", "has", "exist", "in"}}
RETURNS_TAG = re.compile(r"^(@returns?\s*:?|<returns>)\s*(?P<t>.*?)\s*(</returns>)?$", re.I)
TYPE_DEF = re.compile(r"\b(class|struct|interface|record|enum|trait|impl|module|object)\s+([A-Z]\w*)")
CAUSAL = re.compile(r"\b(because|since|so that|otherwise|unless|in case|avoids?|prevents?|workaround|instead|rather than|must|cannot|can't|won't|would|was|were|needs?|requires?)\b", re.I)
SYM = re.compile(r"\+\+|--|\+=|-=|\*=|/=|===|==|!==|!=|<=|>=|=>|->|\?\?|\?\.|\|\||&&|\.\.\.|[=+\-*/<>!?.(\[{%]")
CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


class Line:
    __slots__ = ("n", "code", "comment", "doc")

    def __init__(self, n, code="", comment=None, doc=False):
        self.n, self.code, self.comment, self.doc = n, code, comment, doc


# scanners

def family_of(path):
    ext = os.path.splitext(path)[1].lower()
    return "py" if ext in PY_EXT else "c" if ext in C_EXT else "hash" if ext in HASH_EXT else None


def scan_c(text, lang):
    """Per line: the code part (strings included) and the comment part, with doc = ///, //!, /** or /*!."""
    rows, code, com, doc = [], [], None, False
    state, quote, esc = "code", "", True
    i, n, ln = 0, len(text), 1
    while i < n:
        ch = text[i]
        two = text[i:i + 2]
        if ch == "\n":
            rows.append(Line(ln, "".join(code).strip(), None if com is None else "".join(com).strip(), doc))
            ln += 1
            i += 1
            code = []
            if state == "block":
                com = []
            else:
                com, doc = None, False
                if state == "line":
                    state = "code"
            continue
        if state == "line":
            com.append(ch)
        elif state == "block":
            if two == "*/":
                state = "code"
                i += 1
            else:
                com.append(ch)
        elif state == "str":
            code.append(ch)
            if esc and ch == "\\":
                code.append(text[i + 1:i + 2])
                i += 1
            elif quote == '"' and not esc and two == '""':
                i += 1  # C# verbatim string doubled quote
            elif text.startswith(quote, i):
                i += len(quote) - 1
                state = "code"
        elif two == "//" or (lang == "php" and ch == "#" and text[i + 1:i + 2] != "["):
            state, com = "line", []
            three = text[i:i + 3]
            doc = three in ("///", "//!") and text[i:i + 4] != "////"
            i += 2 if doc else (1 if ch == "#" else 1)
        elif two == "/*":
            state, com = "block", []
            doc = text[i:i + 3] in ("/**", "/*!") and text[i:i + 4] != "/**/"
            i += 2 if doc else 1
        elif ch in "\"'`":
            if ch == "'" and lang == "rs" and not re.match(r"'(\\.|[^'\\])'", text[i:i + 4]):
                code.append(ch)  # Rust lifetime
            else:
                state = "str"
                quote = ch * 3 if text.startswith(ch * 3, i) and ch != "`" else ch
                esc = not (lang == "cs" and text[i - 1:i] == "@") and not (lang == "go" and ch == "`") \
                    and not (lang == "rs" and text[i - 1:i] == "r")
                code.append(quote)
                i += len(quote) - 1
        else:
            code.append(ch)
        i += 1
    rows.append(Line(ln, "".join(code).strip(), None if com is None else "".join(com).strip(), doc))
    return rows


def scan_hash(text):
    rows = []
    for ln, raw in enumerate(text.split("\n"), 1):
        q, i, cut = None, 0, None
        while i < len(raw):
            ch = raw[i]
            if q:
                if ch == "\\" and q == '"':
                    i += 1
                elif ch == q:
                    q = None
            elif ch in "\"'":
                q = ch
            elif ch == "#" and (i == 0 or raw[i - 1] in " \t;("):
                cut = i
                break
            i += 1
        rows.append(Line(ln, (raw if cut is None else raw[:cut]).strip(), None if cut is None else raw[cut + 1:].strip()))
    return rows


def scan_py(text):
    src = text.split("\n")
    rows = [Line(i + 1, s.strip()) for i, s in enumerate(src)]
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(text).readline)
                if t.type not in (tokenize.NL, tokenize.ENCODING)]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return scan_hash(text)
    stmt_start = (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
    for k, t in enumerate(toks):
        if t.type == tokenize.COMMENT:
            row = rows[t.start[0] - 1]
            row.comment, row.code = t.string[1:].strip(), src[t.start[0] - 1][:t.start[1]].strip()
        elif (t.type == tokenize.STRING and (k == 0 or toks[k - 1].type in stmt_start)
              and k + 1 < len(toks) and toks[k + 1].type in (tokenize.NEWLINE, tokenize.ENDMARKER)):
            for ln in range(t.start[0], t.end[0] + 1):
                row = rows[ln - 1]
                row.comment, row.code, row.doc = re.sub(r"^[rbuRBU]*(\"\"\"|'''|\"|')|(\"\"\"|'''|\"|')$", "", src[ln - 1].strip()), "", True
    return rows


def scan(text, path):
    fam = family_of(path)
    if fam == "py":
        return scan_py(text)
    if fam == "hash":
        return scan_hash(text)
    return scan_c(text, os.path.splitext(path)[1].lower().lstrip("."))


# judging

def clean(s):
    s = re.sub(r"^[*/!\s]+", "", s.strip())
    return re.sub(r"^\*+\s?", "", s).strip()


def stem(w):
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]
    if w.endswith("ing") and len(w) > 5:
        w = w[:-3]
        if len(w) > 2 and w[-1] == w[-2]:
            w = w[:-1]
    elif w.endswith("ed") and len(w) > 4:
        w = w[:-2]
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


def code_tokens(code):
    toks = set(SYM.findall(code))
    for ident in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code):
        for part in CAMEL.findall(ident):
            w = part.lower()
            toks.add(w)
            toks.add(stem(w))
    toks.update(re.findall(r"\d+", code))
    return toks


def restates(comment, code):
    words = [w for w in re.findall(r"[a-z0-9]+", re.sub(r"<[^>]+>", " ", comment).lower())
             if w not in STOP and len(w) > 1 and not w.isdigit()]
    if not words or not code:
        return False
    toks = code_tokens(code)
    long_toks = [t for t in toks if len(t) >= 4]
    signature = bool(SIGNATURE.match(code))
    hit = 0
    for i, w in enumerate(words):
        s = stem(w)
        if (i == 0 and signature and len(words) > 1 and (w.endswith("s") or w in IMPERATIVE)) or w in toks or s in toks \
                or (len(s) >= 4 and any(t.startswith(s) or s.startswith(t) for t in long_toks)) \
                or any(x in toks for x in SYN.get(s, set()) | SYN.get(w, set())):
            hit += 1
    return hit / len(words) >= 0.6


def looks_like_code(s):
    if s.endswith((";", "{", "}")) or re.fullmatch(r"[\]\)\}]+;?", s):
        return True
    if re.fullmatch(r"[\w.$:]+\((.*)\);?", s):
        return True
    if re.match(r"^[\w.\[\]$]+\s*(=|\+=|-=|\*=|\|\|=|\?\?=|:=)\s*\S", s) and not re.match(r"^\w+\s*=\s*\w+(\s+\w+){3,}$", s):
        return True
    prose = sum(1 for t in s.split() if t.isalpha())
    return bool(KEYWORD_START.match(s) and re.search(r"[()=\[\].:<>\"']", s) and prose < 6)


def judge(text, first, code_after, doc):
    """Return the kind of a comment line that does not earn its place, or None."""
    s = clean(text)
    bare = re.sub(r"<[^>]+>", " ", s).strip()
    if not bare and not TAG_RESTATES.match(s):
        return None
    if TAG_RESTATES.match(s):
        return "restating"
    m = RETURNS_TAG.match(s)
    if m:  # "<returns>The invoice.</returns>" above "Invoice? Get(Guid id)"
        return "restating" if code_after and restates(m.group("t"), code_after) else None
    if EXEMPT.match(s) or EXEMPT.match(bare):
        return None
    if looks_like_code(s):
        return "commented-out code"
    if BANNER.search(s):
        return "banner"
    if END_MARKER.match(bare):
        return "end marker"
    if NARRATION.search(bare):
        return "narration"
    if first and code_after and not CAUSAL.search(bare) and restates(bare, code_after):
        return "restating"
    return None


def comments_of(rows):
    """Yield (row, text, first_in_run, code_after, is_exempt) for every comment line."""
    out, run_seen, prev_comment, prev_doc, prev_code, type_name = [], False, False, False, "", ""
    for idx, row in enumerate(rows):
        m = TYPE_DEF.search(row.code) if row.code else None
        if m:
            type_name = m.group(2)
        if row.comment is None:
            run_seen, prev_comment = False, False
            if row.code:
                prev_code = row.code
            continue
        if row.code or not prev_comment or row.doc != prev_doc:  # inline comments and docstrings are their own run
            run_seen = False
        prev_comment, prev_doc = not row.code, row.doc
        text = clean(row.comment)
        bare = re.sub(r"<[^>]+>", " ", text).strip()
        exempt = not bare or bool(EXEMPT.match(text) or EXEMPT.match(bare))
        first = not run_seen and not exempt
        if not exempt:
            run_seen = True
        code_after = row.code
        if not code_after and row.doc and re.match(r"^(async\s+)?(def|class)\b", prev_code):
            code_after = prev_code  # a Python docstring documents the line above it
        if not code_after:
            for later in rows[idx + 1:]:
                if later.code:
                    code_after = later.code
                    break
        if code_after and type_name and SIGNATURE.match(code_after):
            code_after += " " + type_name  # "Creates a new rate limiter" above constructor(...)
        if row.code:
            prev_code = row.code
        out.append((row, text, first, code_after, exempt))
    return out


def check(old_text, new_text, path, ratio):
    """Flagged comment lines that new_text adds over old_text, plus (added comment lines, added code lines)."""
    old_rows = scan(old_text, path) if old_text else []
    new_rows = scan(new_text, path)
    old_comments = Counter(clean(r.comment) for r in old_rows if r.comment is not None)
    old_code = Counter(r.code for r in old_rows if r.code)
    flagged, n_comment, n_code = [], 0, 0
    for row in new_rows:
        if row.code and row.comment is None:
            if old_code[row.code] > 0:
                old_code[row.code] -= 1
            else:
                n_code += 1
    for row, text, first, code_after, exempt in comments_of(new_rows):
        if old_comments[text] > 0:
            old_comments[text] -= 1
            continue
        if row.code:
            n_code += 1
        if not exempt and not row.doc and text:
            n_comment += 1
        kind = judge(row.comment, first, code_after, row.doc)
        if kind:
            flagged.append((row.n, kind, text))
    return flagged, n_comment, n_code


def density(n_comment, n_code, ratio):
    return n_comment >= 3 and n_comment / (n_comment + n_code) > ratio


# hook

def apply_edit(text, edit):
    old, new = edit.get("old_string", ""), edit.get("new_string", "")
    if old not in text:
        return None
    return text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)


def hook():
    data = json.load(sys.stdin)
    mode = os.environ.get("CODE_COMMENTS_MODE", "block").lower()
    if data.get("hook_event_name") != "PreToolUse" or mode == "off":
        return
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ""
    if not path or family_of(path) is None:
        return
    old = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            old = f.read()
    tool = data.get("tool_name")
    if tool == "Write":
        new = ti.get("content") or ""
    elif tool == "Edit":
        new = apply_edit(old, ti)
    elif tool == "MultiEdit":
        new = old
        for e in ti.get("edits") or []:
            new = apply_edit(new, e) if new is not None else None
    else:
        return
    if new is None or new == old:
        return
    ratio = float(os.environ.get("CODE_COMMENTS_MAX_RATIO", DEFAULT_RATIO))
    flagged, n_comment, n_code = check(old, new, path, ratio)
    rel = os.path.relpath(path, data.get("cwd") or os.getcwd())
    if rel.startswith(".."):
        rel = path
    out = {"hookEventName": "PreToolUse"}
    if flagged:
        rows = "\n".join(f"  {rel}:{n}  {kind}  {text[:100]}" for n, kind, text in flagged)
        msg = (f"code-comments: {len(flagged)} of the comment lines this edit adds say what the code already says:\n{rows}\n"
               "Resubmit the same edit without these lines. Keep a comment only when it says what the code cannot: the why, "
               "a constraint, a unit, a reference; a doc comment must say more than the signature. Rules: the code-comments skill.")
        if mode == "block":
            out.update(permissionDecision="deny", permissionDecisionReason=msg + " (CODE_COMMENTS_MODE=warn makes this advisory.)")
        else:
            out["additionalContext"] = msg
    elif density(n_comment, n_code, ratio):
        out["additionalContext"] = (f"code-comments: this edit adds {n_comment} comment lines for {n_code} lines of code "
                                    f"({n_comment / (n_comment + n_code):.0%}, limit {ratio:.0%}). Keep the ones that say why; "
                                    "drop the ones that say what.")
    else:
        return
    print(json.dumps({"hookSpecificOutput": out}))


# CLI

def files_in(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for name in sorted(names):
                    f = os.path.join(root, name)
                    if family_of(f):
                        yield f
        else:
            yield p


def main(argv):
    ratio, paths = DEFAULT_RATIO, []
    it = iter(argv)
    for a in it:
        if a == "--ratio":
            ratio = float(next(it))
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
    bad = False
    for path in files_in(paths):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            print(f"{path}: {e}", file=sys.stderr)
            continue
        flagged, n_comment, n_code = check("", text, path, ratio)
        for n, kind, text in flagged:
            print(f"{path}:{n}  {kind}  {text[:100]}")
        if density(n_comment, n_code, ratio):
            print(f"{path}  density  {n_comment} comment lines for {n_code} code lines ({n_comment / (n_comment + n_code):.0%})")
        bad = bad or bool(flagged) or density(n_comment, n_code, ratio)
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1:]:
        sys.exit(main(sys.argv[1:]))
    try:
        main([])
    except Exception:
        pass
    sys.exit(0)
