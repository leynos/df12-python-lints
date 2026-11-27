# RFC 0006: Branch factoring

## Preamble

- **RFC number:** 0006
- **Status:** Proposed
- **Created:** 2026-11-14

## Summary

Propose conservative diagnostics for common statements and stable conditions
spread across neighbouring branches. The useful gap includes a common suffix
after different calculations, a prefix that can safely precede a condition, and
repeated guards whose value cannot change between tests. These operations
require different evidence and must remain independently selectable.

The [shared refactoring lint contract](../refactoring-lint-contract.md) governs
activation, confidence, uncertainty, suppression, and reporting. The first
implementation supplies advice without automatic fixes. This proposal draws
semantic inspiration from Sourcery's branch refactorings; it copies no
implementation code or examples.[^1]

## Problem

Duplicated statements can obscure the part of a decision that actually varies.
A common final operation belongs after an exhaustive conditional when every
normally completing branch performs it. Repeated conditions can likewise hide a
shared prerequisite.

Textual resemblance does not establish a safe transformation. Moving a prefix
before a test changes evaluation order. Testing a property once instead of
twice can change behaviour, even without an assignment to its receiver.
Extracting an early guard from a later branch can skip an earlier exception or
side effect. The checker must distinguish these cases rather than describe all
branch factoring as duplicate removal.

## Current state

Ruff `SIM114` combines entirely identical branch bodies; `SIM102` combines
nested conditionals. Ruff's `RET505`–`RET508` and Pylint's corresponding
`no-else-*` messages handle branches following terminal statements.[^2] These
rules retain ownership of their supported shapes. RFC 0004 covers simple
empty-branch and identical-handler cleanup.

The package already has dispatch-oriented checkers and `_chains.py` traversal
helpers. `elif_chain_tests` and `is_elif_branch` can identify chain structure;
they do not prove equivalent execution paths. `_expressions.attribute_root`
recognizes a syntactic attribute chain, not a side-effect-free access. The
package has no general branch liveness or effect analysis.[^3]

## Goals and non-goals

The goal is to remove a demonstrably redundant branch distinction while
preserving evaluation, binding, exception, and control-flow behaviour. The
initial analysis covers ordinary synchronous function bodies and bounded
`if`/`elif`/`else` regions in one lexical scope.

General Boolean theorem proving, moving context managers, extracting helper
functions, restructuring `match` statements, and changing exception handlers
are outside this proposal. A duplicate-code threshold alone cannot justify a
diagnostic. Entirely identical arms remain upstream territory.

## Proposed design

### Candidate families and ownership

Use provisional symbolic names, with numeric allocation deferred until
implementation:

| Candidate                          | Evidence required                                         | Initial disposition    |
| ---------------------------------- | --------------------------------------------------------- | ---------------------- |
| `factor-common-branch-suffix`      | Exhaustive paths and equivalent trailing statements       | Implement first        |
| `factor-common-branch-prefix`      | Suffix evidence plus safe movement before tests           | Narrow supported forms |
| `merge-stable-guard-blocks`        | Adjacent branches with the same stable test               | Narrow supported forms |
| `factor-repeated-branch-condition` | Shared prerequisite with preserved short-circuit order    | Defer broader forms    |
| `prefer-terminal-guard`            | A final conditional with a provably equivalent early exit | Narrow supported forms |

_Table 1: Branch-factoring candidates and their independent proof obligations._

### Common suffixes

For a proposed suffix extraction, the checker must establish an explicit,
exhaustive conditional: every leaf path has a final `else`, and every normally
completing path ends in the same non-empty statement sequence. Compare abstract
syntax tree structure and resolved lexical bindings, excluding source
locations. Do not equate expressions merely because their rendered text
matches. Branch- specific reaching values may differ: after extraction, each
path must still supply the binding value that its original suffix would have
read.

The following example illustrates a common suffix after different calculations:

```python
def invoice_label(units, discounted):
    if discounted:
        total = units * 8
        label = f"Amount due: {total}"
    else:
        total = units * 10
        label = f"Amount due: {total}"
    return label
```

The proposed result keeps the condition and selected calculation in place:

```python
def invoice_label(units, discounted):
    if discounted:
        total = units * 8
    else:
        total = units * 10
    label = f"Amount due: {total}"
    return label
```

The formatting operation may invoke user code. This extraction does not need to
prove formatting pure: it executes once, after the same calculation and within
the same surrounding exception and cleanup regions. The proof concerns its
execution position, not a blanket purity classification.

Initially accept straight-line suffixes made from ordinary local assignments
and expression statements. Reject annotated assignments, definitions, imports,
declarations, suspension, and compound statements. Reject candidates containing
or crossing a `return`, `raise`, `break`, or `continue`; this restriction
avoids requiring a general control-flow graph in the first implementation. A
missing `else` is not an implicit empty branch that permits extraction.

Require meaningful statements to remain in each arm. If extraction would empty
all arms, delegate the existing identical-arm diagnostic. Comments or local
suppression boundaries that would lose their attachment suppress the candidate.

### Common prefixes

Prefix extraction moves work from after branch selection to before it. In
addition to structural equivalence, prove that the prefix and every crossed
test commute: neither changes the other's inputs, neither can raise an ordinary
exception, and neither performs an observable effect. All referenced names must
be definitely bound before the new location.

The first supported tests should be exact Boolean values or identity tests on
definitely bound, uncaptured local names. Supported prefixes should be literal
assignments to fresh locals with no overlapping dependency. An annotation or
Astroid class inference alone cannot prove an exact builtin or its behaviour.

Hold advice for property access, arbitrary calls, overloaded comparisons,
mutable allocations whose identity escapes, or movement across `with`, `try`,
`await`, or `yield`. In particular, combining matching `with` statements around
a conditional changes context-entry timing and is outside version one.

### Repeated tests and guard extraction

`merge-stable-guard-blocks` may combine adjacent `if` statements, including
matching `else` arms, only when their tests have the same lexical dependencies
and a stable, effect-free Boolean result. Preserve the order of the original
bodies inside each resulting arm. Any write, deletion, capture, unknown
mutation, or suspension that can invalidate the test makes the result unknown.

The checker must not infer stability from a repeated spelling. The following
code must remain silent because the first body changes the second decision:

```python
def adjust_state(setting):
    enabled = setting is not None
    if enabled:
        enabled = False
    if enabled:
        return "still enabled"
    return "disabled"
```

Factoring a shared conjunct from neighbouring tests additionally requires that
the conjunct already appears first on every evaluated path. Keep all remaining
tests in their original order. Do not move a conjunct past another test to make
the pattern fit, and do not change independent `if` statements into `elif`.
Unknown truth methods, descriptors, and user-defined comparison operations
exclude the candidate. Broader distributed-condition factoring remains deferred.

`prefer-terminal-guard` may invert a final function-body conditional and add a
bare `return` only when its false path already reaches that function's implicit
`None` return. Preserve one truth test, and reject generators and changes to
cleanup boundaries. Moving a later guard earlier requires the same commutation
proof as prefix extraction; an empty middle branch alone is insufficient. Cases
already recognized by upstream terminal-branch rules receive no df12 diagnostic.

### Analysis and diagnostic selection

Build bounded branch summaries once per function. A proposed summary records
leaf coverage, statement fingerprints, binding reads and writes, abrupt exits,
and protected-region boundaries. These are proposed helpers, not existing
package capabilities. Reuse `_chains.py` for traversal without weakening its
current clients' contracts.

Choose one non-overlapping candidate per region. Prefer an eligible maximal
suffix, then an eligible prefix, then repeated-test factoring, using source
order to break ties. Report on the first duplicated statement or repeated test
and identify the destination in the message. Re-running after a manual change
may reveal another candidate; one run must not suggest incompatible rewrites.

## Requirements and acceptance

Each candidate must have independent positive and negative tests. Acceptance
requires tests for exhaustive and missing-else paths, nested lexical scopes,
different bindings with identical spelling, property accesses, short-circuit
conditions, writes through aliases, captured variables, ordinary exceptions,
abrupt exits, suppression comments, and cleanup or suspension boundaries.

For the suffix family, compare original and test-only transformed examples that
record calls and deliberately raise in selected branch operations. Returned
values, call order, exception type, and visible mutations must agree. Prefix
and repeated-test tests must independently demonstrate why mutation or throwing
tests prevent a report. Include unknown callbacks in preserved-position suffix
tests so an unnecessary purity restriction cannot silently erase that coverage.

Property tests should cover alpha-renaming, diagnostic uniqueness, and
monotonic conservatism: replacing known facts with unknown facts cannot create
advice. Integration tests must follow the shared contract, including
only-this-message activation and serial versus parallel diagnostic identity.
Bound analysis by syntax size and documented per-scope budgets; budget
exhaustion means silence.

## Compatibility and migration

This RFC changes no checker registration or configuration. After acceptance,
introduce the suffix family first and pilot it independently. Enable other
families only when their safety matrices and representative corpus reviews
justify them. No new runtime dependency or Python baseline increase is required.

Update the user guide with precise exclusions and the developer guide with any
accepted summary abstraction. Keep numeric message allocation and default
enablement separate from this proposal. Existing local suppression conventions
continue to apply.

## Alternatives considered

Delegating all duplication to `df12-duplication` avoids another checker but
does not identify a safe statement destination. Textual common-prefix
extraction is small to implement but cannot establish evaluation-order safety.
A general control-flow optimizer would widen scope and verification cost
substantially. The proposed bounded families retain a reviewable relationship
between evidence and advice.

## Open questions

- Does a suffix of one simple assignment produce enough useful findings to
  justify a diagnostic, or should corpus review establish a higher threshold?
- Should terminal guards remain a separate message after the pilot, given their
  greater style sensitivity?
- Which repeated-condition forms add practical value beyond upstream rules
  without requiring general effect inference?

## Recommendation

Implement exhaustive common-suffix factoring first. Retain separate, stricter
contracts for prefixes, guards, and repeated conditions, and defer any family
whose evidence cannot support a precise recommendation.

[^1]: Sourcery's
      [hoist statements from if](https://docs.sourcery.ai/reference/refactorings/python/hoist-statement-from-if/),
    [hoist similar statements](https://docs.sourcery.ai/reference/refactorings/python/hoist-similar-statement-from-if/),
    [merge repeated ifs](https://docs.sourcery.ai/reference/refactorings/python/merge-repeated-ifs/),
    and [guard](https://docs.sourcery.ai/reference/refactorings/python/guard/).
[^2]: Ruff's [SIM114](https://docs.astral.sh/ruff/rules/if-with-same-arms/),
    [SIM102](https://docs.astral.sh/ruff/rules/collapsible-if/), and
    [RET505](https://docs.astral.sh/ruff/rules/superfluous-else-return/);
    Pylint's [R1705](https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/no-else-return.html).
[^3]: The [developer guide](../developers-guide.md) documents the implemented
    checker and helper boundaries; the package's
    [chain helpers](../../df12_python_lints/_chains.py) and
    [expression helpers](../../df12_python_lints/_expressions.py) define their
    existing contracts.
