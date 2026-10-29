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
import re

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
