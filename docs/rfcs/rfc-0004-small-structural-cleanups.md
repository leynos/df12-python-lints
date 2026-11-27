# RFC 0004: Small structural cleanups

## Preamble

- **RFC number:** 0004
- **Status:** Proposed
- **Created:** 2026-11-14
- **Baseline:** Python 3.12 or later.
- **Audience:** Pylint checker implementers and reviewers.

## Summary

Add opt-in diagnostics for compatible nested try suites, identical ordinary
exception handlers, pass-only branches, and fresh list/set initialization.
Include literal-true assertions and directly trailing continues as small
diagnostics within the same structural family. The
[shared refactoring lint contract](../refactoring-lint-contract.md) governs
proof requirements, reporting, and verification. No first-release checker edits
source.

Sourcery's structural refactorings provide the candidate semantics and
inspiration. This RFC specifies independent, narrower eligibility rules and
includes no Sourcery implementation code.[^1]

## Problem and current state

These structures can obscure a simpler equivalent operation. Neighbouring
upstream rules do not establish complete coverage: duplicate exception-type
checks differ from identical handler bodies; redundant `pass` checks differ
from branch inversion; batching repeated appends differs from folding fresh
initialization.[^2]

The existing df12 checker `C9102` requests assertion messages. It does not
identify an assertion that always succeeds.[^3] When the proposed assertion
diagnostic actually emits for literal `True`, it takes precedence over `C9102`.
Disabling or suppressing the new message leaves existing `C9102` behaviour
unchanged.

## Goals and non-goals

Provide local recommendations whose source shape and supported semantics admit
a concise proof. Keep handler evaluation, exception bindings, cleanup,
comments, object identity, and mutation order explicit.

General branch factoring belongs to RFC 0006. Dictionary initialization already
belongs to optional Pylint `C3401`. Loop-generated collections belong to Ruff
`PERF401`, `PERF403`, and preview `FURB142`; repeated-append batching belongs
to preview `FURB113`. The first release does not reproduce those matchers or
merge `except*` handlers.[^2]

## Proposed design

### Compatible nested try suites

Propose `flatten-compatible-try` when an outer `try` has no handlers or `else`,
has a `finally`, and contains exactly one inner `try`. The inner statement must
have ordinary `except` handlers and no `finally`; it may have an `else`. Move
its body, handlers, and optional `else` into the outer suite, retaining the
outer `finally` unchanged.

This pair illustrates the accepted shape.

```python
try:
    try:
        result = perform_operation()
    except ValueError:
        result = fallback()
finally:
    release_resource()
```

Suggested form:

```python
try:
    result = perform_operation()
except ValueError:
    result = fallback()
finally:
    release_resource()
```

The transformation changes grouping, not the order of protected work. It must
preserve normal completion, returns, propagation from the body or a handler,
and cleanup that raises or overrides a pending return. Reject additional
outer-body statements, outer handlers, an inner `finally`, `except*`, or a
comment/pragma arrangement whose scope the diagnostic cannot describe
unambiguously.[^4] Anchor the outer `try` and span both suites.

### Identical ordinary exception handlers

Propose `merge-identical-except-handlers` for adjacent ordinary handlers in the
same `try`. Compare bodies structurally, preserving literal payload types and
values, names, and statement order. In particular, `True`, `1`, and `1.0` must
remain distinct despite Python value equality. Both handlers must omit `as`, or
both must use the same exception-target spelling. Do not normalize different
targets or reorder handlers in the first release.

Support only bare names resolved to stable, unshadowed built-in exception
classes, or flat tuples of such names. Concatenate their class lists into one
flat, parenthesized tuple, preserving order; a nested tuple would raise
`TypeError` during exception matching. Exclude bare catches, duplicate classes,
and superclass/subclass overlaps within or across the handlers. Those overlaps
can already be redundant or create an upstream redundancy diagnostic after
merging. Also exclude expression-valued handler types, unknown classes, and
differing suppression pragmas or explanatory comments.

Evaluating a merged tuple resolves all its class expressions even when the
first class matches. That extra evaluation makes arbitrary attribute or factory
expressions unsafe. Built-in names provide the closed initial domain. Preserve
handler precedence, the current exception object, and exception-target deletion
after the handler.[^4]

Do not merge `except*` clauses: several clauses can handle distinct parts of
one exception group, so a shared body can run more than once. This difference
requires its own design, not a flag on an ordinary-handler matcher.

### Pass-only branches

Propose `invert-empty-branch` for an `if` body containing only `pass` with a
non-empty `else`. Invert the existing condition and move the `else` body under
that condition. If the original condition already has an outer `not`, remove
that `not` instead. Leave the evaluated operand unchanged.

Also support a pass-only final `elif` followed by a non-empty `else`. Preserve
all earlier branches and invert only that final `elif` condition. Do not
replace a pass-only intermediate branch whose remaining alternatives have
different selection semantics.

Require one original condition evaluation and one truth test at the same
control-flow position. Do not push negation inside comparisons or Boolean
expressions; RFC 0011 owns that separate operation. Exclude suspension or
assignment expressions in the first release. Preserve ordinary comments as
review context and reject pragmas whose association would change. Empty `if`
statements without an alternative stay with Ruff `RUF050`.[^2]

### Fresh list and set initialization

Propose `fold-fresh-list-initialization` for an immediately adjacent pair:
`items = []` followed by either one `items.append(value)` or one
`items.extend([values...])`. The receiver must resolve to that new exact list,
the target must be a simple function-local name, and each element must be a
literal or definitely bound local load that does not refer to `items`. Reject
starred elements, comprehensions, calls, descriptors, and closures.

Suggest a list display containing precisely the original elements. Restrict the
first release to one population statement; a run of consecutive appends already
has Ruff `FURB113` coverage. Reconsider broader fresh-list folding only after
an explicit upstream-overlap decision.

Propose `fold-fresh-set-initialization` for an unshadowed `set()` assignment
followed immediately by exactly one `add` call on that fresh local. Its element
must be a literal or stable, definitely bound local load with established exact
`str`, `bytes`, `int`, `bool`, or `NoneType` type. That domain excludes
effectful hashing and equality. Suggest a one-element set display. Defer
multiple additions: literal construction and constant folding can change
iteration order even for primitive elements. For example, successive additions
of `0`, `3`, and `11` can iterate differently from `{0, 3, 11}` on Python 3.12.

Both rules require a target that is definitely unbound before its initial
assignment, rather than merely a newly allocated collection. Replacing an old
binding could invoke its finalizer before the original population but after a
replacement display has evaluated its elements. Element bindings must remain
stable throughout the candidate. The collection must not escape, gain an alias,
or become visible through a closure before population ends. Reads of the
partially initialized target suppress the candidate. An element expression that
can raise also suppresses it: the original program may expose a partially
populated collection after failure. Allocation failure remains outside the
shared contract's model.

The published Sourcery `Merge List Extend` example accidentally changes one
comma-containing string into three strings. Tests must preserve the actual
elements; that example is evidence for intent, not a correctness oracle.[^1]

### Literal-true assertions and trailing continues

Propose `assert-literal-true` only for `assert True`, optionally with a
message. Suggest inspecting the absent assertion condition before removal. Do
not expand this into constant folding of arbitrary expressions: even an
always-truthy expression may execute effects. An assertion message is lazy and
never evaluated on this path. The first release provides no deletion fix.

Propose `redundant-trailing-continue` only when `continue` is the final direct
statement in a synchronous loop body. Reject nested `try`, `finally`,
conditional, or context-manager positions until a separate control-flow proof
supports them. Removing this direct statement must reach precisely the same
next-iteration or loop-`else` path. Ruff `RET507` removes an `else` after
`continue`; it does not own this deletion.

## Requirements and acceptance tests

Use separate opt-in symbols for the six categories above. The two fresh
collection symbols remain independent. Numeric message IDs stay unallocated.
Anchor structural diagnostics on the opening statement, assertions on the
`assert`, and continues on the `continue` token.

| Family            | Required acceptance evidence                                                                                                                                                                                                                                                       |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Nested try        | Event traces for body, each handler, `else`, and `finally`; normal return, body failure, handler failure, and cleanup override; reject all excluded shapes.                                                                                                                        |
| Handlers          | Both exception targets, non-matching propagation, flat tuple concatenation, handler order, target deletion, and early class-expression failure; reject subclass-overlapping classes, bodies differing only in literal payload type, `except*`, and user-defined class expressions. |
| Empty branches    | Truth-test event counts, exceptions from the unchanged condition, earlier `elif` selection, and no accidental comparison inversion.                                                                                                                                                |
| Fresh collections | Final values, order, alias identity, receiver self-reference, throwing elements, custom hash/equality, and original element boundaries; reject previously bound targets with finalizers, unstable element bindings, and multiple set additions.                                    |
| Assert            | Literal `True` with/without a message; lazy message effects; no match for a call, literal string, tuple, or false assertion.                                                                                                                                                       |
| Continue          | Empty/non-empty iteration, `break` elsewhere, loop `else`, and rejected nested control flow.                                                                                                                                                                                       |

_Table 1: Semantic acceptance requirements for structural candidates._

Add cross-rule tests: `assert-literal-true` subsumes `C9102` on that assertion
only when the new message actually emits. Verify that disabling or suppressing
it preserves `C9102`. `flatten-compatible-try` takes precedence over handler
merging within the same proposed replacement during one run. A later run may
report the handler opportunity. Keep that ordering deterministic and
re-evaluate it against the suite's minimal-message policy.

The implementation must retain exact source spans and comments in evidence even
though it performs no edits. Test Pylint registration, suppression,
target-version behaviour, supported dependency endpoints, and worker runs as
specified in the shared contract.

## Compatibility and migration

All suggested syntax supports Python 3.12. Parentheses around exception tuples
are mandatory for this minimum. Introduce messages disabled by default and
publish concrete eligibility examples when each implementation ships. No
parser, runtime dependency, or command changes accompany this RFC.

## Alternatives considered

Broad text matching would miss handler-expression evaluation and partially
built collection visibility. Reject it. An automatic fixer would also need
comment and pragma relocation rules; defer that capability. A general
control-flow simplifier would overlap RFC 0006 and require much more analysis
than these bounded structural patterns.

## Open questions

- Should differing ordinary comments suppress handler merging permanently,
  or should a later diagnostic include both comment ranges for review?
- Does corpus evidence justify extending trailing-continue detection into
  conditional branches after a local control-flow model exists?

## Recommendation

Implement compatible try flattening and pass-only branch inversion first. Add
handler merging and collection initialization only with their evaluation and
alias counterexamples in the acceptance suite.

[^1]: Sourcery:
      [flatten nested try](https://docs.sourcery.ai/reference/refactorings/python/flatten-nested-try/),
    [merge exception handlers](https://docs.sourcery.ai/reference/refactorings/python/merge-except-handler/),
    [remove pass from body](https://docs.sourcery.ai/reference/refactorings/python/remove-pass-body/),
    [merge list extend](https://docs.sourcery.ai/reference/refactorings/python/merge-list-extend/),
    [merge set add](https://docs.sourcery.ai/reference/refactorings/python/merge-set-add/),
    [remove assert true](https://docs.sourcery.ai/reference/refactorings/python/remove-assert-true/),
    and [remove redundant continue](https://docs.sourcery.ai/reference/refactorings/python/remove-redundant-continue/).
[^2]: Ruff: [rule catalogue](https://docs.astral.sh/ruff/rules/),
    [repeated append](https://docs.astral.sh/ruff/rules/repeated-append/),
    and [unnecessary if](https://docs.astral.sh/ruff/rules/unnecessary-if/).
    Pylint: [dict-init-mutate](https://pylint.readthedocs.io/en/stable/user_guide/messages/convention/dict-init-mutate.html).
[^3]: [Existing assertion-message checker](https://github.com/leynos/df12-python-lints/blob/4a85457d862fe62f6fb9590a6d77cfcc23ab509c/df12_python_lints/assert_messages.py).
[^4]: Python 3.12:
      [the try statement](https://docs.python.org/3.12/reference/compound_stmts.html#the-try-statement).
