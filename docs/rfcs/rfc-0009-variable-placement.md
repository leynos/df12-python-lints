# RFC 0009: Variable placement

## Preamble

- **RFC number:** 0009
- **Status:** Proposed
- **Created:** 2026-11-14

## Summary

Propose conservative diagnostics for local assignment placement, single-use
inlining, reuse of an established value, and repeated-read `while` loops that
can use an assignment expression. Each policy has proof obligations; the loop
proposal preserves repeated input operations.

The [shared refactoring lint contract](../refactoring-lint-contract.md) governs
activation, uncertainty, source reporting, and suppression. Version one
supplies no automatic fixes. Sourcery's placement, inlining, value-reuse, and
named expression transformations provide semantic inspiration; no
implementation code or examples have been copied.[^1]

## Problem

A distant definition increases the state a reader must track. Single-use
temporaries can obscure expressions, repeated evaluation can obscure available
values, and primed loops duplicate their input operation.

Moving or eliminating an assignment can also change when an exception occurs,
which object a consumer receives, whether a closure sees a binding, or how many
times an operation executes. Each diagnostic must assess a particular
replacement rather than reward fewer locals.

## Current state

At the reviewed main commit, the package registers ten checkers exposing
thirteen messages. The registry, tests, configuration, and documentation
contain no custom walrus or named-expression checker. Searches found no
corresponding published proposal.[^2] Unpublished work and other repositories
remain unknown.

Pylint's bundled optional `R6103` (`consider-using-assignment-expr`) belongs to
`pylint.extensions.code_style`. It recognizes assignments immediately before an
`if`, but its released implementation does not handle the primed-read `while`
pattern.[^3] Delegate the `if` case upstream. The current repository
configuration does not load that extension or enable its message.

Ruff `RET504` covers assignment immediately returned. Ruff `PLR1733` and
`PLR1736`, with corresponding Pylint messages, reuse values already bound by
`items()` and `enumerate()`.[^4] These supported shapes remain upstream-owned.
The package has lexical-binding helpers but no general reaching-definition,
liveness, or expression-equivalence engine.

## Goals and non-goals

Use four provisional symbols: `move-local-assignment`,
`inline-single-use-local`, `reuse-proven-local-value`, and
`prefer-while-assignment-expression`. Allocate numeric identifiers only when
implementing accepted scope. RFC 0005 references the loop candidate here rather
than defining a second owner.

The initial scope is ordinary synchronous function locals with bounded
analysis. Globals, nonlocals, captured cells, arbitrary property caching,
cross-function analysis, and local-name minimization are outside scope. Moving
invariant expressions out of loops belongs to the separate loop-invariant
proposal, RFC 0002; it is not implemented infrastructure for this RFC.[^5]

## Proposed design

### Binding and movement evidence

Identify a binding by lexical scope and defining assignment, not identifier
text. A candidate needs a single reaching definition, definitely bound inputs,
and an account of every read, write, deletion, capture, and escape that can
affect its region. Movement and inlining initially require the target's first
binding, avoiding reordered finalization of a previous value. Include augmented
and annotated assignments, unpacking, assignment expressions, loop and
exception targets, and nested-scope capture.

Movement and inlining initially admit exactly this recursive expression grammar:

- Scalar constants whose exact type is `NoneType`, `bool`, `int`, `str`, or
  `bytes`.
- Definitely bound, uncaptured local-name loads with one of those established
  exact types.
- Unary `+` and `-`, and binary `+`, `-`, and `*`, when every operand has
  established exact `int` type. Preserve the original operation grouping.

Parentheses do not widen the grammar. Container displays, including empty ones,
unpacking, comprehensions, f-strings, floats, complex values, string
arithmetic, Boolean operators, comparisons, calls, attributes, and
subscriptions remain outside this movable domain. A list or tuple display
containing an opaque object is not a scalar literal and cannot pass as a
harmless allocation.

Establish scalar facts from these expressions and their local reaching
definitions. An already completed call to unshadowed builtin `len` may
establish an exact integer result; it does not make the call movable or justify
assumptions about its argument. Runtime type guards are deferred in this RFC.
An annotation or Astroid class inference alone supplies no proof. Unknown
evidence suppresses advice. Definitions, decorators, imports, cleanup regions,
suspension, and unsupported dynamic access terminate the region.

These admitted values have no user finalizers, and integer arithmetic cannot
invoke overloaded methods or raise within the shared model's resource limits.
Visible identity-sensitive uses still suppress a changed computed result under
the shared contract. Dictionary reuse and effectful loop reads have separate
contracts below; neither expands the movable grammar.

### Move a local assignment towards its use

`move-local-assignment` may move an ordinary assignment later in the same suite
when all uses remain dominated by it and every crossed operation commutes with
the assignment. Preserve dependency values, ordinary exceptions, observable
effects, object sharing, and the binding's visibility. Version one crosses only
assignments of admitted expressions to other fresh, uncaptured locals, with
disjoint dependencies. Unknown calls and compound statements remain barriers.

Sinking into one branch is a separate extension: it requires that every use
lies in that branch and that omitting evaluation on other paths is
unobservable. Do not infer this from textual use counts. Reject closure
capture, handler or cleanup observations, and values whose allocation or
destruction carries observable behaviour. Moving a declaration must not drop
its annotation or change when a local becomes bound.

Do not report trivial adjacent movement. Require at least one intervening
statement that the reader can omit from the variable's lifetime after the
change. Record that threshold as a noise policy, not a semantic proof.

### Inline a single-use temporary

`inline-single-use-local` requires exactly one evaluated use and a replacement
position with equivalent timing and multiplicity. Check the complete enclosing
expression: callees, preceding arguments, short-circuit operands,
comprehensions, and conditional expressions can execute before or instead of
the substituted value. An assignment followed by a syntactic reference is
insufficient.

The following example illustrates a candidate beyond a direct return alias:

```python
def count_score(parts):
    count = len(parts)
    squared = count * count
    return squared + 1
```

With the real builtin `len`, its successful result establishes an exact integer
for the local calculation. The proposed expression is:

```python
def count_score(parts):
    count = len(parts)
    return count * count + 1
```

Keep `len` in place without inferring properties of `parts`. Reject multiple
reads, captured names, annotated targets, and conditional or repeated use
sites. Suppress advice when an attached explanatory comment has no clear
destination.

### Reuse a proven local value

`reuse-proven-local-value` may replace a repeated expression with an existing
local only when the retained value and reevaluation have equivalent observable
results at that use. Prove that dependencies and relevant mutable state have
not changed; preserve any effects or exceptions that reevaluation would cause.

Start with adjacent, binding-aware cases in two domains. For admitted integer
expressions, the replacement must occupy an operand position in exact-integer
`+`, `-`, `*`, `==`, `!=`, `<`, `<=`, `>`, or `>=`. These value-only consumers
avoid promising identity-preserving reuse of a newly computed integer. Reject
`is`, `id`, and opaque consumers for this domain.

Separately admit `mapping["literal-key"]` when a local dictionary literal with
only literal string keys establishes the exact dictionary and key presence. Its
values may be scalar constants or definitely bound local loads, including
opaque objects. This literal supplies provenance only: its allocation and the
assignment retaining the lookup result stay in place. Require an unchanged,
uncaptured mapping with no alias escape and no intervening relevant effect,
including evaluation before the use inside the consuming expression. Repeating
the lookup returns the same object, so this domain may serve an opaque consumer.

Every other repeated expression, including string-building operations, remains
outside version one. Reject arbitrary calls, properties, unknown aliases, and
expressions mentioning the newly assigned target. Do not duplicate upstream
`items()`/`enumerate()` advice.

### Repeated-read while loops

`prefer-while-assignment-expression` owns the following complete shape: one
ordinary assignment immediately before a `while`, a header that tests the same
local name, and one identical refresh assignment as the final body statement.
Require the same target binding and structurally equivalent input expressions
with matching lexical bindings. Version one accepts only the bare-name
truthiness header and a synchronous input operation.[^6]

The following independent example repeats a reader call at the loop tail:

```python
def collect_packets(reader):
    packets = []
    packet = reader.read(4096)
    while packet:
        packets.append(packet)
        packet = reader.read(4096)
    return packets, packet
```

The proposed loop preserves the final falsy value as well as the packets:

```python
def collect_packets(reader):
    packets = []
    while packet := reader.read(4096):
        packets.append(packet)
    return packets, packet
```

The input call need not be pure: its repetition is intentional. Preserve its
receiver lookup, argument evaluation, call count, truth testing, and ordering
relative to each body execution. The reader may change between iterations; both
forms must resolve it at the corresponding read, without caching it.

Reject any `continue` targeting this loop: the original bypasses the tail read,
while the proposed header would perform another read. A `continue` belonging to
a nested loop is distinct and must not be confused with it. Reject extra writes
to the target, differing refresh expressions, conditional refresh, async
iteration, suspension, or a refresh inside a different cleanup region.

Preserve `break`, `return`, and raised exceptions that bypass the next read. A
loop `else` must run on the same exhaustion paths, and the target must retain
the same value after zero, one, or many iterations and after a break. Rejection
tests must include loop `else`, not silently omit it from the analysis. Do not
transform `while True` plus a leading break guard here; optional Pylint `R3501`
already owns that separate idiom.

### Architecture and selection

Keep the loop recognizer independent from general assignment movement. It can
prove a narrow control-flow correspondence without requiring arbitrary source
purity. Implement it first if accepted.

For other families, proposed per-function summaries should record reaching
definitions, use sites, crossed effects, and value or identity evidence. Reuse
existing lexical lookup contracts without treating
`_expressions.attribute_root` as a purity predicate. Extract shared helpers
only when concrete callers need the same contract. Cache bounded summaries,
terminate conservatively on unknown cycles, and clear state between modules.

Prefer the complete loop candidate over placement suggestions inside it. For
other overlaps, choose one maximal candidate in source order, identifying the
existing binding and destination. The shared contract governs deterministic
spans and independent message activation.

## Requirements and acceptance

Acceptance requires positive and refusal matrices for each symbol. Cover every
admitted expression form and one near-miss for each excluded form, particularly
container displays holding finalizing objects. Test completed `len` result
facts without moving its call, dictionary provenance without moving its
allocation, and unknown consumers of computed integers. Also cover shadowing,
lexical bindings, capture, writes, argument evaluation, short-circuiting,
exception and cleanup paths, identity, and explanatory comments.

For the loop rule, run original and test-only transformed functions against a
scripted reader with empty, single-packet, multi-packet, falsy-value, and
throwing sequences. Compare call traces, truth-test traces, returned values,
final target bindings, body effects, and `else` execution. Include break and
early-return paths, outer-loop `continue` rejection, and nested-loop target
isolation. A failing reader must not receive an extra call in the proposed form.

Differential placement tests must compare exceptions and observable sharing,
not merely final values. Property tests should establish scope isolation,
alpha- renaming, unique diagnostics, and conservative weakening of evidence.
Integration and resource-bound tests follow the shared contract. No diagnostic
ships until its refusal cases and representative findings have been reviewed.

## Compatibility and migration

This RFC implements no lint and changes no configuration. Existing consumers
can separately choose upstream `R6103` for the assignment-before-`if` policy.
Adopting this proposal must not automatically load that extension or enable its
other code-style messages.

All target syntax exists on Python 3.12. Retain the Pylint compatibility range
and opt-in rollout. Document the distinction between local placement, value
reuse, and input-loop restructuring before publishing the new symbols.

## Alternatives considered

Delegating all named-expression advice to `R6103` leaves the repeated-read loop
gap. A general optimizer would make a much larger alias and effect analysis a
prerequisite. Reporting only syntactic repetition would recommend unsafe
caching and reordered exceptions. Keeping separate bounded families allows the
loop candidate to proceed without claiming a general dataflow capability.

## Open questions

- Do movement and single-use inlining produce enough useful findings to justify
  separate messages after excluding comment-bearing and uncertain cases?
- Which exact builtin operations justify identity-safe reuse or value-only
  consumer contracts in an initial release?
- Should later loop support include explicit sentinel comparisons, and what
  parenthesization and comparison contracts would that require?

## Recommendation

Implement and evaluate the repeated-read `while` candidate first. Delegate
assignment-before-`if` to upstream Pylint, and stage other placement families
behind explicit evidence contracts and independent acceptance tests.

[^1]: Sourcery's
      [assignment placement](https://docs.sourcery.ai/reference/refactorings/python/move-assign-in-block/),
    [single-use inlining](https://docs.sourcery.ai/reference/refactorings/python/inline-variable/),
    [assigned-value reuse](https://docs.sourcery.ai/reference/refactorings/python/use-assigned-variable/),
    and [named expressions](https://docs.sourcery.ai/reference/refactorings/python/use-named-expression/).
[^2]: Reviewed repository commit
    [4a85457](https://github.com/leynos/df12-python-lints/tree/4a85457d862fe62f6fb9590a6d77cfcc23ab509c),
    including [registration](../../df12_python_lints/__init__.py),
    [registration tests](../../tests/test_plugin.py), and
    [configuration](../../pyproject.toml).
[^3]: Pylint
      [R6103](https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/consider-using-assignment-expr.html)
    and its released [code-style implementation](https://github.com/pylint-dev/pylint/blob/v4.1.3/pylint/extensions/code_style.py).
[^4]: Ruff [RET504](https://docs.astral.sh/ruff/rules/unnecessary-assign/),
    [PLR1733](https://docs.astral.sh/ruff/rules/unnecessary-dict-index-lookup/),
    and [PLR1736](https://docs.astral.sh/ruff/rules/unnecessary-list-index-lookup/).
[^5]: Proposed
      [RFC 0002 in pull request 83](https://github.com/leynos/df12-python-lints/pull/83)
    describes conservative loop-invariant analysis; its helpers are not shipped.
[^6]: [PEP 572](https://peps.python.org/pep-0572/) defines assignment-expression
    binding and evaluation semantics; Python's
    [while statement](https://docs.python.org/3.12/reference/compound_stmts.html#the-while-statement)
    defines the relevant loop exits.
