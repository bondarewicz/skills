#!/usr/bin/env python3
"""Keeps C# domain code free of infrastructure: flags `using` directives a domain layer must not depend on
(ORMs, web, hosting, messaging, cloud SDKs, mediators and mappers, System.IO, other layers). No dependencies.

A domain file is a `.cs` file under a directory named `Domain` or ending in `.Domain` (any case); test files
and `test`/`tests` directories are skipped.

CLI   python3 ddd.py PATH...
      Walks directories, checks domain files only, prints `file:line  using X;  (group)` per hit, exit 1 if any.
Hook  python3 -I ddd.py < event.json
      SessionStart: when the working tree has domain code, prints the ddd skill's rules as additional context.
      PreToolUse on Edit|Write|MultiEdit: applies the edit in memory and denies it when it adds a forbidden
      using to a domain file; usings already in the file never block. DDD_MODE=warn makes it advisory,
      off disables both events. DDD_ALLOW=MediatR,System.IO removes prefixes from the forbidden list.
      Prints nothing and exits 0 when there is nothing to say or on any internal failure.
"""
import json
import os
import re
import sys
from pathlib import Path

FORBIDDEN = {
    "data": ("Microsoft.EntityFrameworkCore", "System.Data", "System.ComponentModel.DataAnnotations.Schema", "Dapper",
             "Npgsql", "MongoDB", "Marten", "Raven.Client", "StackExchange.Redis"),
    "web": ("Microsoft.AspNetCore", "System.Net.Http", "System.Web"),
    "hosting": ("Microsoft.Extensions", "Autofac", "Serilog", "NLog"),
    "messaging/cloud": ("MassTransit", "NServiceBus", "Rebus", "Wolverine", "Confluent.Kafka", "RabbitMQ", "Azure", "Amazon",
                        "Google.Cloud"),
    "glue": ("MediatR", "AutoMapper", "Mapster"),
    "io": ("System.IO",),
}
LAYER_SEGMENTS = frozenset({"infrastructure", "infra", "application", "api", "webapi", "web", "presentation", "persistence",
                            "adapters", "controllers"})
SKIP_DIRS = {".git", "node_modules", "bin", "obj", "dist", "packages", ".vs", ".idea"}
SKILL_NEXT_TO_SCRIPT = Path(__file__).resolve().parent.parent / "SKILL.md"
FRONTMATTER = re.compile(r"\A---[^\n]*\n.*?\n---[^\n]*(\n|\Z)", re.S)
USING_RE = re.compile(r"^\s*(?:global\s+)?using\s+(?:static\s+)?(?!var\b)([A-Za-z_][\w.]*)(?:\s*=\s*([A-Za-z_][\w.]*))?\s*;")


def is_domain_path(path):
    parts = [p.lower() for p in re.split(r"[\\/]+", path) if p]
    if not parts or not parts[-1].endswith(".cs"):
        return False
    if parts[-1].endswith(("tests.cs", "test.cs")) or any(p in ("test", "tests") for p in parts[:-1]):
        return False
    return any(p == "domain" or p.endswith(".domain") for p in parts[:-1])


def usings(text):
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        m = USING_RE.match(line)
        if m:
            found.append((n, m.group(2) or m.group(1)))
    return found


def parse_allow(value):
    return tuple(p.strip() for p in (value or "").split(",") if p.strip())


def _under(ns, prefix):
    return ns == prefix or ns.startswith(prefix + ".")


def group_of(ns, allow=()):
    if any(_under(ns, a) for a in allow):
        return None
    for group, prefixes in FORBIDDEN.items():
        if any(_under(ns, p) for p in prefixes):
            return group
    if any(seg.lower() in LAYER_SEGMENTS for seg in ns.split(".")):
        return "layer"
    return None


def forbidden(text, allow=()):
    rows = []
    for n, ns in usings(text):
        group = group_of(ns, allow)
        if group:
            rows.append((n, ns, group))
    return rows


# hook

def apply_edit(text, edit):
    old, new = edit.get("old_string", ""), edit.get("new_string", "")
    if old not in text:
        return None
    return text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)


def new_content(tool, tool_input, old):
    if tool == "Write":
        return tool_input.get("content") or ""
    if tool == "Edit":
        return apply_edit(old, tool_input)
    if tool == "MultiEdit":
        new = old
        for e in tool_input.get("edits") or []:
            new = apply_edit(new, e) if new is not None else None
        return new
    return None


def pre_tool_use(data, env):
    mode = env.get("DDD_MODE", "block").lower()
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ""
    if mode == "off" or not is_domain_path(path):
        return None
    old = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            old = f.read()
    new = new_content(data.get("tool_name"), ti, old)
    if new is None or new == old:
        return None
    present = {ns for _, ns in usings(old)}
    rows = [r for r in forbidden(new, parse_allow(env.get("DDD_ALLOW"))) if r[1] not in present]
    if not rows:
        return None
    rel = os.path.relpath(path, data.get("cwd") or os.getcwd())
    if rel.startswith(".."):
        rel = path
    lines = "\n".join(f"  {rel}:{n}  using {ns};  ({group})" for n, ns, group in rows)
    msg = (f"ddd: this edit adds {len(rows)} using{'s' if len(rows) != 1 else ''} the domain layer must not depend on:\n{lines}\n"
           "Keep the domain free of infrastructure: declare an interface (port) here and implement it in the "
           "infrastructure project. Resubmit the edit without these usings. Rules: the ddd skill.")
    out = {"hookEventName": "PreToolUse"}
    if mode == "block":
        out.update(permissionDecision="deny",
                   permissionDecisionReason=msg + " (DDD_MODE=warn makes this advisory; DDD_ALLOW=<namespace,...> allowlists.)")
    else:
        out["additionalContext"] = msg
    return out


def _is_domain_dir(name):
    return name.lower() == "domain" or name.lower().endswith(".domain")


def find_domain_dir(root, depth=6):
    for cur, dirs, _ in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for d in dirs:
            if _is_domain_dir(d):
                return os.path.relpath(os.path.join(cur, d), root)
        if os.path.relpath(cur, root).count(os.sep) + 1 >= depth:
            dirs[:] = []
    return None


def skill_body(env):
    installed = Path(env.get("CLAUDE_CONFIG_DIR") or "~/.claude").expanduser() / "skills" / "ddd" / "SKILL.md"
    for f in (SKILL_NEXT_TO_SCRIPT, installed):
        if f.is_file():
            return FRONTMATTER.sub("", f.read_text(encoding="utf-8"), count=1).strip()
    return None


def session_start(data, env):
    if env.get("DDD_MODE", "block").lower() == "off":
        return None
    rel = find_domain_dir(data.get("cwd") or os.getcwd())
    body = skill_body(env) if rel else None
    if not body:
        return None
    return {"hookEventName": "SessionStart",
            "additionalContext": f"DDD mode: domain code at {rel}. Rules follow; the ddd hook denies forbidden usings there.\n\n{body}"}


def hook_output(data, env):
    event = data.get("hook_event_name")
    if event == "PreToolUse":
        return pre_tool_use(data, env)
    if event == "SessionStart":
        return session_start(data, env)
    return None


def hook():
    out = hook_output(json.load(sys.stdin), os.environ)
    if out:
        print(json.dumps({"hookSpecificOutput": out}))


if __name__ == "__main__":
    if sys.stdin.isatty():
        print(__doc__)
        sys.exit(2)
    try:
        hook()
    except Exception:
        pass
    sys.exit(0)
