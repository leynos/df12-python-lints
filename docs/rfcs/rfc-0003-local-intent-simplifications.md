# RFC 0003: Local intent simplifications

## Preamble

- **RFC number:** 0003
- **Status:** Proposed
- **Created:** 2026-11-14
- **Baseline:** Python 3.12 or later.
- **Audience:** Pylint checker implementers and reviewers.

## Summary

Add opt-in diagnostics for six local idioms: iterable min/max defaults,
last-element indexing, string membership, string prefix/suffix checks, counting
every element of a sized collection, and single-entry dictionary updates. Each
message requires evidence that the more direct expression preserves the
operation's semantics.

The [shared refactoring lint contract](../refactoring-lint-contract.md) governs
evidence, inference limits, Pylint integration, suppression, and verification.
The first release reports advice and makes no source edits. Sourcery's public
catalogue provides the candidate semantics and inspiration; this proposal
includes no implementation code from Sourcery.[^1]

## Problem and current state

These idioms hide the operation behind an explicit condition, index
calculation, traversal, or temporary mapping. Existing upstream checks cover
neighbouring patterns without owning these complete transformations.

| Candidate                | Existing owner nearby                  | Residual scope                                                                     |
| ------------------------ | -------------------------------------- | ---------------------------------------------------------------------------------- |
| Iterable min/max default | Ruff `PLR1730`; Pylint `R1730`/`R1731` | An empty-collection fallback, rather than selection between two values.            |
| Last-element index       | No targeted equivalent identified      | `items[len(items) - 1]` for an established sequence.                               |
| String membership        | No targeted equivalent identified      | A `find`/`count` result used only as an existence test.                            |
| Prefix/suffix check      | Ruff `PIE810`, `FURB188`               | Slice comparisons; the upstream rules combine existing tests or remove affixes.    |
| Sized reduction          | No targeted equivalent identified      | `sum(1 for item in items)` where direct length preserves observations.             |
| Single-entry update      | Optional Pylint `C3401`                | An existing dictionary's one-entry update, rather than folding its initialization. |

_Table 1: Rule boundaries checked against upstream documentation on 2026-11-14._

Ruff's rule catalogue and Pylint's dictionary initialization check define the
upstream boundaries. Implementations must recheck the pinned versions before
adding a duplicate diagnostic.[^2] RFC 0005 owns explicit comparisons with
`len`, RFC 0008 owns dictionary union/filtering, and RFC 0010 owns numeric
reductions that add values.

## Goals and non-goals

Recognize narrow, useful patterns with source-backed exact-type evidence.
Preserve types, identity where observable, evaluation order, and exceptions
within the shared contract's model. Report the operation the developer can use
and the range that can change.

Generic collection protocols, arbitrary mapping implementations, subclass
dispatch, bounded substring searches, and algebraic index normalization are
outside the first release. Type annotations alone never establish eligibility.
No new message duplicates an upstream rule's complete supported pattern.

## Proposed design

### Min/max defaults

Propose `prefer-minmax-default` for a two-arm statement that assigns the same
simple local target in both arms. Its condition must be the same definitely
bound local sequence name passed as the sole positional argument to an
unshadowed `min` or `max`; the other arm must assign a constant default.
Support the positive condition and its direct `not` inversion.

The sequence must have established exact type `list`, `tuple`, `str`, or
`bytes`, with stable binding between the test and call. Its truth test must
mean non-emptiness. The default must be an immutable literal constant, with no
call, lookup, named expression, or format evaluation. This restriction
preserves the original lazy fallback despite argument evaluation becoming
eager. Exclude `key`, multiple positional arguments, surrounding target
mutation, and already supplied `default` keywords in the first release.[^3]

The following pair illustrates the whole candidate; the list display supplies
exact-type evidence.

```python
scores = [12, 4, 9]
if scores:
    highest = max(scores)
else:
    highest = 0
```

Suggested form:

```python
scores = [12, 4, 9]
highest = max(scores, default=0)
```

The message anchors the `if` and names the reduction. A computed fallback such
as `load_default()` suppresses the diagnostic even if it appears cheap.

### Last-element indexing

Propose `prefer-negative-index` for exactly `items[len(items) - 1]`, where both
occurrences refer to the same definitely bound local and `len` resolves to its
built-in. Establish exact `list`, `tuple`, `str`, or `bytes` type and stable
binding. Suggest `items[-1]`.[^4]

Exclude mappings, custom sequences, repeated receiver calls, an overloaded
index operand, and other index arithmetic. Do not extrapolate a last-element
rule into a general algebra simplifier. Empty sequences must preserve
`IndexError`; the test suite checks empty and non-empty paths.

### String membership and affixes

Propose `prefer-string-membership` for an exact `str` or `bytes` receiver and
same-kind literal or definitely bound needle. Recognize `find(needle)` with
comparison/operator pairs `(==, -1)`, `(!=, -1)`, `(>, -1)`, or `(>=, 0)`, and
`count(needle)` compared with zero using `>`, `==`, or `!=`. Canonicalize the
comparison orientation internally; do not treat every numeric comparison as
equivalent. Suggest the corresponding `in` or `not in` expression.[^5]

Both receiver and needle must be stable local loads or literals. Reject extra
arguments, keyword arguments, chained comparisons, mixed `str`/`bytes`, and use
of the numeric result elsewhere. A bare `find` truth test is not an existence
test and must never match. Empty needles remain supported because the specified
existence comparisons and membership agree.

Propose `prefer-string-affix-check` for `text[:n] == literal` or
`text[-n:] == literal` and their `!=` counterparts. Require a non-empty
same-kind `str`/`bytes` literal of length `n`, literal integer bounds, no step,
and the same receiver proof. Suggest `startswith`/`endswith`, with outer `not`
for inequality. Exclude the zero-length suffix case: `text[-0:]` is the whole
string, while every string ends with the empty string.[^5]

The messages anchor the comparison and state the replacement operation. Existing
`startswith`/`endswith` combinations remain upstream territory.

### Sized reductions

Propose `prefer-sized-length` for `sum(1 for item in items)`, requiring an exact
`int` literal `1`, with one synchronous generator clause, a simple local
generator target, no filters, and no `start` argument. Resolve `sum` and the
suggested `len` as unshadowed built-ins. Establish that `items` is an exact
built-in `list`, `tuple`, `str`, `bytes`, `dict`, `set`, or `frozenset`, and
that no operation can mutate or replace it within the candidate.[^3]

Iteration over those containers does not inspect element truth values or invoke
element equality for this generator. A list comprehension earlier in the
function can establish an exact list even when its elements have unknown types.
A generic iterable, asynchronous comprehension, custom iterator, or generator
function cannot establish the required length contract.

Exclude `range` initially: its mathematical length can exceed the platform's
`len` limit while an integer sum has no equivalent fixed-width limit. Support
would require an additional bounded-length proof. Anchor the `sum` call and
suggest `len(items)`, preserving the generator's separate binding scope.

### Single-entry dictionary updates

Propose `prefer-single-key-assignment` for a standalone
`mapping.update({key: value})`, with an established exact `dict` receiver, one
literal entry, no unpacking, and a simple local receiver name. Suggest
`mapping[key] = value`.[^6]

Evaluation order changes: a call evaluates its receiver and arguments in order,
whereas assignment evaluates the value before its target. Therefore the first
release accepts only definitely bound local loads or literals for `key` and
`value`. The key must have an established exact, immutable built-in type with
modelled, effect-free hashing and equality: `str`, `bytes`, `int`, `bool`, or
`NoneType`. Existing keys in the dictionary must share that closed key domain;
a custom existing key can execute equality during insertion. Opaque objects
remain permitted as values when merely loaded from a bound local. Reject calls,
attributes, comprehensions, named expressions, unknown key populations, and
subclasses.[^7]

The diagnostic anchors `update`. It does not apply to an expression whose
return value is used, and it does not claim that `update` and `__setitem__`
have equivalent behaviour on arbitrary mappings.

## Requirements and acceptance tests

Each candidate gets a separate symbolic message. Numeric identifiers remain
unallocated until implementation. The shared contract defines opt-in
registration, confidence, budgets, spans, and suppression behaviour.

| Family            | Required positive cases                                                   | Required rejection or counterexample cases                                                      |
| ----------------- | ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Min/max           | Empty/non-empty exact sequences; both branch orientations; `None` default | Generator truthiness; computed defaults; shadowed built-ins; custom `__bool__`; extra arguments |
| Negative index    | Empty/single/multiple elements; four supported sequence types             | Dictionary keys; custom `__getitem__`; repeated receiver calls; changed binding                 |
| Membership        | Empty needle; absent/present match; valid comparison orientations         | `find` used as truth value; bounded searches; mismatched kinds; chained comparisons             |
| Affix             | Short/long receivers; equality/inequality; prefix and suffix              | Empty suffix; wrong slice width; non-unit step; custom slicing                                  |
| Length            | Empty/non-empty supported containers; unknown element types               | Unsized input; filter; asynchronous generator; custom iteration; oversized range                |
| Dictionary update | Primitive keys; opaque loaded values; matching final aliases              | Calls whose event order changes; custom collision keys; dict subclass; used return value        |

_Table 2: Minimum semantic acceptance matrix._

Property tests compare source and suggested forms over bounded supported
values. Include exception class and event-log assertions for adversarial
objects, and prove that the checker rejects those objects instead of merely
showing the happy-path replacement works. Run under Python 3.12 and newer
supported runtimes; test target-version gates independently of host version.

## Compatibility and migration

The package remains Python 3.12+. No syntax requires a higher minimum.
Implement one family at a time and retain the existing Pylint dependency range.
Document each newly available opt-in symbol in the users' guide only when its
implementation ships. These RFCs themselves change no enabled rule.

## Alternatives considered

An annotation-driven matcher would recognize more code but mistake protocol or
subclass behaviour for exact built-ins. Reject that approach. A generic algebra
engine would substantially enlarge the proof obligations; keep numeric
normalization in RFC 0010. Existing Ruff/Pylint checks remain the owner
whenever their matcher already covers the full candidate.

## Open questions

- Which exact-type origins beyond literals and local reaching definitions
  justify their implementation cost after the first corpus evaluation?
- Should bounded string-search arguments form a later separate diagnostic?

These questions concern expansion only; the initial grammar above is fixed.

## Recommendation

Start with string affix checks, last-element indexing, and constant min/max
defaults. Add sized reductions and one-key updates only after their type,
iteration, and key-domain evidence passes adversarial tests.

[^1]: Sourcery:
      [max/min default](https://docs.sourcery.ai/reference/refactorings/python/max-min-default/),
    [negative index](https://docs.sourcery.ai/reference/refactorings/python/simplify-negative-index/),
    [substring search](https://docs.sourcery.ai/reference/refactorings/python/simplify-substring-search/),
    [prefix/suffix checks](https://docs.sourcery.ai/reference/refactorings/python/str-prefix-suffix/),
    [use len](https://docs.sourcery.ai/reference/refactorings/python/use-len/),
    and [dictionary update](https://docs.sourcery.ai/reference/refactorings/python/simplify-dictionary-update/).
[^2]: Ruff: [rule catalogue](https://docs.astral.sh/ruff/rules/).
    Pylint: [dict-init-mutate](https://pylint.readthedocs.io/en/stable/user_guide/messages/convention/dict-init-mutate.html).
[^3]: Python 3.12:
      [built-in functions](https://docs.python.org/3.12/library/functions.html).
[^4]: Python 3.12:
      [sequence operations](https://docs.python.org/3.12/library/stdtypes.html#common-sequence-operations).
[^5]: Python 3.12:
      [string methods](https://docs.python.org/3.12/library/stdtypes.html#string-methods).
[^6]: Python 3.12:
      [dictionary operations](https://docs.python.org/3.12/library/stdtypes.html#mapping-types-dict).
[^7]: Python 3.12:
      [evaluation order](https://docs.python.org/3.12/reference/expressions.html#evaluation-order).
