#!/usr/bin/env python3
"""Fixtures for the ddd hook: domain-path detection, using extraction, forbidden matching.

    python3 test_ddd.py
"""
import unittest

from ddd import forbidden, is_domain_path, parse_allow, usings


class DomainPath(unittest.TestCase):
    def test_yes(self):
        for p in ("src/Orders/Domain/Order.cs", "Acme.Orders.Domain/Order.cs", "domain/x.cs", "/abs/ACME.DOMAIN/A.cs"):
            self.assertTrue(is_domain_path(p), p)

    def test_no(self):
        for p in ("Acme.Orders.Api/C.cs", "Acme.DomainEvents/X.cs", "src/Orders/Domain/Order.ts", "Orders.Domain/OrderTests.cs",
                  "Orders.Domain/tests/X.cs", "Orders.Domain/Test/X.cs"):
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


if __name__ == "__main__":
    unittest.main()
