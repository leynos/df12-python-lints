# RFC 0005: Residual idiom refactorings

## Preamble

- **RFC number:** 0005
- **Status:** Proposed
- **Created:** 2026-11-14
- **Baseline:** Python 3.12 or later.
- **Audience:** Pylint checker implementers and reviewers.

## Summary

Add opt-in diagnostics for useful forms left outside neighbouring Ruff and
Pylint checks: redundant identity generators, flag-based searches, joining
transformed strings, first-match loops, explicit length comparisons, and
assignment-plus-fallback blocks. Delegate the repeated-read walrus pattern to
[RFC 0009](rfc-0009-variable-placement.md).

The [shared refactoring lint contract](../refactoring-lint-contract.md) governs
evidence and reporting. The first release emits suggestions without editing
source. Sourcery's catalogue provides the candidate semantics and inspiration;
this RFC includes no Sourcery implementation code.[^1]

## Problem and current state

A rule name that mentions an idiom does not imply that its matcher covers every
source form. Each proposed message owns only the stated residual case.

| Candidate             | Existing upstream coverage                    | Proposed residual form                                                        |
| --------------------- | --------------------------------------------- | ----------------------------------------------------------------------------- |
| Identity generator    | Ruff `C400`/`C401` for `list`/`set` consumers | Identity generators inside unshadowed `any`/`all`.                            |
| Boolean search        | Ruff `SIM110`; optional Pylint `C0501`        | A local flag assignment followed by `break`.                                  |
| Joining strings       | Pylint `R1713`                                | Modelled transformations of each piece, beyond the raw-loop-variable matcher. |
| First match           | Ruff `RUF015`                                 | A search loop that returns its first matching item, then returns a default.   |
| Length comparison     | Ruff `PLC1802`; Pylint `C1802`/`C1805`        | Explicit `> 0` and `<= 0` in a direct condition.                              |
| Fallback block        | Ruff `FURB110`                                | Assignment followed by an `if not` reassignment.                              |
| Assignment expression | Optional Pylint `R6103`                       | Repeated-read `while`, owned by RFC 0009.                                     |

_Table 1: Residual ownership, checked against upstream documentation on
2026-11-14._

Ruff documents the Boolean-return loop and materialize-then-select patterns
separately. Pylint's assignment-expression rule describes assignment before
`if`, while `C1805` concerns zero equality and inequality.[^2] Confirm these
boundaries against actual pinned matcher fixtures at implementation time.

## Goals and non-goals

Express a simple operation directly while preserving short-circuiting, iterator
consumption, exceptional paths, and surviving local bindings. Unknown evidence
suppresses advice, even when the shorter expression looks plausible.

The first release excludes arbitrary callbacks, descriptor reads, asynchronous
iteration, comprehensions with filters except where explicitly specified, and
functions relying on frame or local-variable inspection. It does not replace
generic consumers with collection arguments, implement a general
loop-to-comprehension engine, or claim a universal speed improvement.

## Proposed design

### Shared loop domain

The first-release loop transformations below require a synchronous loop in a
synchronous function body, over an established exact built-in list or tuple
with stable binding and no mutation during the candidate. Module and class
scope cannot satisfy the local-binding proof. The loop variable must be a fresh
simple local: no earlier binding that reassignment could release, no capture,
and no read or identity observation after the candidate, including enclosing
handlers and cleanup. The candidate cannot cross a scope boundary.

Flag and first-match transformations also require elements with established
exact `bool`, `int`, `str`, `bytes`, or `NoneType` types, independently of the
predicate's result type. A dead loop variable can still retain an arbitrary
object until function exit; deleting that binding can advance its finalizer.
Joining has its own exact-string element requirement. Identity-generator
removal creates no new change to an outer loop binding and uses its separate
proof below.

A supported predicate contains literals, definitely bound local loads, `not`,
and modelled comparisons on established exact `bool`, `int`, `str`, `bytes`, or
`NoneType` values. Ordering requires compatible kinds. It must produce an exact
Boolean and cannot invoke user code or raise on the proved domain. Calls,
descriptors, and rich comparisons with unknown operands are unknown. These
restrictions prevent moving a possible `StopIteration` into a generator, where
PEP 479 changes it into `RuntimeError`.[^3]

An implementation must define concrete transfer functions for element facts; it
cannot infer homogeneous elements merely from an annotation. Literal containers
and established local origins are sufficient for an initial implementation.
Unsupported loop shapes remain silent.

### Identity generators

Propose `remove-identity-generator` for `any(item for item in items)` and
`all(item for item in items)`, resolving the consumer to its unshadowed
built-in. Require one synchronous generator clause, an identical simple-name
element and target, and no filter. Establish `items` as an exact built-in list
or tuple in the first release. Each element must have established exact `bool`,
`int`, `str`, `bytes`, or `NoneType` type. Suggest passing `items` directly.

Both forms perform their truth test inside the same built-in consumer, outside
the generator body. Nevertheless, a custom truth method can observe the extra
reference held by a generator and return a different result. The closed element
domain excludes those callbacks. Preserve order and the short-circuit position.
Never extend this rule to arbitrary consumers that may inspect argument type or
identity. Keep general iterator and iterable protocols outside the initial
domain.

### Flag-based Boolean searches

Propose `prefer-flag-any` for this complete shape: a fresh local flag receives
literal `False`; a following loop contains only an `if` with a supported
predicate; its body assigns literal `True` to the flag and breaks. There is no
loop `else`, alternative branch, other assignment, or use of the flag within
the loop.

The following pair illustrates the pattern with exact integer elements.

```python
def has_high_score():
    scores = [2, 11, 4]
    found = False
    for score in scores:
        if score > 10:
            found = True
            break
    return found
```

Suggested form:

```python
def has_high_score():
    scores = [2, 11, 4]
    found = any(score > 10 for score in scores)
    return found
```

Apply the shared loop domain. The predicate must be total on that domain:
otherwise the original flag assignment can remain visible after failure while
the rewritten right-hand side fails before assignment. The `any` lookup must
resolve to the built-in. Anchor the initial flag assignment and span the loop.
Boolean-return loops remain with `SIM110`/`C0501`.[^4]

### Joining transformed string pieces

Propose `prefer-transformed-string-join` for a fresh local initialized to `""`,
followed by a loop whose only statement adds a transformed string piece to that
local. Support both `result += piece` and `result = result + piece` after
exact-string evidence establishes equivalent behaviour. The accumulator must
not be read, captured, or observed between iterations.

The initial transformation grammar permits `item.strip()` and `item.lower()` on
established exact string elements, with no arguments and no further chaining.
Suggest `"".join(transform(item) for item in items)`. Both methods return
strings without user callbacks under that model. Raw `item` addition remains
with Pylint `R1713`; arbitrary `item.description` is deferred because an
attribute can invoke a descriptor and fail.[^5]

Apply the shared loop-domain checks and reject visible identity-sensitive uses
of the computed string. Include empty input and method failures from rejected
subclasses in tests. The claim is a clearer aggregate operation; performance
claims require separate measurements on supported interpreters.

### First matching item

Propose `prefer-first-match-next` for a loop whose sole statement is
`if predicate(item): return item`, immediately followed by `return default`.
There is no loop `else`, additional work, enclosing handler/cleanup that
observes changed locals, or suspension. Apply the shared loop domain and
predicate grammar.

The default must be an immutable literal or definitely bound local whose load
is effect-free. Its evaluation becomes eager in
`next((item for item in items if predicate(item)), default)`. Reject a call,
attribute, subscription, named expression, or expression that can fail in that
position. Resolve `next` to its built-in and preserve the returned item's
identity. The message anchors the loop and identifies the default.
Materialize-and-select patterns remain with Ruff `RUF015`.[^6]

### Explicit length comparisons

Propose `prefer-length-truth-test` for direct `if`, `while`, or conditional
expression tests consisting of `len(items) > 0` or `len(items) <= 0`, including
reversed comparison operands. Resolve `len` to its built-in and establish an
exact list, tuple, dictionary, set, frozen set, string, or bytes value with
stable binding. Suggest `items` or `not items` in that test position.[^7]

Exclude value-producing contexts: replacing `return len(items) > 0` with
`return items` changes the return type. Also exclude custom truth/length
implementations, array-like values, `range` without a bounded-length proof, and
comparisons with other bounds. Bare `if len(items)` and equality with zero stay
with the upstream checks identified in Table 1.

### Assignment-plus-fallback blocks

Propose `prefer-fallback-expression` for a fresh simple local assignment
followed immediately by `if not value: value = fallback`, with no `else` and no
other body statement. The local must not be captured or observed by any
operation within the candidate. Suggest `value = primary or fallback`.

The initial domain requires primary and fallback to be literals or definitely
bound local loads. Establish the primary's exact built-in truth behaviour; do
not infer it from a protocol or annotation. The fallback can load an opaque
bound object because neither form tests it. Reject fallible or effectful
operands: the original local exists during the fallback, whereas the
replacement assigns only after its right-hand side completes.

All falsy values must intentionally trigger the fallback. A `None`-only test is
a different operation and must not match. Existing conditional expressions
remain with Ruff `FURB110`.[^8]

## Requirements and acceptance tests

Each family gets its own independently enableable symbol. Numeric IDs remain
unallocated. The shared contract supplies confidence, source-span, inference
budget, suppression, and supported-Pylint requirements.

| Family             | Required semantic cases                                                                                                                                                                                |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Identity generator | Empty input and short-circuiting over admitted scalars; reject custom truth methods, including reference-count-sensitive results, unsupported consumers, filters, and shadowing.                       |
| Flag search        | No match/first/middle/last match; fresh versus pre-bound targets; reject module/class scope; element finalizers after clearing the input; capture and cleanup observers; rejected throwing predicates. |
| Transformed join   | Empty/single/multiple strings; exact methods versus overrides; non-string pieces; accumulator observation; identity-sensitive consumers.                                                               |
| First match        | Absent/present match; default identity; eager-default counterexamples; rejected `StopIteration` predicates and live loop targets.                                                                      |
| Length test        | Supported empty/non-empty values; value-context rejection; zero-equality delegation; custom truth/length and oversized ranges.                                                                         |
| Fallback           | Every supported falsy kind, truthy primary, opaque fallback, `None`-only rejection, captured locals, and exceptions exposing intermediate bindings.                                                    |

_Table 2: Minimum acceptance matrix for residual idioms._

Compare results, types, exception classes, event traces, and final bindings
over the supported domains. Negative fixtures must establish absence of the
diagnostic, not merely record a runtime mismatch. Test rule ownership by
pinning upstream examples and confirming the new checker stays silent on those
complete patterns.

## Compatibility and migration

All recommended forms support Python 3.12. PEP 709 inlines collection
comprehensions in that release; it does not justify claiming that every
generator is faster.[^9] Short-circuiting and memory changes must follow the
specific rule's evidence rather than a blanket generator preference.

Roll out one opt-in message at a time. Identity-generator removal and explicit
length tests have the smallest initial proof domains. Search, join, and
fallback messages follow after local binding/exception-path analysis exists.
RFC 0009 owns the walrus extension; no duplicate message registers here.

## Alternatives considered

Treating upstream names as full coverage would miss the residual statement
forms. Reimplementing those upstream rules would create competing advice. This
proposal instead owns explicit non-overlapping shapes. Broad callback inference
would recognize more searches but require exception and effect models beyond
this first release.

## Open questions

- Which real corpus cases justify widening the closed string transformation
  grammar beyond `strip()` and `lower()`?
- Can a later iterator model expand identity-generator removal while
  preserving lifecycle and exception observations?

## Recommendation

Implement the small residual matchers first, then add loop transformations only
when exceptional paths and binding lifetimes have direct regression coverage.
Keep repeated-read walrus detection in RFC 0009.

[^1]: Sourcery:
      [simplify generator](https://docs.sourcery.ai/reference/refactorings/python/simplify-generator/),
    [use any](https://docs.sourcery.ai/reference/refactorings/python/use-any/),
    [use join](https://docs.sourcery.ai/reference/refactorings/python/use-join/),
    [use next](https://docs.sourcery.ai/reference/refactorings/python/use-next/),
    [length comparison](https://docs.sourcery.ai/reference/refactorings/python/simplify-len-comparison/),
    and [fallback](https://docs.sourcery.ai/reference/refactorings/python/use-or-for-fallback/).
[^2]: Pylint:
      [assignment expressions](https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/consider-using-assignment-expr.html)
    and [zero comparison](https://pylint.readthedocs.io/en/stable/user_guide/messages/convention/use-implicit-booleaness-not-comparison-to-zero.html).
[^3]: [PEP 479: generator StopIteration handling](https://peps.python.org/pep-0479/).
[^4]: Ruff:
      [reimplemented builtin, SIM110](https://docs.astral.sh/ruff/rules/reimplemented-builtin/).
[^5]: Pylint:
      [consider-using-join](https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/consider-using-join.html).
    Python 3.12: [string methods](https://docs.python.org/3.12/library/stdtypes.html#string-methods).
[^6]: Ruff:
      [unnecessary iterable allocation, RUF015](https://docs.astral.sh/ruff/rules/unnecessary-iterable-allocation-for-first-element/).
[^7]: Ruff: [len test, PLC1802](https://docs.astral.sh/ruff/rules/len-test/).
    Python 3.12: [truth-value testing](https://docs.python.org/3.12/library/stdtypes.html#truth-value-testing).
[^8]: Ruff:
      [conditional fallback, FURB110](https://docs.astral.sh/ruff/rules/if-exp-instead-of-or-operator/).
[^9]: [PEP 709: inlined comprehensions](https://peps.python.org/pep-0709/).
