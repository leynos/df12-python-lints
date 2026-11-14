# RFC 0008: Dictionary construction and filtering

## Preamble

- **RFC number:** 0008
- **Status:** Proposed
- **Created:** 2026-11-14

## Summary

Propose independently selectable diagnostics for dictionary union construction
and replacement of an isolated deletion loop with a filtered dictionary
comprehension. Both require evidence about exact dictionary semantics, aliases,
evaluation order, and exceptional paths. A type annotation alone cannot supply
that evidence.

The [shared refactoring lint contract](../refactoring-lint-contract.md) governs
activation, reporting, and uncertainty. Version one provides no automatic
fixes. Sourcery's dictionary-union and deletion-comprehension refactorings
supply semantic inspiration; this proposal copies no implementation code or
examples.[^1]

## Problem

Configuration assembly often obscures a simple right-biased merge behind a
temporary copy and update. Conversely, a loop that deletes selected entries may
describe a new filtered value more clearly as a comprehension.

Neither rewrite follows from syntax alone. Dictionary union differs from
general mapping unpacking; replacing mutation with rebinding changes object
identity and what existing aliases observe. An exception partway through a
deletion loop can expose partial mutation, while a failed comprehension leaves
the original binding intact. A diagnostic must establish the relevant contract
before preferring a shorter expression.

## Current state

Pylint's optional `C3401` (`dict-init-mutate`), loaded through
`pylint.extensions.dict_init_mutate`, already covers empty dictionary
initialization followed by known-key assignments.[^2] Ruff `PERF403` covers
dictionary construction through a population loop.[^3] These remain upstream
responsibilities, including their documented limitations. Single-key `update`
simplification belongs to RFC 0003.

Python supports dictionary union throughout the package's Python 3.12 baseline.
For ordinary dictionaries, the right operand supplies a duplicate key's final
value; updating an existing key does not move its insertion position.[^4] This
language capability does not establish that an arbitrary `Mapping`, dictionary
subclass, or inferred instance has those exact operational semantics.

The package has conservative import-binding and dataclass-specific state
helpers, but no general escape or dictionary-content analysis. Any such
analysis introduced here must remain explicitly bounded and independently
tested.[^5]

## Goals and non-goals

The goal is to expose construction of a new mapping value when its semantics
are established. Proposed symbols are `prefer-dict-union-construction` and
`prefer-isolated-dict-filter`; numeric identifiers remain unallocated.

General in-place filtering, preservation of custom mapping subclasses,
arbitrary mapping protocols, nested merge semantics, and automatic
configuration migration are outside scope. The proposal does not claim that
union always improves performance or that replacing every mutation with a
comprehension improves code.

## Proposed design

### Exact dictionary evidence

The first implementation must derive an exact builtin dictionary from local
construction and reaching-definition evidence. Supported origins are dictionary
literals and operations with reviewed exact-result contracts. An annotation, an
inferred `ClassDef`, or a name spelled `dict` is insufficient. Resolve any
builtin constructor through active lexical bindings, including shadowing.

Require simple, definitely bound local operands and no intervening mutation
that invalidates content facts. Initially support keys proven to be exact
strings. This avoids silently changing arbitrary `__hash__` or `__eq__` calls
during construction. Unknown keys, subclasses, unpacking sources, ambiguous
reaching definitions, and unsupported provenance suppress advice.

Represent evidence explicitly: exact container kind, known key domain, origin,
aliases and escapes, relevant writes, and ordinary exception uncertainty.
Unknown evidence must never become an affirmative fact through a fallback.

### Union construction

Recognize these bounded forms only after applying the evidence above:

| Original shape                                      | Suggested shape | Additional requirement                                      |
| --------------------------------------------------- | --------------- | ----------------------------------------------------------- |
| `{**left, **right}`                                 | `left \| right` | Both operands are simple local names                        |
| Fresh `left.copy()` followed by one `update(right)` | `left \| right` | Intermediate target has no observation or escape            |
| `dict(left) \| right`                               | `left \| right` | Constructor is the unshadowed builtin and copy is redundant |

_Table 1: Initial union-construction shapes and their additional obligations._

The following independent example illustrates the copy-and-update candidate:

```python
def request_options():
    defaults = {"timeout": 5, "attempts": 2}
    overrides = {"timeout": 12}
    options = defaults.copy()
    options.update(overrides)
    return options
```

The preferred construction retains both sources and their key order:

```python
def request_options():
    defaults = {"timeout": 5, "attempts": 2}
    overrides = {"timeout": 12}
    options = defaults | overrides
    return options
```

For the copy-and-update form, require immediate adjacency, a local's first
assignment, and a fresh target that neither source references. Reject a target
captured by a closure, exposed through a view, stored elsewhere, or observed by
a call. No handler or cleanup path may observe an intermediate target state.
Preserve any later use of the resulting target; the diagnostic must not also
inline a return or erase a meaningful local name.

Restrict source expressions to stable local reads because unpacking the first
mapping occurs before evaluating the second expression, whereas binary union
evaluates both operands before performing the merge. Calls or properties in
either position require a separate proof and remain outside version one.

Exclude longer copy/update or union chains. Their intermediate allocations,
alias exposure, and evaluation boundaries can differ, and repeated unions can
copy a growing mapping more than once. Do not recommend `|=` as a substitute
for new-value construction: it has a different mutation and operand contract.
An existing alias to either source is harmless only when the operation leaves
that source untouched and the analysis proves no crossed effect can mutate it.

### Isolated filtered rebuild

Recognize a fresh local dictionary followed by a loop over its explicit
`copy()`, containing only a supported predicate and deletion of the current
key. The proposed comprehension iterates the original dictionary's `items()`,
retains the original key and value, and negates the deletion predicate without
changing its meaning or evaluation order.

For version one, the predicate may only test an exact string key against a
stable local exact set or frozen set of exact strings. Establish finite
contents from supported local construction. Require values with established
exact `NoneType`, `bool`, `int`, `float`, `complex`, `str`, or `bytes` types so
deletion cannot invoke an instance finalizer. User callbacks, arbitrary
equality, unknown containers, and predicates that may raise remain outside
scope.

The following example retains only recognized settings:

```python
def recognized_settings():
    settings = {"colour": "teal", "debug": "off", "obsolete": "yes"}
    recognized = {"colour", "debug"}
    for key in settings.copy():
        if key not in recognized:
            del settings[key]
    return settings
```

The corresponding new-value construction preserves survivor order:

```python
def recognized_settings():
    settings = {"colour": "teal", "debug": "off", "obsolete": "yes"}
    recognized = {"colour", "debug"}
    settings = {
        key: value
        for key, value in settings.items()
        if key in recognized
    }
    return settings
```

The target must remain unaliased and unobserved from its fresh construction
until replacement. Reject parameter dictionaries, globals, nonlocals, captured
cells, stored references, self-referential contents, retained views or
iterators, identity observations, and passing the target to unknown code.
Annotations cannot establish this ownership property. A previous alias that is
later deleted still requires a proof that no observation or escape occurred;
version one should reject it.

Require the original loop variable to be previously unbound and dead after the
loop, including closure capture and exception paths. This avoids retaining a
previous value with observable finalization. Comprehensions do not preserve the
loop variable's outer binding.[^6] Reject `break`, `continue`, loop `else`,
suspension, nested loops, extra writes, and extra body statements. Do not
replace mutation with `clear()` plus `update()` to retain identity: that
creates a different exception and observation contract.

Predicate totality and guaranteed key presence matter even without a handler
beside the loop. A caller can catch an exception and inspect an escaped object;
the isolation and effect requirements must cover the complete supported region.
The shared analysis model defines excluded interpreter instrumentation and
resource-exhaustion effects; ordinary application exceptions remain relevant.

### Implementation boundaries

Keep recognition, dictionary evidence, and final diagnostic decisions separate.
Reuse lexical lookup patterns from `_dataclass_decorators.py` only through a
policy-neutral extraction that preserves its strict ambiguity contract. Do not
reuse dataclass instance-state helpers as if they tracked arbitrary containers.

Cache proposed content and escape summaries once per function, with explicit
budgets and conservative cycle handling. Record the proof supporting each
candidate so tests can exercise it independently of message selection. Report
one maximal recognized construction, anchored to its first assignment or
unpacking expression. Avoid overlapping reports with upstream construction
rules or the single-key update proposal.

## Requirements and acceptance

Positive tests must cover duplicate string keys, insertion order, empty
operands, survivor order, retained value identity, and each supported union
shape. Negative tests must cover custom mappings and subclasses, shadowed
constructors, custom hashing/equality, source calls, alias and view escape,
self-reference, target capture, live loop variables, throwing predicates,
partial mutation, and longer merge chains.

Differential tests must compare the original and test-only transformed programs
over bounded exact dictionaries. Compare ordered items, input non-mutation,
returned object relationships, visible traces, and ordinary exceptions. Include
aliasing and exception counterexamples as explicit rejection tests; checking
only final dictionary equality would miss the central risks.

Property tests must establish alpha-renaming invariance and monotonic refusal
when a known container or ownership fact becomes unknown. Integration tests
must exercise each symbol independently, explained suppression, and
deterministic serial/parallel output. Acceptance also requires analysis growth
measurements on large construction regions and a manually reviewed corpus of
useful findings.

## Compatibility and migration

The documentation change implements and enables nothing. Consumers may already
enable `C3401` or `PERF403`; their configuration can remain unchanged. After
acceptance, pilot union construction before filtered rebuilds because its
ownership obligations are smaller. Keep both messages opt-in under the shared
contract and document their distinct exclusions.

Python 3.12 already supplies every proposed target construct. Preserve the
package's Pylint compatibility range. Add any accepted evidence helper and its
reuse policy to the developer guide before other checkers depend on it.

## Alternatives considered

Keeping copy/update and deletion loops is a valid choice when their mutation
semantics matter. Recommending comprehensions solely from a `dict` annotation
would miss aliases, subclasses, and exception behaviour. General mapping
protocol inference would cost substantially more than the initial scope
justifies. Upstream ownership remains preferable where a matching diagnostic
already exists.

## Open questions

- Does the narrow filtered-rebuild subset produce enough practical findings to
  justify its ownership analysis?
- Which additional key or value domains have operation contracts strong enough
  to expand coverage without relying on implementation accidents?
- Should union advice distinguish a readability preference from removal of a
  demonstrably unnecessary intermediate copy in its final wording?

## Recommendation

Implement a small, exact-dictionary union diagnostic first. Retain filtered
rebuild as a separate candidate that ships only after alias, exception, and
loop-binding rejection tests establish its intended boundary.

[^1]: Sourcery's
      [dictionary union](https://docs.sourcery.ai/reference/refactorings/python/use-dictionary-union/),
    [copy/update union](https://docs.sourcery.ai/reference/refactorings/python/dict-assign-update-to-union/),
    [redundant union constructor](https://docs.sourcery.ai/reference/refactorings/python/remove-redundant-constructor-in-dict-union/),
    and [deletion comprehension](https://docs.sourcery.ai/reference/refactorings/python/del-comprehension/).
[^2]: Pylint
      [C3401](https://pylint.readthedocs.io/en/stable/user_guide/messages/convention/dict-init-mutate.html).
[^3]: Ruff
      [PERF403](https://docs.astral.sh/ruff/rules/manual-dict-comprehension/).
[^4]: Python's
      [dictionary operations](https://docs.python.org/3.12/library/stdtypes.html#mapping-types-dict)
    and [PEP 584](https://peps.python.org/pep-0584/).
[^5]: The [developer guide](../developers-guide.md) and
    [import-binding implementation](../../df12_python_lints/_dataclass_decorators.py).
[^6]: Python's
      [comprehension scope rules](https://docs.python.org/3.12/reference/expressions.html#displays-for-lists-sets-and-dictionaries).
