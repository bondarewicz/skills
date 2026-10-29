# Cognitive Complexity: the rules

Source: G. Ann Campbell, *Cognitive Complexity: a new way of measuring understandability*,
SonarSource, v1.7 (29 Aug 2023), https://www.sonarsource.com/docs/CognitiveComplexity.pdf.
This file is the specification condensed; the score is identical to SonarQube rule S3776.

## Three principles

1. **Ignore shorthand.** Structures that let several statements read as one cost nothing:
   the method itself, lambdas, null-coalescing (`?.`, `??`, `?:`).
2. **+1 for each break in the linear flow** of the code (top to bottom, left to right).
3. **+1 per level of nesting** for the flow-breaking structures that are nested.

Cyclomatic complexity gives `sumOfPrimes` and `getWords` the same score (4). Cognitive
complexity gives 7 and 1, matching how hard they are to read.

## Four kinds of increment

| Kind | What | Example |
|---|---|---|
| Structural | +1, plus the nesting level, and nests what is inside | `if`, `for`, `while`, `switch`, `catch`, ternary |
| Hybrid | +1, nests what is inside, but no nesting penalty for itself (the `if` already paid) | `else if`, `elif`, `else` |
| Fundamental | +1, no nesting penalty, nests nothing | boolean operator sequences, `goto`, labeled `break`/`continue`, recursion |
| Nesting only | no increment, but what is inside is one level deeper | lambdas, nested functions, anonymous classes |

## Appendix B, the specification

**B1. +1 for each of:** `if`, `else if`, `else`, ternary; `switch`; `for`, `foreach`; `while`,
`do while`; `catch`; `goto LABEL`, `break LABEL`, `continue LABEL`, `break NUMBER`,
`continue NUMBER`; each sequence of binary logical operators; each method in a recursion cycle.

**B2. Nesting level +1 inside:** `if`, `else if`, `else`, ternary; `switch`; `for`, `foreach`;
`while`, `do while`; `catch`; nested methods and method-like structures such as lambdas.

**B3. Nesting increment (+ current nesting level) for:** `if`, ternary; `switch`; `for`,
`foreach`; `while`, `do while`; `catch`.

## Details that decide most arguments

- **`switch` is +1 total**, however many `case`s. An `if / else if` chain is +1 per branch.
  A `switch` compares one value against literals; a chain can compare anything.
- **`catch` is +1** whatever it catches (`catch (A | B e)` is still 1). `try` and `finally` are free.
- **Boolean operators count per sequence of the same operator**, not per operator:
  `a && b && c` = 1, `a && b || c` = 2, `a && b && c || d || e && f` = 3, `a && !(b && c)` = 2.
  This applies everywhere, including assignments and return statements, not only in `if`.
- **Recursion is +1** for every method in the cycle, direct or indirect. It is a loop in disguise.
- **Jumps:** `goto`, `break label`, `continue label` are +1. Plain `break`, `continue`, early
  `return`, `throw` are free. Early returns often *reduce* the score by removing nesting.
- **Method structure is free**, so a class full of simple getters scores 0 and aggregate
  scores per class or file mean something.
- **Lambdas and nested functions** are free but what they contain is one level deeper.
  Their contents count toward the enclosing method.
- **Null-coalescing** (`a?.b`, `a ?? b`, Kotlin `?:`) is free.
- **Preprocessor conditionals** (`#if`, `#ifdef`) count like `if` and nest what they wrap.

## C# as sonar-dotnet scores it

sonar-dotnet's walker (`CSharpCognitiveComplexityMetric.cs`) departs from the paper in three places.
The scorer follows sonar-dotnet:

- Pattern combinators count like `&&`/`||`: `x is A or B` is +1 per run of `and` or of `or`.
- `goto` (and `goto case`) is +1 plus nesting, not a flat +1.
- A `static` local function is scored on its own. A non-static one counts toward its parent, one level deeper.
- A `switch` expression counts like a `switch` statement. Endpoint lambdas (`app.MapGet(..., async () => {...})`)
  count toward the method that registers them.

## Appendix A, language compensations

- **COBOL** has no `else if`: an `IF` as the only statement of an `ELSE` is not nested and the
  `ELSE` itself is free.
- **JavaScript** module pattern: an outer function that contains only declarations is ignored;
  the functions it declares start at nesting 0. An outer function with its own control flow is
  scored normally.
- **Python decorators**: a function whose body is only a nested function and a `return` does not
  nest the inner function.

## Worked examples from the paper (also the scorer's test fixtures)

```java
int sumOfPrimes(int max) {
  int total = 0;
  OUT: for (int i = 1; i <= max; ++i) {   // +1
    for (int j = 2; j < i; ++j) {         // +2 (nesting 1)
      if (i % j == 0) {                   // +3 (nesting 2)
        continue OUT;                     // +1
      }
    }
    total += i;
  }
  return total;                           // = 7
}

String getWords(int number) {
  switch (number) {                       // +1
    case 1:  return "one";
    case 2:  return "a couple";
    default: return "lots";
  }                                       // = 1
}

void myMethod() {
  try {                                   // free
    if (condition1) {                     // +1
      for (int i = 0; i < 10; i++) {      // +2 (nesting 1)
        while (condition2) { … }          // +3 (nesting 2)
      }
    }
  } catch (ExcepType1 | ExcepType2 e) {   // +1
    if (condition2) { … }                 // +2 (nesting 1)
  }                                       // = 9
}

void myMethod2() {
  Runnable r = () -> {                    // free, nesting is now 1
    if (condition1) { … }                 // +2 (nesting 1)
  };                                      // = 2
}
```

Larger examples with the paper's scores: `overriddenSymbolFrom` = 19, `addVersion` = 35,
`toRegexp` = 20, YUI `save` = 20. They are in `scripts/test_cogc.py`; run the scorer with
`--explain` on them to see every increment.

```python
def a_decorator(a, b):
  def inner(func):          # nesting 0: decorator idiom
    if condition:           # +1
      print(b)
    func()
  return inner              # = 1

def not_a_decorator(a, b):
  my_var = a*b
  def inner(func):          # nesting 1
    if condition:           # +2
      print(b)
    func()
  return inner              # = 2
```

## Thresholds

SonarQube flags a function above **15**. Sonar reports class and file totals too; those have no
fixed threshold, use them to compare units of the same kind.
