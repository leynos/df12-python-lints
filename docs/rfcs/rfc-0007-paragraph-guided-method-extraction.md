# RFC 0007: Paragraph-guided method extraction

## Preamble

- **RFC number:** 0007
- **Status:** Proposed
- **Created:** 2026-11-14

## Summary

Add an opt-in Pylint diagnostic, provisionally named
`consider-paragraph-extraction`, for a contiguous sequence that computes one
value through several temporary bindings. Report the exact candidate, its
inputs, and its surviving output after conservative local analysis. Developers
choose whether a helper improves the design, its name, and its destination.

The [shared refactoring lint contract](../refactoring-lint-contract.md) governs
registration, allocation, inference, determinism, and rollout. Version one
supplies diagnostics without extraction edits. Its evidence establishes the
stated local conditions; it does not prove observational equivalence after
introducing a function call.

## Problem

Sourcery's Extract Method, Class Extract Method, and Extract Duplicate Method
identify opportunities to give a computation a name.[^1] A useful residual
diagnostic must identify a bounded computation rather than infer a design
problem from function length alone. Conversely, introducing a helper for every
run of assignments adds indirection without establishing a useful abstraction.

This proposal borrows catalogue intent from Sourcery and the paragraph model
from Whitaker. It proposes an independent Python design and copies no
implementation code.

## Current state

At df12 commit `4a85457d862fe62f6fb9590a6d77cfcc23ab509c`, the registered
checkers contain no paragraph-extraction analysis. Existing R9104 and R9110
discourage trivial attribute and forwarding wrappers; the new rule must not
recommend those shapes.[^2] The `df12-duplication` command delegates clone
detection to pinned `nose` releases.[^3] Pylint R0801 detects similar lines
across files.[^4] These duplication signals do not establish that an individual
sequence has a small, coherent input/output boundary.

Whitaker commit `94c899622c5cfd6a7049d51ddfcff5ac35358341` contains three
distinct kinds of evidence:

- **Implemented model:** ordered statement and expression shapes, callee
  identities, explicit unknown states, and local slots assigned by first
  appearance. A renamed local can retain the same fingerprint.[^5]
- **Implemented tests:** unit, property, and behaviour tests cover renaming,
  structural differences, slot ordering, and repeatability.[^6]
- **Planned detector:** the `single_binding_paragraph` design walks backwards
  from a sink binding, including contributing statements until the first
  non-contributor. It proposes 3–8 statements, at most three external inputs,
  and rejection of intermediate reuse and unsupported control flow. Roadmap
  items 8.3.1–8.3.4 remain unchecked.[^7]

The implemented fingerprints neither discover source paragraphs nor establish
semantic equivalence. Their coarse shapes omit details such as literal values.
Whitaker's planned detector uses statement dependencies, not blank-line
splitting. Python can adopt that source-local boundary without treating layout
or fingerprint equality as proof.

## Goals and non-goals

Identify a locally explainable extraction candidate, account for every input
and later use, and keep uncertain cases quiet. Retain useful temporary names
when no distinct computation emerges.

Version one excludes clone grouping, whole-program inference, stateful method
extraction, generated helper names, destination selection, and automatic
rewriting. It does not replace the duplication gate or complexity diagnostics.

## Proposed design

### Candidate boundary and dependency analysis

Analyse direct statements in synchronous function and method bodies. Within
each body, consider a simple assignment to a fresh local name as a possible
sink. The initial supported statement is `name = expression`; reject chained
assignment, unpacking, annotations, and augmented assignment inside candidates.

For each sink:

1. Initialize the required bindings from the sink expression's local reads.
2. Walk backwards through immediately preceding statements, up to the maximum
   length. Include a statement only when its fresh target supplies a required
   binding. Remove that binding and add its initializer's local reads.
3. Stop at the first non-contributor or unsupported statement. Never skip an
   intervening statement to assemble a more attractive candidate.
4. Resolve the remaining reads as inputs, each definitely bound at entry.
   Candidate definitions must not overwrite parameters or earlier bindings.
5. Require the sink to be the sole candidate-defined name used afterwards.
   Reject any later read of an intermediate, including reads inside nested
   scopes and exception handlers. Version one conservatively rejects even reads
   after a later rebinding; it need not prove those harmless.
6. Apply the effect and scope rules below, then the size and input limits.

Proposed defaults are a minimum of three statements, a maximum of eight, and at
most three inputs. Count logical statements, not physical lines. These are
trial thresholds, not empirical claims about ideal helper size. Reject a
candidate when removing its function's docstring, proven entry guards, and
final return leaves only that candidate: the computation already has a name.

Build binding and use summaries once per function. Bound backward walks by the
configured maximum and cap inference work through the shared contract.
Incomplete summaries suppress findings. For overlapping candidates, retain the
longest supported interval, then the earliest start and end positions; emit
only non-overlapping intervals in source order.

### Effects, scope, and supported expressions

Python bindings and closures operate at function scope, while extracted code
would execute in another frame.[^8] The candidate model must therefore track
bindings rather than spellings and distinguish reads from writes.

Version one accepts string literals, proven exact-string local reads, and a
closed set of non-mutating operations: `strip()`, `lower()`, and
`replace(old, new)` with literal string arguments. Require at least one of
these supported computations; a sequence of aliases alone supplies no
extraction candidate. Record receiver type, argument restrictions, return type,
exceptions, allocation, mutation, callbacks, and identity for each supported
operation. Every other call or operator suppresses the candidate until a
separately reviewed model supports it.

Every intermediate binding whose caller-held reference would disappear must
hold an established exact `str`. These immutable scalar values have no instance
finalizer. Reject opaque objects, mutable values, subclasses, and containers,
including immutable containers that retain unknown objects. A later extension
needs an explicit non-finalization proof for each additional value domain.
Merely proving that a name has no later reads is insufficient: its reference
can keep an object alive.[^9]

The following counterexample must remain silent:

```python
def keep_aliases(value, events):
    first = value
    second = first
    result = second
    events.append(result is value)
    del value, result
    events.append("after deletion")
```

Pass a fresh object whose finalizer appends `"released"` to `events`. On
CPython, the function records `[True, "after deletion", "released"]` because
`first` and `second` retain the object until the function exits. Moving the
three assignments into a helper that returns `result` instead records
`[True, "released", "after deletion"]`. Finalization timing varies between
implementations; the changed reachability already defeats the required lifetime
proof. The opaque-value and alias-only exclusions both reject this paragraph.

Literal provenance or a dominating exact-type guard can establish an exact
string. Resolve `type` and `str` to built-ins, and require the rejection branch
to exit. Reject ambiguous inference, subclasses, shadowed built-ins, and
intervening operations that invalidate the proof. An annotation or an
`isinstance` test alone does not establish exact built-in behaviour.

Reject attribute or subscript writes, mutation through aliases, resource
operations, and arbitrary property reads. Reject candidates containing control
flow, comprehensions, assignment expressions, imports, nested definitions,
`yield`, `await`, `return`, `raise`, or `del`. Candidates inside loops,
`try`/`except`/`finally`, or `with` suites remain outside version one.

Suppress the containing function when `global`, `nonlocal`, dynamic execution,
known frame inspection, or reflective local access prevents a complete local
account. Check nested scopes for captured candidate bindings. Class-cell access
and zero-argument `super()` also suppress candidates. Unknown evidence never
becomes an assumed absence of effects.

The lifetime conditions are eligibility requirements, not assumptions deferred
to human review. The advisory boundary still leaves the helper's binding,
signature, and destination unspecified; those choices require separate review.
New frames also affect tracebacks and tracing, outside the shared observation
model. The diagnostic must not certify an unspecified complete extraction as
semantics-preserving or automatically safe.

### Source context and diagnostic

Blank lines and leading comments can explain the author's intended paragraph.
They cannot admit a failed candidate. Do not infer a helper name from a comment
or split a multiline expression at an empty physical line. The initial checker
requires no token-based paragraph segmentation.

The following design example has one candidate: the three assignments from
`trimmed` through `key`. The exact-type guard establishes the input evidence;
the checksum and publication remain separate computations.

```python
import hashlib


def publish_artifact(component, payload, publish):
    if type(component) is not str:
        raise TypeError("component must be an exact string")

    # Normalize the artefact key.
    trimmed = component.strip()
    separated = trimmed.replace(" ", "-")
    key = separated.lower()

    digest = hashlib.sha256(payload).hexdigest()
    publish(key, payload, digest)
```

Report the first assignment through the sink, with this proposed wording:
“Consider extracting this 3-statement computation of 'key'; input:
'component'.” Include input names in first-use order. Attach no replacement
text or suggested method signature. In a class method, the same analysis may
identify a computation that belongs in a function; the diagnostic deliberately
leaves that decision to review.

## Requirements and test acceptance

The implementation must keep candidate discovery separate from effect and scope
confirmation, so each rejected case has a testable reason. Documented inference
failures produce unknown evidence. Programming errors retain the error
behaviour required by the shared contract.

| Case                                                                  | Required outcome                                                 |
| --------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Published example with resolved built-ins                             | One finding over the three assignments; one input and one output |
| Same example without the exact-type guard                             | No finding, including when `component` has a `str` annotation    |
| Guard has a continuing rejection branch or unstable built-in binding  | No finding                                                       |
| Later use or capture of `trimmed`                                     | No finding                                                       |
| A logging call between contributing assignments                       | No merged candidate across that call                             |
| Custom receiver, property, mutation, or unsupported operator          | No finding                                                       |
| Opaque or mutable intermediate whose removal can advance finalization | No finding; retain the alias-lifetime counterexample             |
| Exact-string aliases without a supported computation                  | No finding                                                       |
| Two inputs with the same spelling in different scopes                 | No conflation of bindings                                        |
| Too few statements, too many inputs, or oversized candidate           | No finding outside configured limits                             |
| Whitespace, comments, or renamed locals change                        | Same decision and corresponding source span                      |
| Entire helper body or trivial forwarding wrapper                      | No finding                                                       |
| Overlapping candidates and repeated parallel runs                     | Identical non-overlapping diagnostics and ordering               |

_Table 1: Acceptance cases for paragraph extraction diagnostics._

Unit tests cover summaries and boundary decisions. Property tests vary local
names, formatting, and rejected expression shapes. Behaviour tests run the
opt-in plugin through Pylint and assert spans, evidence, and clean default
behaviour. Parse the published example on Python 3.12 and supported later
versions; execution alone does not validate detection. Review every finding in
a declared corpus and record useful, redundant, and incorrect advice before
expanding the expression model or changing defaults.

## Compatibility and migration

The [shared contract](../refactoring-lint-contract.md) makes adoption explicit.
Existing configurations and the duplication command retain their behaviour.
Python 3.12 remains the floor. New syntax or astroid nodes outside the
supported model suppress candidates until covered by tests; annotations
introduced by newer Python versions never silently widen the proof boundary.

## Alternatives considered

Length thresholds identify large functions but supply no extraction boundary.
Blank-line splitting follows formatting without checking dependencies. Clone
fingerprints identify resemblance while missing a unique computation and cannot
prove input/output compatibility. Unrestricted dependence slicing has greater
recall but requires alias, control-flow, and scope reasoning beyond this first
release. The bounded contiguous model supplies a specific, reviewable span with
predictable rejection rules.

## Open questions

- Does the trial corpus justify a three-statement minimum, or does four
  produce more useful suggestions?
- Which additional exact built-in operations add useful coverage without
  turning the checker into a general effect analyser?
- Should a later duplication report cross-link independently validated
  candidates without introducing duplicate diagnostics?

## Recommendation

Accept the opt-in diagnostic design and its narrow first expression model.
Evaluate the usefulness of the reported computations before broadening scope.
Keep Whitaker's implemented fingerprinting, its planned detector, and the
Python-specific extraction conditions distinct in documentation and tests.

## References

[^1]: Sourcery,
      [Extract Method](https://docs.sourcery.ai/reference/refactorings/python/extract-method/),
    [Class Extract Method](https://docs.sourcery.ai/reference/refactorings/python/class-extract-method/),
    and [Extract Duplicate Method](https://docs.sourcery.ai/reference/refactorings/python/extract-duplicate-method/).
    Catalogue intent only; accessed 2026-11-14.
[^2]: df12-python-lints at `4a85457d862fe62f6fb9590a6d77cfcc23ab509c`,
    [registration](https://github.com/leynos/df12-python-lints/blob/4a85457d862fe62f6fb9590a6d77cfcc23ab509c/df12_python_lints/__init__.py)
    and [trivial-wrapper checks](https://github.com/leynos/df12-python-lints/blob/4a85457d862fe62f6fb9590a6d77cfcc23ab509c/df12_python_lints/wrappers.py).
[^3]: df12-python-lints,
      [duplication adapter](https://github.com/leynos/df12-python-lints/blob/4a85457d862fe62f6fb9590a6d77cfcc23ab509c/df12_python_lints/duplication/detector.py)
    and [ADR 0002](../adrs/adr-0002-df12-duplication-command.md).
[^4]: Pylint,
      [duplicate-code / R0801](https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/duplicate-code.html),
    accessed 2026-11-14.
[^5]: Whitaker,
      [paragraph fingerprint model](https://github.com/leynos/whitaker/blob/94c899622c5cfd6a7049d51ddfcff5ac35358341/common/src/rstest/paragraph_fingerprint.rs).
[^6]: Whitaker,
      [unit tests](https://github.com/leynos/whitaker/blob/94c899622c5cfd6a7049d51ddfcff5ac35358341/common/src/rstest/tests/fingerprint.rs),
    [property tests](https://github.com/leynos/whitaker/blob/94c899622c5cfd6a7049d51ddfcff5ac35358341/common/src/rstest/tests/fingerprint_props.rs),
    and [behaviour scenarios](https://github.com/leynos/whitaker/blob/94c899622c5cfd6a7049d51ddfcff5ac35358341/common/tests/features/rstest_fingerprint.feature).
[^7]: Whitaker,
      [single-binding paragraph design](https://github.com/leynos/whitaker/blob/94c899622c5cfd6a7049d51ddfcff5ac35358341/docs/lints-for-rstest-fixtures-and-test-hygiene.md#lint-b-single-binding-paragraph-detection)
    and [roadmap section 8.3](https://github.com/leynos/whitaker/blob/94c899622c5cfd6a7049d51ddfcff5ac35358341/docs/roadmap.md#83-single_binding_paragraph-lint).
[^8]: Python 3.12,
      [execution model](https://docs.python.org/3.12/reference/executionmodel.html),
    especially naming, binding, and execution frames.
[^9]: Python 3.12,
      [objects, reachability, and finalization](https://docs.python.org/3.12/reference/datamodel.html#objects-values-and-types),
    including the distinction between CPython reference counting and portable
    garbage-collection guarantees.
