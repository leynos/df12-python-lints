# RFC 0010: Numeric and logical transformations

## Preamble

- **RFC number:** 0010
- **Status:** Proposed
- **Created:** 2026-11-14

## Summary

Propose four optional diagnostics for Boolean quantifier duality, integer
reductions, paired quotient and remainder calculations, and integer comparison
algebra. Each diagnostic requires a specific proof of its operand semantics.
Python 3.12 remains the minimum supported language version.

The [shared refactoring contract](../refactoring-lint-contract.md) governs
registration, suppression, bounded analysis, and diagnostic-only delivery.
[RFC 0011](rfc-0011-de-morgan-transformations.md) owns transformations of outer
Boolean expressions. This RFC owns `any()` and `all()` transformations. An
outer normalization retains admitted Boolean leaves unchanged. Independent
nested candidates may both report when a quantifier occurs inside such a leaf,
for example `bool(any(...))`.

## Problem

Mathematical identities do not establish equivalent Python behaviour.
Arithmetic methods can differ, Boolean operators can return operands, and
comparisons need not define a total order.[^1] Replacing an accumulation loop
with `sum()` also requires a numeric contract: Python 3.12 changed floating
point summation, so the replacement can change the answer.[^2]

Sourcery's catalogue identifies useful opportunities through its
`invert-any-all`, `invert-any-all-body`, `sum-comprehension`,
`simplify-division`, and `simplify-numeric-comparison` entries.[^3] These
entries provide inspiration and examples of intent. This proposal neither
copies their implementation nor treats every documented replacement as valid.

## Current state

The package provides Pylint checkers using Astroid and supports
`pylint>=3.3,<5`. Existing expression helpers classify syntax and bindings;
they do not prove exact numeric types. Ruff's `SIM110` already recognizes loops
implementing `any()` or `all()`.[^4] That coverage does not establish
quantifier duality or numeric equivalence.

## Proposed design

### Diagnostic families

Table 1 names proposed symbols. Numeric message identifiers remain unallocated.

| Proposed symbol               | Candidate                                     | Suggested direction                             |
| ----------------------------- | --------------------------------------------- | ----------------------------------------------- |
| `prefer-any-all-duality`      | Negated generator body passed to a quantifier | Move body negation outside and swap `any`/`all` |
| `prefer-integer-sum`          | Exact integer accumulation loop               | Express the reduction with `sum`                |
| `prefer-integer-divmod`       | Adjacent quotient and remainder assignments   | Compute both results with `divmod`              |
| `simplify-integer-comparison` | Integer offset against an integer literal     | Move the offset into the literal bound          |

*Table 1: Proposed diagnostic families and their normalization directions.*

### Proof vocabulary

An **integer fact** requires an exact built-in `int`, excluding `bool` and
subclasses. Version one may derive facts from integer literals, unary signs,
and unambiguous dominating local assignments to those expressions or unshadowed
built-in `len()` calls. The calls remain at their original locations. A name
must remain bound and unchanged throughout the candidate. Annotations,
`isinstance()`, and an inferred class name do not suffice. Constructor-based
facts and runtime type guards remain deferred.

A **Boolean fact** follows RFC 0011's exact-Boolean grammar. Unknown inference,
multiple reaching definitions, unsupported effects, or exceeded analysis
budgets suppress the diagnostic. An inference result must corroborate the
approved syntax; Astroid's inference iterator alone does not establish a
runtime type guarantee.[^5]

Preserve input identities and alias relationships. Newly computed integer
identity depends on allocation and interning decisions outside this numeric
contract.[^1] Suppress reductions and paired division when their results have
visible identity-sensitive consumers such as `is` or `id()`.

### Quantifier duality

Match one synchronous generator argument whose body is `not P`, where `P` has a
Boolean fact. Keep its iterator, target, filters, evaluation order, and
generator boundary unchanged. Require unshadowed built-in quantifiers, and
reject assignment expressions, suspension, and additional call arguments.

Normalize `any(not P for ...)` to `not all(P for ...)`, and normalize
`all(not P for ...)` to `not any(P for ...)`. If an immediate outer `not`
already exists, cancel the resulting double negation. Never perform the reverse
transformation. Negation means `not P`; it does not mean replacing `<` with
`>=` or `==` with `!=`.

This example preserves the existing generator and each identity test:

```python
has_missing = any(not (record is not None) for record in records)

# Suggested expression.
has_missing = not all(record is not None for record in records)
```

Do not remove the generator. Moving an arbitrary object's truth test out of its
generator can change `RuntimeError` into `StopIteration` under PEP 479.[^6]
Requiring an exact Boolean result makes the moved conversion inert. In
particular, `any(not item for item in items)` with unknown items must remain
unreported. Sourcery's published `invert-any-all-body` example omits the
necessary outer negation; it is not an acceptance oracle.

### Integer reductions

Match adjacent `total = 0` and `for item in values: total += item` statements
in a function. Version one accepts only an unchanged local `values` bound
earlier to an unshadowed `range()` result or a tuple literal of exact integer
literals. Construction therefore completes before the candidate begins. Require
fresh, distinct, ordinary local targets, and prove that `item` has no
subsequent read, closure capture, or other observable binding use. Reject
additional loop statements, `else`, control transfers, mutation, and scope
introspection.

Suggest `total = sum(values)` with unshadowed `sum`. This establishes exact
integer addition and exhaustion of a built-in iterator without introducing a
generator. Generic iterables, arbitrary element expressions, nonzero
initializers, subclasses, and floating point values remain outside version one.
No runtime speed claim forms part of the diagnostic.

### Division and comparison algebra

For `prefer-integer-divmod`, require adjacent assignments `q = n // d` and
`r = n % d` with identical operands, integer facts, and a provably nonzero
divisor. Operands must be literals or stable local names. Targets must be
distinct ordinary local names, absent from both operands, with no closure
capture. Suggest `q, r = divmod(n, d)` only when `divmod` resolves to the
built-in function. Its documented integer result matches the two
operations.[^7] Separate custom `__floordiv__`, `__mod__`, and `__divmod__`
methods do not establish that relationship.[^8]

For `simplify-integer-comparison`, match `(n + k) OP m` or `(n - k) OP m`, where
`n` is a stable local integer, `k` and `m` are integer literals, and `OP` is
one comparison from `<`, `<=`, `==`, `!=`, `>=`, or `>`. Suggest `n OP (m - k)`
or `n OP (m + k)`, respectively, with the new literal computed by bounded
analysis. Reject chained comparisons, literal-only comparisons, and all other
arithmetic shapes.

For example, after `size = len(payload)`, `size + 1 < 10` may become
`size < 9`. A parameter merely annotated `size: int` does not qualify.

## Requirements and acceptance tests

Implement recognizers using Astroid nodes and scope-aware name lookup. Keep
proof records local to one analysis run, and never execute linted code. Report
on the quantifier call, loop, first division assignment, or comparison,
respectively. Each message must identify the suggested operation and the proven
domain. Apply the shared suppression and overlap policy.

Acceptance requires the following independent semantic tests:

- Positive fixtures for all four families, including empty reductions, both
  quantifiers, both outer-negation cases, signed division, and all six
  comparison operators. Assert exact message positions and symbols.
- Negative fixtures for shadowed built-ins, ambiguous assignments, annotated
  parameters, integer subclasses, live or previously bound loop targets,
  floating point values, zero or unknown divisors, and targets reused as
  division operands.
- A truth method raising `StopIteration` must demonstrate the generator
  boundary counterexample and suppress quantifier duality. Stateful truth
  methods must remain excluded unless an unchanged Boolean-producing leaf
  performs the conversion inside the generator.
- Property tests must compare values, exact types, consumed iterator prefixes,
  callback traces, and raised exceptions for the admitted grammar. Generate
  arbitrary signed integers, nonzero divisors, Boolean streams, and empty
  tuples. Check quotient/remainder reconstruction and comparison equivalence.
- Quantifier tests must also compare generator cleanup and object-release
  traces on exhaustion, short-circuit exits, and exceptions. Include `finally`
  logging in input generators and explicit close/release behaviour; retaining a
  generator syntactically does not itself prove equivalent lifetime effects.
- Regression examples must reject `int(-3 / 2)` becoming `-3 // 2`, and
  `int((2**53 + 1) / 1)` becoming `(2**53 + 1) // 1`. They differ through
  rounding direction and floating point precision, respectively.

Document examples must execute on Python 3.12. The implementation must also
pass the repository's supported interpreter and Pylint compatibility suites.

## Compatibility and migration

Keep every family independently opt-in and provide no automatic fix in version
one. Existing configuration and diagnostic identifiers remain unchanged.
Respect Pylint's configured Python baseline and suppress these families below
3.12. Human review must still assess whether the suggested expression improves
the surrounding explanation.

## Alternatives considered

Generic algebraic simplification would cover more code but cannot establish
Python's operator contracts. Assuming that type annotations enforce exact types
would produce false positives. Blanket loop-to-`sum()` conversion would ignore
floating point accuracy and partial updates after exceptions.

Defer `x / x`, `x - x`, squaring, comparison inversion, and `int(a / b)`
replacement. Zero, NaN, result types, precision, and overloaded methods require
different proofs. Exclude `sum(predicate(...))` to `.count()` rewrites because
equality, identity shortcuts, and custom methods complicate their semantics
without a clear additional benefit.

## Open questions

Reviewers must decide whether the intentionally narrow integer reduction
grammar finds enough useful cases to justify shipping it. Expansion to
additional immutable containers needs separate evidence and acceptance tests.
Numeric message allocation remains an implementation decision.

## Recommendation

Accept the four families as separate proposals under the shared conservative
contract. Deliver quantifier duality and integer comparison algebra first;
retain the stricter proofs for reductions and paired division. Require an
explicit RFC amendment before expanding into general arithmetic identities.

[^1]: Python 3.12,
      [expressions](https://docs.python.org/3.12/reference/expressions.html).
[^2]: Python 3.12,
      [`sum()`](https://docs.python.org/3.12/library/functions.html#sum).
[^3]: Sourcery,
      [invert any/all](https://docs.sourcery.ai/reference/refactorings/python/invert-any-all/),
    [invert any/all body](https://docs.sourcery.ai/reference/refactorings/python/invert-any-all-body/),
    [sum comprehension](https://docs.sourcery.ai/reference/refactorings/python/sum-comprehension/),
    [simplify division](https://docs.sourcery.ai/reference/refactorings/python/simplify-division/),
    and [simplify numeric comparison](https://docs.sourcery.ai/reference/refactorings/python/simplify-numeric-comparison/).
[^4]: Ruff,
      [`reimplemented-builtin` (`SIM110`)](https://docs.astral.sh/ruff/rules/reimplemented-builtin/).
[^5]: Astroid,
      [inference](https://pylint.pycqa.org/projects/astroid/en/stable/inference.html).
[^6]: [PEP 479: Change StopIteration handling inside generators](https://peps.python.org/pep-0479/).
[^7]: Python 3.12,
      [`divmod()`](https://docs.python.org/3.12/library/functions.html#divmod).
[^8]: Python 3.12,
      [emulating numeric types](https://docs.python.org/3.12/reference/datamodel.html#emulating-numeric-types).
