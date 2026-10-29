#!/usr/bin/env python3
"""
Realistic estimates for work Claude does itself: a ledger of measured turns, and a Stop hook that
rejects estimates in human units (hours, days, "half a day", sprints) in favour of measured minutes.

Hook, SessionStart: prints the measured pace table and the estimating rule as context. With no ledger yet
                    it first seeds one from every transcript under ~/.claude/projects.
Hook, Stop:         logs the turn that just ended (active and idle seconds, tool calls, edits, lines
                    written, test runs, questions asked) to ~/.claude/state/estimates/ledger.jsonl, then
                    scans the reply for a human-scale estimate. Found: decision=block with the table and
                    the exact line shape to reply with; a correction that carries no number is blocked
                    once more, then the turn may end. ESTIMATES_MODE=warn shows the user a systemMessage
                    instead; off disables the scan (the turn is still logged).
CLI:
  python3 estimates.py [--table]       the pace table
  python3 estimates.py --rebuild       rescan every transcript and rewrite the ledger
  python3 estimates.py --recent N      the last N measured turns
  python3 estimates.py --check TEXT    run the detector on TEXT (- reads stdin); exit 1 if it finds one

Register in ~/.claude/settings.json:
    SessionStart matcher "startup|resume|clear|compact": python3 -I ~/.claude/hooks/estimates.py
    Stop:                                                 python3 -I ~/.claude/hooks/estimates.py
Any failure in hook mode exits 0 with no output.
"""
import json
import os
import re
import select
import statistics
import sys
from datetime import datetime
from pathlib import Path

# A longer silence inside a turn is the user away (permission prompt, question), not Claude working.
GAP_S = 600
CLASSES = (("XS", 20), ("S", 100), ("M", 400), ("L", 1200), ("XL", None))
LABELS = {"XS": "<20", "S": "<100", "M": "<400", "L": "<1200", "XL": "1200+"}
EDIT_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
# Files written through Bash (auto mode does this) are invisible to the edit tools; heredoc bodies count instead.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n\s*\2\s*$", re.S | re.M)
TEST_RE = re.compile(r"\b(pytest|unittest|npm test|pnpm test|yarn test|bun test|dotnet test|go test|cargo test|"
                     r"jest|vitest|mocha|rspec|phpunit|mvn test|gradle test)\b", re.I)

NUM = (r"(?:\d+(?:[.,]\d+)?|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
       r"(?:a )?couple(?: of)?|(?:a )?few|several|many|multiple|some)")
UNIT = r"(?:hours?|hrs?|days?|weeks?|wks?|months?|sprints?|afternoons?|mornings?|evenings?|work(?:ing)?[- ]?days?)"
DURATION = re.compile(rf"\b(?:{NUM}\s*(?:(?:to|-|–|or)\s*{NUM}\s*)?{UNIT}|\d+(?:\.\d+)?\s?h|"
                      r"half[- ]a[- ]day|half[- ]days?|all day|a day or two|a full day|the rest of the day)\b", re.I)
CONTEXT = re.compile(r"\b(?:estimat\w*|eta|effort|budget\w*|time-?box\w*|takes?|taking|for me|of work|worth of|"
                     r"plan(?:ning|ned|s)?|about|around|roughly|approximately|needs?|require\w*|allow|allot\w*|"
                     r"set aside|expect\w*)\b|~", re.I)
# Past tense and actuals, schedules and config, a human doing the work, calendar events.
EXCLUDE = re.compile(r"\b(?:took|spent|elapsed|lasted|ago|was|were|has been|have been|had been|ran for|"
                     r"time-?outs?|ttl|cron|every|intervals?|expir\w*|cache\w*|retention|sla|rate[- ]?limits?|"
                     r"windows?|poll\w*|sleep|delays?|backoff|debounce|uptime|downtime|at \d|"
                     r"humans?|developers?|devs?|engineers?|person|people|someone|contractors?|team|by hand|"
                     r"manually|junior|senior|you|your|yours|yourself|"
                     r"meetings?|calls?|workshops?|old|yesterday|last week|last month)\b", re.I)
CODE = re.compile(r"```.*?```|`[^`\n]*`|https?://\S+", re.S)
MINUTES = re.compile(r"\b\d+(?:\.\d+)?\s*(?:(?:to|-|–|or)\s*\d+(?:\.\d+)?\s*)?min(?:ute)?s?\b", re.I)
SHAPE = ("Claude: <median> to <p90> min (<class>, ~<lines> lines in <files> files, n=<turns>). "
         "You: ~<minutes> min (<what they read or decide>).")
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")

RULE = ('Estimating work Claude does itself: size it in files and lines, quote the class\'s median to p90 in '
        'minutes with the class and n, and give the user\'s own minutes (reading, decisions, manual tests) '
        'separately, e.g. "Claude: 10 to 25 min (L, ~500 lines, n=20). You: ~5 min." Hours, days, "half a '
        'day" and sprints measure a human typing; the estimates Stop hook rejects them unless the sentence '
        'names a human doing the work. Full rules: the estimates skill.')
EMPTY = ("No measured turns yet: the ledger fills as turns complete, and "
         "`python3 ~/.claude/hooks/estimates.py --rebuild` seeds it from past transcripts. "
         "Until then: a turn that writes a few hundred lines takes minutes, not hours.")


def claude_dir():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def ledger_path():
    return claude_dir() / "state" / "estimates" / "ledger.jsonl"



def find_estimates(text):
    """[(duration phrase, sentence)] for every sentence that estimates in hours or longer."""
    hits = []
    for sentence in SENTENCE.split(CODE.sub(" ", text)):
        if EXCLUDE.search(sentence) or not CONTEXT.search(sentence):
            continue
        for m in DURATION.finditer(sentence):
            hits.append((m.group(0), sentence.strip()))
    return hits



def _is_prompt(d):
    if d.get("type") != "user":
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, str):
        return bool(c.strip())
    if isinstance(c, list):
        kinds = {b.get("type") for b in c if isinstance(b, dict)}
        return "text" in kinds and "tool_result" not in kinds
    return False


def _lines(name, inp):
    if not isinstance(inp, dict):
        return 0
    if name == "MultiEdit":
        return sum(str(e.get("new_string", "")).count("\n") + 1 for e in inp.get("edits", []) if isinstance(e, dict))
    key = {"Write": "content", "Edit": "new_string", "NotebookEdit": "new_source"}[name]
    return str(inp.get(key, "")).count("\n") + 1


def _count(row, block):
    name, inp = block.get("name", ""), block.get("input")
    row["tools"] += 1
    if name in EDIT_TOOLS:
        row["edits"] += 1
        row["lines"] += _lines(name, inp)
    elif name == "Bash":
        command = str(inp.get("command", "")) if isinstance(inp, dict) else ""
        row["bash"] += 1
        row["lines"] += sum(m.group(3).count("\n") + 1 for m in HEREDOC.finditer(command))
        if TEST_RE.search(command):
            row["tests"] += 1
    elif name == "AskUserQuestion":
        row["asks"] += 1
    elif name in ("Agent", "Task"):
        row["agents"] += 1


def _entries(path):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for raw in text.splitlines():
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get("type") not in ("user", "assistant"):
            continue
        if d.get("isSidechain") or d.get("isMeta"):
            continue
        try:
            yield datetime.fromisoformat(str(d.get("timestamp")).replace("Z", "+00:00")).timestamp(), d
        except ValueError:
            continue


def _new_row(path, d):
    return {"session": Path(path).stem, "start": d["timestamp"], "cwd": d.get("cwd", ""),
            "active_s": 0, "idle_s": 0, "tools": 0, "edits": 0, "lines": 0, "bash": 0,
            "tests": 0, "asks": 0, "agents": 0}


def _tool_uses(d):
    if d["type"] != "assistant":
        return
    for b in (d.get("message") or {}).get("content") or []:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            yield b


def turns(path):
    """One row per user prompt: wall clock split into active and idle, and what the tools did."""
    rows, cur, last = [], None, 0.0
    for t, d in _entries(path):
        if _is_prompt(d):
            cur = _new_row(path, d)
            rows.append(cur)
            last = t
            continue
        if cur is None:
            continue
        gap = max(0, round(t - last))
        last = t
        cur["idle_s" if gap > GAP_S else "active_s"] += gap
        for b in _tool_uses(d):
            _count(cur, b)
    return rows


def append_row(row):
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def read_ledger():
    """Rows in first-seen order; a turn logged twice (a Stop that continued) keeps its last row."""
    try:
        raw = ledger_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    by = {}
    for line in raw:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict):
            by[(r.get("session"), r.get("start"))] = r
    return list(by.values())


def rebuild():
    rows = []
    for f in sorted((claude_dir() / "projects").glob("*/*.jsonl")):
        rows += turns(f)
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return len(rows)



def size_class(lines):
    for name, limit in CLASSES:
        if limit is None or lines < limit:
            return name


def _p90(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(0.9 * (len(xs) - 1)))]


def table(rows):
    work = [r for r in rows if r.get("tools", 0) > 0]
    if not work:
        return EMPTY
    sessions = len({r.get("session") for r in work})
    out = [f"Measured pace: {len(work)} turns with tool calls in {sessions} session{'s' if sessions != 1 else ''}. "
           f"Active minutes per turn, silences over {GAP_S // 60} min removed.",
           f"{'size':5} {'lines':>6} {'turns':>6} {'median':>7} {'p90':>6}  {'tool calls':>10}"]
    for name, _ in CLASSES:
        rs = [r for r in work if size_class(r.get("lines", 0)) == name]
        if not rs:
            continue
        mins = [r.get("active_s", 0) / 60 for r in rs]
        out.append(f"{name:5} {LABELS[name]:>6} {len(rs):6d} {statistics.median(mins):7.1f} {_p90(mins):6.1f}  "
                   f"{statistics.median(r.get('tools', 0) for r in rs):10.0f}")
    return "\n".join(out)



def _session_start():
    if not ledger_path().exists():
        rebuild()
    return f"ESTIMATES (estimates hook).\n{table(read_ledger())}\n{RULE}"


def _block_file(session_id):
    return ledger_path().parent / f"block-{re.sub(r'[^A-Za-z0-9_-]', '_', str(session_id or 'unknown'))}.json"


def _blocks_this_turn(session_id, start):
    try:
        state = json.loads(_block_file(session_id).read_text(encoding="utf-8"))
        return state["count"] if state.get("start") == start else 0
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def _remember_blocks(session_id, start, count):
    f = _block_file(session_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"start": start, "count": count}), encoding="utf-8")


def _follow_up(data, start, message):
    """After our own block, the correction must carry a number: one more block, then let go."""
    session = data.get("session_id")
    if _blocks_this_turn(session, start) != 1:
        return None
    _remember_blocks(session, start, 2)
    if MINUTES.search(message):
        return None
    reason = f"estimates: the correction has no number. Reply with only the corrected line:\n  {SHAPE}\n{table(read_ledger())}"
    return json.dumps({"decision": "block", "reason": reason})


def _stop(data):
    start = ""
    if data.get("transcript_path"):
        rows = turns(os.path.expanduser(data["transcript_path"]))
        if rows:
            append_row(rows[-1])
            start = rows[-1]["start"]
    mode = os.environ.get("ESTIMATES_MODE", "block").lower()
    if mode == "off":
        return None
    message = data.get("last_assistant_message") or ""
    if data.get("stop_hook_active"):
        return _follow_up(data, start, message) if mode == "block" else None
    hits = find_estimates(message)
    if not hits:
        return None
    found = "\n".join(f'  "{phrase}" in: {sentence[:160]}' for phrase, sentence in hits[:5])
    if mode == "warn":
        return json.dumps({"systemMessage": f"estimates: the reply estimates in human units:\n{found}"})
    _remember_blocks(data.get("session_id"), start, 1)
    reason = (f"estimates: the reply estimates in human units, which measure a person typing:\n{found}\n"
              f"Continue with the corrected estimate and nothing else: one line per flagged sentence, "
              f"numbers from the table below, in this shape:\n  {SHAPE}\n"
              f"Pick the class by the lines the work will write. A sentence that estimates a human's work "
              f"keeps its hours and says so (\"for a human developer\").\n{table(read_ledger())}")
    return json.dumps({"decision": "block", "reason": reason})


def hook(data):
    """The text to print for this hook event, or None."""
    event = data.get("hook_event_name")
    if event == "SessionStart":
        return _session_start()
    if event == "Stop":
        return _stop(data)
    return None



def _recent(rows):
    print(f"{'start':20} {'active':>7} {'idle':>6} {'lines':>6} {'tools':>5} {'tests':>5} {'size':4}  project")
    for r in rows:
        print(f"{r.get('start', '')[:19]:20} {r.get('active_s', 0) / 60:6.1f}m {r.get('idle_s', 0) / 60:5.0f}m "
              f"{r.get('lines', 0):6d} {r.get('tools', 0):5d} {r.get('tests', 0):5d} "
              f"{size_class(r.get('lines', 0)):4}  {os.path.basename(r.get('cwd', ''))}")


def _stdin_payload():
    """Hook JSON from stdin, or "" when nothing is piped: a tty, or the idle open pipe the Bash tool gives."""
    if sys.stdin.isatty():
        return ""
    ready, _, _ = select.select([sys.stdin], [], [], 1.0)  # shortcut: POSIX only, upgrade if a Windows user appears
    return sys.stdin.read() if ready else ""


def main(argv):
    if not argv or argv == ["--table"]:
        print(table(read_ledger()))
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd in ("-h", "--help"):
        print(__doc__)
        return 0
    if cmd == "--rebuild":
        print(f"{rebuild()} turns written to {ledger_path()}")
        return 0
    if cmd == "--recent":
        work = sorted((r for r in read_ledger() if r.get("tools", 0) > 0), key=lambda r: r.get("start", ""))
        _recent(work[-(int(rest[0]) if rest else 10):])
        return 0
    if cmd == "--check":
        text = sys.stdin.read() if rest in ([], ["-"]) else " ".join(rest)
        hits = find_estimates(text)
        for phrase, sentence in hits:
            print(f'"{phrase}" in: {sentence[:160]}')
        return 1 if hits else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    if sys.argv[1:]:
        sys.exit(main(sys.argv[1:]))
    raw = _stdin_payload()
    if not raw.strip():
        sys.exit(main([]))
    try:
        out = hook(json.loads(raw))
        if out:
            print(out)
    except Exception:
        pass
    sys.exit(0)
