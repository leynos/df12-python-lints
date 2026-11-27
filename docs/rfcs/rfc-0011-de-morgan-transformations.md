# RFC 0011: De Morgan transformations

## Preamble

- **RFC number:** 0011
- **Status:** Proposed
- **Created:** 2026-11-14

## Summary

Propose `prefer-de-morgan-normalization`, an optional diagnostic for Boolean
expressions whose explicit negations can be reduced without changing operand
evaluation. Require exact Boolean results at the leaves and preserve the order
and number of evaluations. Version one reports a reviewable suggestion and
supplies no automatic fix.

The [shared refactoring contract](../refactoring-lint-contract.md) governs
configuration, suppression, analysis budgets, and compatibility.
[RFC 0010](rfc-0010-numeric-and-logical-transformations.md) owns quantifier
duality and numeric algebra. This RFC owns outer `not`, `and`, and `or`
normalization only. Its outer replacements retain admitted Boolean leaves
unchanged. Independently eligible RFC 0010 candidates may also report inside
those leaves, for example inside `bool(any(...))`. A direct `any()` or `all()`
call is not an admitted leaf in version one.

## Problem

Nested negation can obscure a predicate's purpose. De Morgan's laws provide
equivalent Boolean formulae, but Python expressions include additional
behaviour: `and` and `or` return operands, while `not` returns a Boolean.
Objects can customize truth testing.[^1] An equivalent truth table alone does
not prove equivalent evaluation.

Sourcery's `de-morgan` entry motivates this proposal.[^2] Its examples combine
Boolean normalization with operator inversion. This RFC credits that catalogue
as inspiration and defines an independent, narrower contract; it does not copy
an implementation.

## Current state

The package uses Astroid visitors within Pylint checkers and supports Python
3.12 or later. Existing expression helpers do not prove Boolean semantics. Ruff
already covers isolated double negation with `SIM208`, and Pylint provides
`unnecessary-negation` (`C0117`).[^3] These rules do not establish a general
multi-operand normalization contract.

Ruff's comparison-negation rules also document unsafe fixes for custom equality
methods.[^4] This proposal must not treat those diagnostics as proof that
comparison operators are interchangeable.

## Proposed design

### Exact-Boolean grammar

Define a Boolean-producing leaf as one of the following expressions:

- `True` or `False`.
- A single identity or membership comparison: `is`, `is not`, `in`, or
  `not in`. Its operand expressions remain unchanged.
- A call to unshadowed built-in `bool` with exactly one positional argument
  and no keyword or starred arguments.
- A local name with one dominating assignment to an approved Boolean
  expression, no closure capture, and no write or deletion between that
  definition and the end of the candidate.

Build Boolean expressions from those leaves using `not`, `and`, and `or`. Every
expression admitted by this grammar returns an exact built-in `bool`. Names
require bound-local proof, not annotation-based inference. Exclude global and
nonlocal names as Boolean facts, ambiguous bindings, chained comparisons, and
ordinary rich comparisons. A `bool` return annotation does not establish that a
call returns a Boolean.

Leaf evaluation may have effects. For example, `bool(probe())` performs its
conversion exactly once in either expression; subsequent truth tests operate on
the Boolean result. The checker must retain that call and its position. Reject
assignment expressions, `await`, `yield`, and `yield from` anywhere inside a
candidate in version one. This limits scope-sensitive changes while leaving
ordinary predicate calls available through explicit conversion.

### Normalization direction

Generate candidates using exactly these one-step transformations, with every
`P` satisfying the Boolean grammar:

1. Push an outer `not` through one `and` or `or`, exchange the connective,
   and cancel double negations introduced at its immediate children.
2. Factor one leading `not` from every child of an `and` or `or`, exchange
   the connective, and place that negation outside the group.

Emit a diagnostic only when the candidate strictly reduces the total count of
explicit `not` nodes. Preserve operand order, grouping within untouched
children, and short-circuit order. Do not distribute conjunction over
disjunction, reorder predicates, deduplicate operands, or introduce a different
comparison operator. Ties produce no diagnostic.

For overlapping candidates, report only the outermost eligible expression. Each
suggestion must contain a De Morgan step across a connective; isolated
double-negation simplification remains with existing linters. Re-analysis must
never recommend the inverse transformation.

Reject fully constant expressions and connective operands that are literal
Booleans. Existing constant-condition and Boolean-identity diagnostics own
those simpler cases.

The following example removes three negations while preserving two explicit
conversions and their short-circuit order:

```python
allowed = not (not bool(is_owner()) and not bool(is_editor()))

# Suggested expression.
allowed = bool(is_owner()) or bool(is_editor())
```

Factoring can also improve a longer predicate without replacing its leaves:

```python
unavailable = not bool(has_primary()) and not bool(has_replica())

# Suggested expression.
unavailable = not (bool(has_primary()) or bool(has_replica()))
```

Both examples return a Boolean even in assignments and returns. A plain
`not (a and b)` produces no diagnostic: distributing it increases the number of
explicit negations and unknown operands fail the proof grammar.

### Semantic exclusions

Stateful truth methods show why unrestricted rewriting fails. With a fresh
instance for each expression, the following values differ on Python 3.12:

```python
class Toggle:
    def __init__(self):
        self.calls = 0

    def __bool__(self):
        self.calls += 1
        return self.calls > 1


left = Toggle()
original = not (left and True)  # False; two truth tests.

right = Toggle()
rewritten = not right or not True  # True; one truth test.
```

The first expression can test a returned operand again. The proposed grammar
excludes both unrestricted operands. Do not weaken it merely because a
particular interpreter optimizes an enclosing `if` test differently.

Never infer inverse comparison laws. For `nan = float("nan")`, `not (nan < 0)`
is true while `nan >= 0` is false. Python also permits custom comparison
methods whose results or ordering laws differ.[^5] Do not replace
`not (a == b)` with `a != b`, even when the result appears Boolean. Similarly,
do not remove Boolean conversion from `not not value`: a list and `True` can
have the same truth value while differing in type and identity.

## Requirements and acceptance tests

Implement a bounded Astroid recognizer over `UnaryOp`, `BoolOp`, and approved
leaves. Use scope-aware lookup to resolve built-ins and local assignments. Keep
proof records within one module analysis. Astroid can return multiple inference
results or an unknown result; neither permits an optimistic diagnostic.[^6] Do
not evaluate application code or introduce an unrestricted symbolic simplifier.

The message must identify the outer expression and proposed normalized form,
using the symbolic name `prefer-de-morgan-normalization`. Allocate its numeric
identifier during implementation. Follow the shared suppression policy and make
output deterministic across traversal order.

Acceptance requires these test groups:

- Positive fixtures for both connectives, both directions, mixed immediate
  negations that strictly reduce the count, nested groups, identity and
  membership leaves, explicit `bool` calls, and proven local Boolean names.
- Negative fixtures for equal or increased negation counts, unknown operands,
  annotations alone, integer truth values, rich and chained comparisons,
  shadowed `bool`, mutation of local bindings, and suspension or assignment
  expressions. Standalone `not not value` must not trigger this family.
- Exhaustive Boolean truth tables for small trees and property tests for
  larger trees. Compare exact values and types, leaf visitation order, call
  counts, short-circuit prefixes, and raised exceptions. Require each emitted
  candidate to reduce the metric and prevent cycles on repeated analysis.
- Effect probes whose Boolean conversion logs, changes state, or raises.
  `bool(probe())` leaves must retain one conversion at the same point. Opaque
  probes must suppress the diagnostic. Keep the `Toggle` and NaN examples as
  counterexamples to rejected broader grammars.
- Integration fixtures for assignments, returns, `if`/`while` tests, and
  nested expressions, with exact diagnostic locations and explained local
  suppressions. Check overlapping patterns yield one outermost message.

Execute examples on Python 3.12 and run the implementation against supported
Pylint versions. Tests must distinguish semantic correctness from compliance
with the stylistic negation metric.

## Compatibility and migration

The family remains opt-in under the shared contract. Existing checkers and
message identifiers remain unchanged. Suppress reporting below the configured
Python 3.12 baseline and provide no automatic fix in version one. Document that
fewer negations express a proposed style preference; a named domain predicate
may still communicate intent better.

## Alternatives considered

Unrestricted Boolean algebra ignores operand values and truth-test effects.
Limiting all reports to condition contexts would still rely on interpreter
behaviour unless the checker proves the same semantic conditions. Assuming that
comparison results are Booleans excludes neither NaN nor custom operator
semantics. Always pushing negations inward can make expressions longer and
creates disagreement with factoring rules.

The proposed strict metric gives a terminating, reviewable preference while the
proof grammar establishes its semantic boundary.

## Open questions

Reviewers must assess whether negation count predicts readability well enough
for this opt-in family. Extending the Boolean grammar to exact built-in rich
comparisons requires a separate proof and examples; it must not permit operator
inversion implicitly. Numeric message allocation remains open.

## Recommendation

Accept the narrow diagnostic family and its exact-Boolean proof grammar.
Require the semantic counterexamples and trace-based tests before enabling
implementation. Keep quantifier duality in RFC 0010 and standalone negation
rules with Ruff and Pylint.

[^1]: Python 3.12,
      [truth value testing and Boolean operations](https://docs.python.org/3.12/library/stdtypes.html#truth-value-testing).
[^2]: Sourcery,
      [apply De Morgan's laws](https://docs.sourcery.ai/reference/refactorings/python/de-morgan/).
[^3]: Ruff,
      [`double-negation` (`SIM208`)](https://docs.astral.sh/ruff/rules/double-negation/),
    and Pylint, [`unnecessary-negation` (`C0117`)](https://pylint.pycqa.org/en/stable/user_guide/messages/convention/unnecessary-negation.html).
[^4]: Ruff,
      [`negate-equal-op` (`SIM201`)](https://docs.astral.sh/ruff/rules/negate-equal-op/)
    and [`negate-not-equal-op` (`SIM202`)](https://docs.astral.sh/ruff/rules/negate-not-equal-op/).
[^5]: Python 3.12,
      [value comparisons](https://docs.python.org/3.12/reference/expressions.html#value-comparisons).
[^6]: Astroid,
      [inference](https://pylint.pycqa.org/projects/astroid/en/stable/inference.html).
