#!/usr/bin/env python3
"""Fixtures with known scores: the white paper's worked examples plus one small sample per language.

    python3 test_cogc.py
"""
import unittest

from cogc import score_source

# --- SonarSource white paper, "Cognitive Complexity" v1.7 --------------------------------------

PAPER_JAVA = (r'''
int sumOfPrimes(int max) {
  int total = 0;
  OUT: for (int i = 1; i <= max; ++i) {
    for (int j = 2; j < i; ++j) {
      if (i % j == 0) {
        continue OUT;
      }
    }
    total += i;
  }
  return total;
}

String getWords(int number) {
    switch (number) {
      case 1:
        return "one";
      case 2:
        return "a couple";
      case 3:
        return "a few";
      default:
        return "lots";
    }
}

void myMethod () {
  try {
    if (condition1) {
      for (int i = 0; i < 10; i++) {
        while (condition2) { ... }
      }
    }
  } catch (ExcepType1 | ExcepType2 e) {
    if (condition2) { ... }
  }
}

void myMethod2 () {
  Runnable r = () -> {
    if (condition1) { ... }
  };
}

@Nullable
private MethodJavaSymbol overriddenSymbolFrom(ClassJavaType classType) {
  if (classType.isUnknown()) {
    return Symbols.unknownMethodSymbol;
  }

  boolean unknownFound = false;
  List<JavaSymbol> symbols = classType.getSymbol().members().lookup(name);
  for (JavaSymbol overrideSymbol : symbols) {
    if (overrideSymbol.isKind(JavaSymbol.MTH)
            && !overrideSymbol.isStatic()) {

      MethodJavaSymbol methodJavaSymbol = (MethodJavaSymbol)overrideSymbol;
      if (canOverride(methodJavaSymbol)) {
        Boolean overriding = checkOverridingParameters(methodJavaSymbol,
                      classType);
        if (overriding == null) {
          if (!unknownFound) {
            unknownFound = true;
          }
        } else if (overriding) {
          return methodJavaSymbol;
        }
      }
    }
  }

  if (unknownFound) {
    return Symbols.unknownMethodSymbol;
  }

  return null;
}

private void addVersion(final Entry entry, final Transaction txn)
      throws PersistitInterruptedException, RollbackException {
  final TransactionIndex ti = _persistit.getTransactionIndex();
  while (true) {
    try {
      synchronized (this) {
        if (frst != null) {
          if (frst.getVersion() > entry.getVersion()) {
            throw new RollbackException();
          }
          if (txn.isActive()) {
            for
                (Entry e = frst; e != null; e = e.getPrevious()) {
              final long version = e.getVersion();
              final long depends = ti.wwDependency(version,
                    txn.getTransactionStatus(), 0);
              if (depends == TIMED_OUT) {
                throw new WWRetryException(version);
              }
              if (depends != 0
                    && depends != ABORTED) {
                throw new RollbackException();
              }
            }
          }
        }
        entry.setPrevious(frst);
        frst = entry;
        break;
      }
    } catch (final WWRetryException re) {
      try {
        final long depends = _persistit.getTransactionIndex()
              .wwDependency(re.getVersionHandle(),txn.getTransactionStatus(),
              SharedResource.DEFAULT_MAX_WAIT_TIME);
        if (depends != 0
              && depends != ABORTED) {
          throw new RollbackException();
        }
      } catch (final InterruptedException ie) {
        throw new PersistitInterruptedException(ie);
      }
    } catch (final InterruptedException ie) {
      throw new PersistitInterruptedException(ie);
    }
  }
}

private static String toRegexp(String antPattern,
      String directorySeparator) {

  final String escapedDirectorySeparator = '\\' + directorySeparator;
  final StringBuilder sb = new StringBuilder(antPattern.length());
  sb.append('^');
  int i = antPattern.startsWith("/") ||
      antPattern.startsWith("\\") ? 1 : 0;

  while (i < antPattern.length()) {

    final char ch = antPattern.charAt(i);
    if (SPECIAL_CHARS.indexOf(ch) != -1) {
      sb.append('\\').append(ch);
    } else if (ch == '*') {
      if (i + 1 < antPattern.length()
            && antPattern.charAt(i + 1) == '*') {

        if (i + 2 < antPattern.length()
              && isSlash(antPattern.charAt(i + 2))) {
          sb.append("(?:.*")
              .append(escapedDirectorySeparator).append("|)");
          i += 2;
        } else {
          sb.append(".*");
          i += 1;
        }
      } else {
        sb.append("[^").append(escapedDirectorySeparator).append("]*?");
      }
    } else if (ch == '?') {
      sb.append("[^").append(escapedDirectorySeparator).append("]");
    } else if (isSlash(ch)) {
      sb.append(escapedDirectorySeparator);
    } else {
      sb.append(ch);
    }
    i++;
  }

  sb.append('$');
  return sb.toString();
}
''', {"sumOfPrimes": 7, "getWords": 1, "myMethod": 9, "myMethod2": 2,
      "overriddenSymbolFrom": 19, "addVersion": 35, "toRegexp": 20})

PAPER_JS = ('''
Y.Model = {
save: function (options, callback) {
  var self = this;

  if (typeof options === 'function') {
    callback = options;
    options  = {};
  }

  options || (options = {});

  self._validate(self.toJSON(), function (err) {
    if (err) {
      callback && callback.call(null, err);
      return;
    }

    self.sync(self.isNew() ? 'create' : 'update',
        options, function (err, response) {
        var facade = {
            options : options,
            response: response
          },
        parsed;

      if (err) {
        facade.error = err;
        facade.src   = 'save';
        self.fire(EVT_ERROR, facade);

      } else {
        if (!self._saveEvent) {
          self._saveEvent = self.publish(EVT_SAVE, {
            preventable: false
          });
        }

        if (response) {
          parsed = facade.parsed = self._parse(response);
          self.setAttrs(parsed, options);
        }

        self.changed = {};
        self.fire(EVT_SAVE, facade);
      }

      callback && callback.apply(null, arguments);
    });
  });
  return self;
}
};
''', {"save": 20})

PAPER_PY = ('''
def a_decorator(a, b):
  def inner(func):
    if condition:
      print(b)
    func()
  return inner

def not_a_decorator(a, b):
  my_var = a*b
  def inner(func):
    if condition:
      print(b)
    func()
  return inner

def decorator_generator(a):
  def generator(func):
    def decorator(func):
      if condition:
        print(b)
      return func()
    return decorator
  return generator
''', {"a_decorator": 1, "not_a_decorator": 2, "decorator_generator": 1})

# --- one sample per language -------------------------------------------------------------------

PY = ('''
class Svc:
    def process(self, orders, user):
        total = 0
        for order in orders:                                   # +1
            if order.status == "paid" and order.amount > 0:    # +2 +1
                for item in order.items:                       # +3
                    if item.sku in user.blocked or item.qty == 0:  # +4 +1
                        continue
                    total += item.price * item.qty
            elif order.status == "refunded":                   # +1
                total -= order.amount
            else:                                              # +1
                log(order)
        try:
            save(total)
        except IOError:                                        # +1
            return None
        return total if total > 0 else 0                       # +1

    def walk(self, node):
        if node is None:                 # +1
            return 0
        return 1 + sum(self.walk(c) for c in node.children)   # +1 recursion

def tidy(xs):
    out = [x for x in xs if x and x.ok]   # +1 (and); the comprehension itself is free
    while out:                            # +1
        out.pop()
    else:                                 # +1
        pass
    return lambda y: y if y else out      # +2 ternary at nesting 1 (lambda)
''', {"process": 16, "walk": 2, "tidy": 5})

TS = ('''
interface Opts { retries?: number; onError?: (e: Error) => void }

export function toRegexp(antPattern: string, sep: string): string {
  let i = antPattern.startsWith("/") || antPattern.startsWith("\\\\") ? 1 : 0;   // +1 +1
  const out: string[] = [];
  while (i < antPattern.length) {                     // +1
    const ch = antPattern[i];
    if (SPECIAL.includes(ch)) {                       // +2
      out.push("\\\\" + ch);
    } else if (ch === "*") {                          // +1
      if (antPattern[i + 1] === "*" && isSlash(antPattern[i + 2] ?? "")) {   // +3 +1
        out.push("(?:.*" + sep + "|)");
        i += 2;
      } else {                                        // +1
        out.push(".*");
      }
    } else {                                          // +1
      out.push(ch);
    }
    i++;
  }
  return out.join("");
}

export const fetchAll = async (urls: string[], opts: Opts = {}): Promise<string[]> => {
  const results: string[] = [];
  for (const url of urls) {                                   // +1
    let attempt = 0;
    while (attempt <= (opts.retries ?? 0)) {                  // +2
      try {
        results.push(await fetch(url).then((r) => { return r.ok ? r.text() : Promise.reject(r); }));  // +4
        break;
      } catch (e) {                                           // +3
        attempt++;
        opts.onError?.(e as Error);
        if (attempt > (opts.retries ?? 0) && !opts.onError) throw e;   // +4 +1
      }
    }
  }
  return results;
};

class Repo {
  #cache = new Map<string, number>();
  async *entries(filter?: RegExp) {
    for (const [k, v] of this.#cache) {        // +1
      if (filter && !filter.test(k)) continue; // +2 +1
      yield [k, v] as const;
    }
  }
}
''', {"toRegexp": 12, "fetchAll": 15, "entries": 4})

CS = ('''
namespace Shop;

public class OrderService
{
    private readonly ILogger _log;
    public int Retries { get; set; }

    public int Count
    {
        get
        {
            if (_items == null) return 0;      // +1
            return _items.Count;
        }
    }

    public decimal Total(IEnumerable<Order> orders, Customer? customer)
    {
        decimal total = 0;
        int? bonus = customer?.Tier == Tier.Gold ? 10 : null;       // +1
        foreach (var order in orders)                                // +1
        {
            if (order is null || order.Items.Count == 0) continue;   // +2 +1
            var discount = order.Kind switch                         // +2
            {
                OrderKind.Bulk => 0.1m,
                OrderKind.Vip when customer?.Tier == Tier.Gold => 0.2m,
                _ => 0m
            };
            total += order.Items.Sum(i => i.Price * i.Qty) * (1 - discount);
            try
            {
                Validate(order);
            }
            catch (ValidationException ex) when (ex.Severity > 1)     // +2
            {
                _log.Warn(ex.Message ?? "n/a");
                if (Retries > 0 && ex.Retryable)                     // +3 +1
                {
                    total += Total(new[] { order }, customer);       // +1 recursion
                }
            }
        }
        return bonus is null ? total : total + bonus.Value;          // +1
    }

    public string Describe(Order order)
    {
        Func<Order, string> f = o =>
        {
            if (o.Items.Count > 3) return "big";                     // +2
            return o.Items.Count > 0 ? "small" : "empty";            // +2
        };
        var s = $"{order.Id}: {f(order)}";
        return s;
    }
}
''', {"Count.get": 1, "Total": 15, "Describe": 4})

GO = ('''
package main

func (s *Server) Walk(n *Node, depth int) error {
	for i := 0; i < len(n.Kids); i++ {          // +1
		if err := s.Walk(n.Kids[i], depth+1); err != nil {   // +2, +1 recursion
			return err
		}
	}
	switch n.Kind {                             // +1
	case Leaf:
		return nil
	case Branch:
		if n.Left == nil && n.Right == nil {   // +2 +1
			return errors.New("empty")
		}
	}
	return nil
}

func serve(ch chan int) {
	go func() {
		for v := range ch {                     // +2
			select {                            // +3
			case <-done:
				return
			default:
				if v > 10 || v < 0 {           // +4 +1
					continue
				}
			}
		}
	}()
outer:
	for {                                       // +1
		for _, x := range xs {                  // +2
			if x == 0 {                         // +3
				break outer                     // +1
			}
		}
	}
}
''', {"Walk": 8, "serve": 17})

RS = ('''
fn classify(x: &&str, items: &[Item]) -> u32 {
    let mut n = 0;
    'outer: loop {                                     // +1
        for item in items {                            // +2
            match item.kind {                          // +3
                Kind::A if item.weight > 10 => {       // (match guard: free)
                    n += 1;
                }
                Kind::B | Kind::C => break 'outer,     // +1
                _ => {}
            }
        }
        let Some(v) = item.value() else { return n };  // (let-else: free)
        if v > 0 && !x.is_empty() {                    // +2 +1
            n += v;
        } else {                                       // +1
            n = items.iter().map(|i| { if i.ok { 1 } else { 0 } }).sum();  // closure: +4 +1
        }
    }
    n
}

impl Default for Item {
    fn default() -> Self { Item { kind: Kind::A, weight: 0 } }
}

fn apply<F>(f: F) -> u32 where F: for<'a> Fn(&'a str) -> u32 {
    f("x")
}
''', {"classify": 16, "default": 0, "apply": 0})

KT = ('''
class Parser(val strict: Boolean) {
    fun parse(input: String?, depth: Int = 0): Node? {
        val text = input ?: return null
        val kind = when {                                  // +1
            text.startsWith("{") -> Kind.Obj
            text.startsWith("[") -> Kind.Arr
            else -> Kind.Scalar
        }
        return if (kind == Kind.Scalar) scalar(text) else {   // +1 +1
            val parts = split(text)
            for (p in parts) {                             // +3
                if (p.isBlank() && strict) throw Err()     // +4 +1
            }
            parse(parts.first(), depth + 1)                // +1 recursion
        }
    }

    fun kind(x: Int) = when {                              // +1
        x < 0 -> if (strict) Kind.Err else Kind.Neg        // +2 +1
        else -> Kind.Pos
    }

    fun sign(x: Int) = if (x > 0) 1 else -1                // +1 +1

    fun label(x: Int): String {
        val base = x
            .toString()
        return base
    }
}
''', {"parse": 12, "kind": 4, "sign": 2, "label": 0})

SWIFT = ('''
struct Loader {
    func load(_ path: String?) throws -> Data? {
        guard let p = path, !p.isEmpty else { return nil }   // +1
        var out: Data? = nil
        do {
            out = try? read(p)
        } catch {                                             // +1
            if let e = error as? IOError {                    // +2
                log(e.code > 0 ? "warn" : "info")             // +3
            }
        }
        repeat {                                              // +1
            out = out ?? Data()
        } while out == nil                                    // (do-while: free)
        return out
    }

    private var cached: String?
    private var expires: Date = .distantPast
    var label: String { cached != nil ? "hit" : "miss" }     // +1
}
''', {"load": 8, "<top-level>": 1})

PHP = ('''<?php
class Tree {
    public function size($node, $acc = 0) {
        # count
        if ($node === null) {                 // +1
            return $acc;
        } elseif (!is_array($node)) {         // +1
            return $acc + 1;
        }
        foreach ($node as $k => $child) {     // +1
            if ($k === 'skip' or $k === 'x') { // +2 +1
                continue 2;                   // +1
            }
            $acc = $this->size($child, $acc); // +1 recursion
        }
        return $acc > 0 ? $acc : 1;           // +1
    }
}
''', {"size": 9})

C = (r'''
#include <stdio.h>
#define CHECK(x) \
    if (!(x)) { return -1; }

static int scan(const char *s, int n) {
    int i = 0, bad = 0;
    do {                                    /* +1 */
        if (s[i] == '\\' || s[i] == '"') {  /* +2 +1 */
            bad++;
        } else if (s[i] == 0) goto done;    /* +1 +1 */
        i++;
    } while (i < n);
done:
    switch (bad) {                          /* +1 */
        case 0: return 0;
        default: return bad > 3 ? -1 : bad; /* +2 (nested in the switch) */
    }
}
''', {"scan": 9})

CPP = ('''
template <typename T>
int count_if_ok(const std::vector<T>& xs) {
    auto ok = [&](const T& x) {              // closure: nesting 1
        if constexpr (std::is_integral_v<T>) {   // +2
            return x > 0 && x < 100;         // +1
        } else {                             // +1
            return !x.empty();
        }
    };
    int n = 0;
    for (const auto& x : xs) if (ok(x)) n++; // +1 +2
    return n;
}
''', {"count_if_ok": 7})

JS_ASI = ('''
export default function f(a, b) {
  if (a) return 1
  for (const x of b) {       // +1 (not nested under the braceless if)
    if (x) continue          // +2
  }
  const re = /[{(]\\//g
  return a ? 1 : 2           // +1
}

app.get('/', async (req, res) => {
  if (req.query.q) res.send(await find({ q: req.query.q }))   // +1
})

const pick = (a, b) => {
  const v = a
    ? a.value
    : b
  if (v)
    return v
  return null                // +1 +1 (the braceless if ends at this line)
}

export function List({ items, user }) {
  if (!items.length) return <p>Nothing here, don't wait</p>   // +1
  return (
    <ul className="list">
      {items.map((it) => (
        <li key={it.id}>{it.ok && user ? it.name : <em>n/a</em>}</li>   // +1 &&, ternary +2 (nesting 1: arrow)
      ))}
    </ul>
  )
}
''', {"f": 5, "<callback in get>": 1, "pick": 2, "List": 4})

JAVA_BRACELESS = ('''
class A {
  int g(int a, int[] xs) {
    if (a > 0) return a > 5 ? 1 : 2;     // +1 +2
    if (a < 0) for (int x : xs) a += x;  // +1 +2
    return a;
  }
}
''', {"g": 6})


class Scores(unittest.TestCase):
    def check(self, lang, fixture):
        src, expected = fixture
        got = {fn.name: fn.score for fn in score_source(src, lang)}
        for name, want in expected.items():
            self.assertEqual(got.get(name), want, f"{lang} {name}: expected {want}, got {got}")

    def test_paper_java(self): self.check("java", PAPER_JAVA)
    def test_paper_js(self): self.check("js", PAPER_JS)
    def test_paper_py(self): self.check("py", PAPER_PY)
    def test_python(self): self.check("py", PY)
    def test_typescript(self): self.check("ts", TS)
    def test_csharp(self): self.check("cs", CS)
    def test_go(self): self.check("go", GO)
    def test_rust(self): self.check("rs", RS)
    def test_kotlin(self): self.check("kt", KT)
    def test_swift(self): self.check("swift", SWIFT)
    def test_php(self): self.check("php", PHP)
    def test_c(self): self.check("c", C)
    def test_cpp(self): self.check("cpp", CPP)
    def test_js_asi(self): self.check("js", JS_ASI)
    def test_java_braceless(self): self.check("java", JAVA_BRACELESS)

    def test_csharp_sonar_dotnet(self):
        # sonar-dotnet (CSharpCognitiveComplexityMetric.cs) differs from the paper: pattern and/or count,
        # goto gets a nesting increment, a static local function is scored on its own.
        src = r'''class P {
  int Pat(object o, string s) {
    if (s is not { Length: > 0 and <= 254 } raw || o is int or long) return 1;
    return 0;
  }
  int Sw(int x) {
    if (x > 0) {
      return x switch { 1 => 1, _ => 2 };
    }
    return 0;
  }
  void Go(int x) {
    while (x > 0) {
      if (x == 3) goto done;
      x--;
    }
    done: ;
  }
  int Locals(int x) {
    int Inner(int y) { if (y > 0) return 1; return 0; }
    static int Stat(int y) { if (y > 0) return 1; return 0; }
    return Inner(x) + Stat(x);
  }
}
'''
        self.assertEqual({f.name: f.score for f in score_source(src, "cs")},
                         {"Pat": 4, "Sw": 3, "Go": 6, "Locals": 2, "Stat": 1})

    def test_csharp_expression_bodied(self):
        src = "class C {\n  static int Twice(int x) =>\n    x > 0 ? x * 2 : 0;\n  int P => a && b ? 1 : 0;\n  int Q { get => 1; }\n}\n"
        self.assertEqual({f.name: f.score for f in score_source(src, "cs")}, {"Twice": 1, "P": 2, "Q.get": 0})

    def test_py_else_line(self):
        src = "def f(a):\n    if a:\n        x = 1\n    # note\n    else:\n        x = 2\n    return x\n"
        self.assertIn((5, 1, "else"), score_source(src, "py")[0].incs)


if __name__ == "__main__":
    unittest.main()
