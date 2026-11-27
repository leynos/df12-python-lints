# RFC 0002: Conservative loop-invariant expression lint

## Preamble

- **RFC number:** 0002
- **Status:** Proposed
- **Created:** 2026-11-14
- **Scope:** A new, opt-in Pylint checker in `df12-python-lints`.
- **Delivery:** Semantics and acceptance criteria only; no implementation.

## Summary

Add `loop-invariant-expression`, a conservative diagnostic for repeated
computations inside synchronous loops. Report an expression only when the
analysis establishes stable dependencies, safe evaluation outside the loop,
safe reuse of the result, and a plausible reduction in repeated work. Unknown
facts suppress the diagnostic. Do not provide automatic fixes.

Anthony Shaw's Perflint, particularly W8201 `loop-invariant-statement`, supplies
the semantic starting point and inspiration: identify expressions and
subexpressions whose inputs do not change across loop iterations, and account
for operations that can mutate those inputs.[^1] This proposal deliberately
narrows that idea to expression-level recommendations with explicit effects,
control-flow, identity, and cost contracts. It does not claim behavioural
compatibility with Perflint.

This RFC contains no Perflint implementation code, copied tests, or copied
examples. It proposes an independent implementation, not a vendored checker or
a new runtime dependency.

## Problem

An expression that refers only to unchanged names is not necessarily constant:
those names can refer to mutable objects, descriptors, stateful callables, or
objects with overloaded operations. Even a constant result does not establish
that moving its evaluation preserves exceptions, side effects, or object
identity. Finally, a safe transformation need not improve performance.

Loop-invariant code motion (LICM) therefore involves three separate questions:
whether a computation is invariant, whether evaluating and reusing it elsewhere
preserves the relevant behaviour, and whether avoiding repeated evaluation is
worth considering. A lint consumed by humans and implementing agents must not
present an answer to the first question as an answer to all three.

## Current state

The package already loads custom checkers through `df12_python_lints` and
supports `pylint>=3.3,<5`. Its published inventory does not include this
expression-level rule.[^2] The conservative dataclass analysis establishes a
relevant precedent: uncertainty suppresses advice, analysis does not execute
the inspected program, and repeated analysis uses bounded local caches.[^3]

This RFC adds no checker registration, dependency, configuration, or shipped
message. Its example configuration describes the proposed future interface,
not a feature available in the current release.

## Goals and non-goals

Goals:

- Find worthwhile repeated computations without recommending changes to
  observable application behaviour within the documented analysis model.
- Specify independently testable invariance, movement, reuse, and cost rules.
- Integrate with ordinary Pylint selection, reporting, and suppression.
- Prefer false negatives to recommendations founded on uncertain evidence.

Non-goals:

- General Python optimization, whole-program alias analysis, or proving
  arbitrary functions pure.
- Moving statements, assignments, branches, or loops as complete units.
- Loop unswitching, automatic rewriting, or introducing lazy caches.
- Importing Perflint's implementation or its unrelated performance messages.
- Claiming a measured speed-up from source syntax alone.

## Proposed design

The following subsections define the proposed normative behaviour. “Must”
indicates an acceptance requirement, not a claim that an implementation exists.

### 1. Public diagnostic and plugin integration

Use the symbol `loop-invariant-expression`. Allocate an unused `R91xx`
identifier at implementation time, checking shipped and pending messages.
This RFC reserves no numeric message identifier and does not renumber existing
messages. The category is refactoring advice, not a claim that the original
program is incorrect.

The proposed message is:

```plaintext
Expression %r repeats loop-invariant work; consider computing it once before the loop at line %s
```

The expression argument must be a bounded, single-line source rendering. Attach
the diagnostic to the complete expression span, not the enclosing statement.
The line argument identifies the selected loop. The extended message help must
explain the analysis assumptions, lack of automatic fixes, and need to measure
performance before making a non-trivial refactor.

Register the checker through the existing package plugin. Keep the message
disabled by default using Pylint's message mechanism, without a second custom
feature switch. Proposed explicit activation is:

```toml
[tool.pylint.main]
load-plugins = ["df12_python_lints"]

[tool.pylint."messages control"]
enable = ["loop-invariant-expression"]
```

Normal Pylint command-line selection and local suppression must work. An
intentional suppression needs an explanation under the existing df12 policy.
Analysis must work when this is the only enabled message, with no dependency on
another checker's visitor or enabled state. Use Pylint's existing confidence
levels honestly: inferred facts must not masquerade as purely syntactic
certainty. Native checker registration and reporting remain the integration
boundary.[^4]

### 2. The transformation being assessed

For each candidate expression, assess a conceptual rewrite that creates a fresh
local binding immediately before the selected loop and replaces that expression
occurrence with a read of the binding. Keep the enclosing statements, assignment
targets, branches, and number of externally visible actions unchanged.

This is a semantic test for emitting advice, not an automatic-fix specification.
The binding must not collide with existing names, change an existing target's
post-loop value, or escape its enclosing execution scope. Do not simulate a
rewrite by importing, evaluating, or modifying the inspected program.

A candidate qualifies only when all four predicates hold:

- **Invariant:** every dependency retains the relevant value or state across
  all relevant iterations and paths.
- **Movable:** earlier evaluation preserves ordinary exceptions, effects, and
  control-flow behaviour under subsection 3.
- **Reusable:** substituting one result for repeated results does not introduce
  observable sharing, mutation, identity, or lifetime differences.
- **Worth considering:** subsection 8 identifies non-trivial repeated work.

These predicates produce independent evidence. Purity alone establishes none of
termination, totality, identity-insensitive consumption, or profitability.

### 3. Analysis model and limits of the guarantee

The initial model covers ordinary sequential execution with the normal
semantics of resolved built-ins. Exclude external mutation of frames, debugger
or tracing intervention, asynchronous signal-handler mutation, concurrent
mutation, and monkey-patching of trusted built-ins. Recognized uses of `exec`,
`eval`, frame inspection, or dynamic namespace mutation invalidate affected
facts. Do not use this boundary to disregard ordinary callbacks, closures,
custom iteration, descriptors, or overloaded operations.

Preserve return values, ordinary exception behaviour, externally visible action
order and multiplicity, and observable aliasing or identity relationships. The
model does not promise identical timing, allocation counts, tracing events,
resource-exhaustion failures such as `MemoryError`, or delivery points of
asynchronous exceptions. These exclusions must appear in the eventual rule
help; without them, even ordinary allocation cannot be treated as total.

Python gives objects identity as well as value, and an immutable container may
refer to mutable objects.[^5] Consequently, “immutable” is not sufficient proof
that repeated results can be shared. Reject results passed to unknown consumers,
stored where identity or later mutation could be observed, compared with `is`,
or inspected through `id`. Fresh mutable containers and iterators are not
reusable candidates in the initial implementation.

A fresh immutable intermediate may qualify when all of its uses remain within
recognized value-only operations. The analysis must establish that containment
rather than assuming all immutable results have irrelevant identity.

### 4. Initial expression vocabulary

Start with a deliberately small, reviewed operation catalogue:

- No-argument `str.lower`, `str.upper`, and `str.casefold` on a proven exact
  built-in `str` supply eligible string-transform work.
- Resolved built-in `len` on exact `str`, `bytes`, or `tuple` can consume or
  compose with that work. The length of a tuple depends on its outer structure,
  not on whether its elements are mutable.
- Supported built-in arithmetic and comparisons may compose known values, but
  require exact operand types and an operation-specific exception rule. A
  division, conversion, or shift is not total merely because its inputs are
  stable. Unsupported operations produce an unknown result.

This catalogue specifies semantics, not a requirement to call these operations
while linting. Every operation entry must describe its input evidence, state
reads, possible effects and exceptions, result kind, identity behaviour, and
cost class. Do not recognize a function or method by spelling alone.

Literal-origin bindings and supported exact built-in results can establish type
facts. A resolved built-in `range` with proven exact integer arguments can
establish exact integer loop targets and bounded trip-count facts without
executing the iterable. Other iterator shapes need their own reviewed contract.
An annotation, `Final`, protocol, class name, or `isinstance` check alone
cannot establish an exact runtime built-in type or immutability. User-defined
subclasses, arbitrary attributes, properties, overloaded operators, and unknown
calls remain unsupported expression dependencies. A resolved builtin name must
also remain unshadowed along the relevant paths.

Do not add a user-configurable pure-function allowlist in the initial release.
A later extension would need explicit exception, result-sharing, dependency,
and cost contracts, not merely a list of qualified names marked “pure”.

### 5. Binding, mutation, and scope semantics

Track bindings by lexical identity, not just identifier text. All reaching
definitions relevant to a dependency must support the same required facts;
ambiguous inference or a possibly unbound local suppresses the candidate.

Account for writes from ordinary, chained, unpacking, annotated, and augmented
assignments; assignment expressions; deletion; loop targets; imports; exception
and context-manager targets; pattern captures; and definitions. An annotation
without a value is not an assignment of a runtime value. Attribute and subscript
writes affect objects, not merely the spelling of a base name.

Track simple aliases where needed to invalidate facts. Distinguish changing a
binding from mutating the object it references. Unknown calls can mutate
reachable objects and captured cells, including through aliases or closures.
Unrelated unknown calls need not invalidate an uncaptured local exact immutable
value, but an unknown consumer of a candidate result prevents a reuse claim.

The initial rule does not report candidates that depend on mutable state,
global bindings, nonlocal cells, or captured local dependencies. This
restriction avoids requiring general alias analysis to make the first release
useful. It must not silently relax when inference becomes difficult.

Aggregate writes and effects from nested loops into the enclosing loop summary.
An inner loop is not an isolated island of state. Analyse nested function bodies
in their own execution scope, not as if their statements execute at definition
time. Definition-time defaults and decorators, and class-body execution, still
have runtime effects; conservatively treat unsupported cases as unknown.
Comprehension targets likewise do not become bindings in the enclosing loop.

### 6. Loop and control-flow semantics

The first implementation reports expressions in synchronous `for` and `while`
bodies inside functions. Inspect loop headers for dependencies and effects, but
do not report expressions in headers or loop `else` suites. Module and class
body loops, comprehension loops, generator expressions, and `async for` are
outside the initial reporting scope. A candidate in a loop containing an
`await`, `yield`, or `yield from` remains silent across that suspension
boundary.

A source-level assignment before a `for` statement precedes evaluation of the
iterable, iterator construction, and the first iteration. Moving a computation
there must account for those operations, not just statements in the body.
Similarly, a `while` test runs before each body entry and may itself mutate
state. Python's loop and exception semantics define these boundaries.[^6]

For the initial rule, require an expression that executes unconditionally on
body entry, before any statement or earlier subexpression that might exit,
raise, or perform an unknown effect. Reject candidates beneath conditional
branches, short-circuit operands, conditional-expression arms, exception
handlers, and nested context-manager or cleanup regions. Do not move a candidate
across a change in handler or cleanup context. A surrounding handler that
contains both the loop and the proposed binding is not itself such a change.

Require the candidate to terminate and have no ordinary exception for the
established input facts. Non-empty input alone does not justify moving a
possibly raising expression past iterator setup or preceding effects. Empty
loops and loops that exit before reaching an expression must retain their
original behaviour; do not introduce eager division, lookup, conversion, or
resource acquisition on those paths.

Each occurrence belongs to its nearest enclosing loop in the same execution
scope, and that loop must be supported. Never skip an unsupported loop to target
an outer one. Do not issue additional outer-loop diagnostics for the same
occurrence. Analyse inner loops separately, with their current enclosing
bindings, and reconsider further movement only on a subsequent lint run after
an actual edit.

### 7. Diagnostic selection

Select the largest expression at an occurrence that satisfies all four
predicates and whose replacement has safe uses. A variant parent can contain an
invariant child. An unsafe parent does not automatically make every child
unsafe, but the child's consumers still need the reuse check.

Emit at most one diagnostic for a selected source occurrence. Suppress nested
findings already covered by that diagnostic. Distinct occurrences may each
report; identical expression text does not establish interchangeable scope or
placement. Output order must follow source order and must not depend on AST
traversal accidents, previous modules, or worker count.

Never select an entire `if` statement, `print` call, mutation, assignment, or
loop merely because a contained condition or argument is invariant. Removing
repeated computation must not remove repeated actions.

### 8. Profitability policy

Use structural cost classes rather than fabricated timings. The initial
threshold requires at least one supported string transform that scans its
input. Bare literals, name reads, constant-size lookups, standalone `len`, and
cheap scalar arithmetic do not qualify. Combining only trivial operations must
not manufacture an expensive classification. Exclude expressions already known
to be compile-time constants without executing arbitrary constant expressions.

Suppress findings for loops provably limited to zero or one relevant execution.
An unknown trip count does not prove repeated work at runtime; wording remains
advisory. Even an eligible transform over a short string may not repay the
extra binding. Cost policy is a noise filter, not a speed-up guarantee.

Widening the operation catalogue or enabling the rule by default requires
measured examples from representative df12 workloads. Benchmark complete
original and manually refactored functions on the interpreter configurations
actually used, including the configured PyPy lane where relevant. Do not assume
that CPython and PyPy optimize the same source shapes identically.

### 9. Independent illustrative examples

The following new examples illustrate the proposal, not Perflint behaviour or
an implemented checker. They must become regression fixtures when implemented.

This expression qualifies: the exact string is stable, the transform is total
within the model, its intermediate feeds resolved `len`, and the resulting
integer feeds known integer arithmetic. Select `len(label.casefold())`, not the
multiplication that also depends on `weight`:

```python
def weighted_label_size() -> int:
    label = "Customer Reference"
    total = 0
    for weight in range(64):
        total += len(label.casefold()) * weight
    return total
```

An alias can mutate an object without rebinding its original name. The following
loop must not produce advice to cache `len(values)`. It is also below the
initial cost threshold; mutation tests must exercise the invariance predicate
directly so that the cost filter cannot hide a broken mutation analysis:

```python
def observe_growth() -> list[int]:
    values = [5]
    alias = values
    lengths = []
    for _ in range(3):
        lengths.append(len(values))
        alias.append(8)
    return lengths
```

Stable operands do not make eager evaluation safe. For an empty input, this
function does not divide at all. Moving the division before the loop would
introduce a failure when `divisor` is zero:

```python
def scaled_values(items: tuple[int, ...], divisor: int) -> list[float]:
    results = []
    for item in items:
        results.append(item * (12 / divisor))
    return results
```

Equal initial contents do not make freshly allocated objects interchangeable.
Moving `[7]` before this loop would replace distinct lists with shared state:

```python
def independent_rows() -> list[list[int]]:
    rows = []
    for _ in range(3):
        rows.append([7])
    rows[0].append(9)
    return rows
```

### 10. Analysis architecture and resource bounds

Keep the Pylint adapter thin. Separate scope and binding evidence, loop write
and effect summaries, expression facts, and final diagnostic selection into
small components only where those boundaries earn their complexity. Reuse
existing policy-neutral binding helpers after checking their contracts; do not
weaken another checker's ambiguity rules to force reuse.

Compute reusable summaries once per execution scope and cache expression facts
within the module. Propagate nested effects without rescanning every subtree
for every name. Any fixed-point computation must have a monotone domain and an
explicit termination bound. Exceeding an inference or analysis budget yields
unknown evidence and no recommendation, never optimistic fallback.

A minimal evidence record needs dependency identities, mutation or escape
uncertainty, supported operation identity, totality, result-sharing safety,
placement constraints, and cost class. This is a checker-specific analysis
boundary, not a new general-purpose optimizer framework.

Clear module state between modules and keep disabled-message overhead minimal.
Never import or execute the inspected application, mutate its syntax tree, read
its environment to resolve values, or perform network access. Preserve the
package's existing Pylint compatibility boundary; widening it is separate work.

## Requirements

### Functional and safety requirements

- Implement the predicates and conservative exclusions above independently.
- Report only supported expression occurrences with valid source spans.
- Preserve ordinary Pylint activation, suppression, confidence, and reporting.
- Keep the initial rule opt-in, with no automatic fixes or custom purity list.
- Preserve Perflint attribution in the eventual rule documentation, while
  clearly identifying the independent implementation and semantic differences.

### Verification requirements

Test safety properties directly as well as through the final diagnostic:

- Example tests must cover supported positive cases, largest-expression
  selection, shadowed built-ins, exact types versus subclasses, ambiguous
  bindings, aliases, closures, every write form, and nested-loop writes.
- Control-flow tests must cover empty loops, single iterations, early exits,
  `for` and `while` header effects, exceptions, handlers, cleanup, conditional
  evaluation, suspension, and definitions with execution-time effects.
- Identity tests must cover mutable allocation, immutable results escaping to
  unknown consumers, and safe containment within known value-only consumers.
- Property tests must establish alpha-renaming invariance, diagnostic
  uniqueness, scope isolation, and monotonic conservatism: weakening a proof
  fact to unknown cannot turn rejection into acceptance. Adding a relevant
  write, escape, or effect cannot make that candidate eligible.
- Differential tests must generate a bounded, supported source language and
  compare original and test-only transformed programs. Compare returned values,
  ordinary exceptions, action traces, and observable sharing across zero, one,
  and multiple iterations. Apply time and resource bounds to generated runs.
- Integration tests must exercise plugin loading, only-this-message activation,
  disabled-by-default behaviour, local suppression, repeated registration, and
  serial versus multi-worker reporting with the same source occurrences.

The differential transformation belongs only to the test harness. Passing it
provides evidence within the generated language, not a proof for arbitrary
Python. CrossHair may check small pure decision kernels where useful; it must
not become a prerequisite for claiming whole-program correctness.

Record analysis time and memory on deep and wide synthetic syntax trees and a
representative repository corpus. Assert bounded work or growth relationships,
not brittle wall-clock constants. Review candidate precision, practical value,
and Pylint overhead separately; a high detection count is not a success metric.

## Compatibility and migration

The documentation PR changes no runtime behaviour. After acceptance, implement
the narrow checker and its tests, then document the shipped interface in the
users' and developers' guides and update the message inventory. Allocate the
final message number at that point and record substantive accepted decisions
in an architectural decision record.

Loading `df12_python_lints` must not enable the new message implicitly. Existing
consumers need no configuration change unless they choose to evaluate it. A
broad explicit Pylint selection such as enabling all messages may include it;
the release notes must distinguish that from the default-disabled guarantee.

Pilot explicit activation in representative repositories. Manually classify
findings by semantic safety and practical benefit, and benchmark useful
refactors. A future change to default enablement or a broader semantic catalogue
requires its own review and migration note. Do not automatically add blanket
suppressions or refactor consumers during adoption.

Perflint W8201 remains a separate message. The plugin must not require Perflint
or silently disable it when both plugins load; projects that enable both may
see overlapping advice and should choose their policy explicitly.

## Alternatives considered

### Import the existing Perflint checker

This offers the fastest route to its established diagnostic behaviour, but does
not supply the stronger movement, sharing, and cost contracts proposed here.
Reject this option for the initial implementation. Preserve conceptual credit
without importing upstream code or pretending to implement a drop-in clone.

### Report syntactic invariance as an aggressive advisory

This would find more opportunities but would require every recipient to finish
the safety analysis. Reject it for the first release because the diagnostic
would invite unsafe mechanical edits. A separately named exploratory mode could
be proposed later; it must not dilute this message's contract.

### Implement general effect inference or automatic fixes

These could increase coverage but would substantially enlarge the trusted
analysis and verification surface. Defer both. A small operation catalogue and
explicit negative cases provide a reviewable starting point.

### Rely only on profiling and manual review

Profiling remains necessary to establish a speed-up. It does not replace an
inexpensive reminder about a supported repeated computation during development.
Use the lint to select candidates, not to replace measurement.

## Open questions

- Which repository corpus and interpreter configurations should gate expansion
  of the initial operation catalogue and any later default enablement?
- Which additional expensive operations justify a complete effects, totality,
  and result-sharing contract rather than a permissive purity assumption?
- Is the practical yield of the initial conservative subset sufficient to keep
  the rule, once its analysis overhead and review burden are measured?

These questions do not authorize relaxing the safety contract. Insufficient
useful findings are a reason to retain opt-in status, revise the proposal, or
reject the rule, rather than manufacture confidence from missing evidence.

## Recommendation

Adopt the semantics as the basis for a small, independently implemented Pylint
checker. Begin with the narrow string-transform subset, conservative silence,
explicit activation, and no automatic fixes. Expand only when regression
coverage and workload evidence justify the additional analysis.

## References and attribution

[^1]: Anthony Shaw, [Perflint W8201 documentation](https://github.com/tonybaloney/perflint/blob/22f831509bc7765ce272ad6fcb99398d86a26a52/README.md#w8201-loop-invariant-statement-loop-invariant-statement).
    Credit applies to the lint's purpose, loop-invariant expression and
    subexpression semantics, and recognition of mutation as an obstacle.
    The stricter movement, identity, cost, and opt-in contracts are this RFC's
    proposed departures. Perflint's [licence](https://github.com/tonybaloney/perflint/blob/22f831509bc7765ce272ad6fcb99398d86a26a52/LICENSE)
    identifies Anthony Shaw as copyright holder. This proposal includes no
    upstream implementation or test material.
[^2]: The repository's [message inventory](../../README.md) and
    [package metadata](../../pyproject.toml), inspected at
    `4a85457d862fe62f6fb9590a6d77cfcc23ab509c`.
[^3]: [ADR 001: Conservative dataclass layout analysis](../adrs/adr-0001-conservative-dataclass-layout-analysis.md).
[^4]: Pylint, [How to write a checker](https://pylint.readthedocs.io/en/stable/development_guide/how_tos/custom_checkers.html).
[^5]: Python language reference, [Objects, values and types](https://docs.python.org/3/reference/datamodel.html#objects-values-and-types).
[^6]: Python language reference, [Compound statements](https://docs.python.org/3/reference/compound_stmts.html),
    especially the `for`, `while`, and `try` statement definitions.
