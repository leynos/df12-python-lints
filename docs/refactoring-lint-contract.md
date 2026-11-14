# Proposed refactoring lint contract

## Status and scope

- **Status:** Proposed; accompanies RFCs 0003–0011.
- **Created:** 2026-11-14.
- **Audience:** Checker implementers and design reviewers.
- **Baseline:** Python 3.12 or later; the existing `pylint>=3.3,<5`
  dependency range.

The nine RFCs propose opt-in Pylint diagnostics for refactorings that current
Ruff and bundled Pylint rules do not fully cover. This contract defines their
shared evidence, reporting, and verification requirements. It proposes no
implementation change. Future checkers report diagnostics; developers change
their programs by applying the recommended refactorings.

The source baseline is commit `4a85457d862fe62f6fb9590a6d77cfcc23ab509c`. The
plugin currently registers ten checkers and thirteen messages. Its helpers
cover particular syntax and binding questions; they do not supply a general
control-flow, liveness, alias, or effect analysis.[^1] An implementation must
add the minimum analysis its rule needs and demonstrate that analysis
independently.

## Proposal ownership

Each proposal owns the following candidate transformations. A cross-reference
delegates ownership; it does not introduce a second diagnostic.

| RFC                                                            | Candidate owner                                                                                                                             |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| [0003](rfcs/rfc-0003-local-intent-simplifications.md)          | Local intent improvements: min/max defaults, negative indices, string search and affixes, sized reductions, and one-key dictionary updates. |
| [0004](rfcs/rfc-0004-small-structural-cleanups.md)             | Small structural cleanup: compatible try suites, identical ordinary handlers, empty branches, and fresh list/set initialization.            |
| [0005](rfcs/rfc-0005-residual-idiom-refactorings.md)           | Residual generator, search, joining, explicit-length, and fallback idioms.                                                                  |
| [0006](rfcs/rfc-0006-branch-factoring.md)                      | Shared branch statements, repeated conditions, and guard placement.                                                                         |
| [0007](rfcs/rfc-0007-paragraph-guided-method-extraction.md)    | Paragraph-guided function and method extraction.                                                                                            |
| [0008](rfcs/rfc-0008-dictionary-construction-and-filtering.md) | Dictionary union, copying, and filtered reconstruction.                                                                                     |
| [0009](rfcs/rfc-0009-variable-placement.md)                    | Assignment movement, inlining, reuse, and repeated-read while conditions.                                                                   |
| [0010](rfcs/rfc-0010-numeric-and-logical-transformations.md)   | Numeric reductions and algebra, quotient/remainder pairs, and any/all duality.                                                              |
| [0011](rfcs/rfc-0011-de-morgan-transformations.md)             | De Morgan normalization of Boolean negation.                                                                                                |

_Table 1: Ownership within the proposed refactoring suite._

RFCs 0001 and 0002 already have published proposals in separate pull requests.
Their numbers remain reserved. RFC 0002 owns loop-invariant expression advice;
these proposals must coordinate analysis requirements with it without assuming
its implementation exists.[^2]

## Semantic evidence

### Evidence states

Every required fact has one of three outcomes: established, contradicted, or
unknown. A diagnostic requires all its eligibility facts to be established.
Contradicted or unknown facts suppress it. A type annotation, a suggestive
name, an attribute-chain match, or one successful Astroid inference result does
not establish runtime type, purity, non-aliasing, or absence of effects.

An exact built-in type means the value cannot be a subclass with overriding
behaviour. Establish it from a closed source-origin proof, a dominating exact
`type(value) is Builtin` guard with stable bindings, or a documented closed
model of a built-in operation. Resolve `type` and `Builtin` themselves to their
unshadowed built-ins. A plain `isinstance` guard does not exclude subclasses.
Join control-flow facts conservatively and invalidate facts on reassignment,
escape, or an unmodelled operation that can affect them.

The first implementation may support only literals and local reaching
definitions. Runtime guards are an extension requiring their own proof and
tests. A rule must state which evidence producers it actually supports; there
must be no silently optimistic fallback.

### Preserved observations

For the rule's supported input domain, the proposed replacement must preserve:

- Result values, relevant result types, input identities, and mutable aliases.
- Evaluation order and multiplicity of effectful expressions and truth tests.
- Mutation, alias visibility, iterator consumption, and short-circuit exits.
- Exception classes and the relative order of fallible operations.
- Bindings visible after the transformed region, including empty-loop paths.
- Control transfer, handler scope, cleanup, and suspension behaviour.

These obligations apply to each specified replacement. RFC 0007 instead reports
an extraction boundary without choosing a helper name, signature, or
destination. Its evidence must establish the stated effect, binding, and
lifetime conditions, but cannot certify an unspecified extraction. The
diagnostic must identify that limit explicitly.

Python evaluates an assignment's right-hand side before its targets. It also
returns operands from `and` and `or`; these details prevent several tempting
textual rewrites.[^3] Each RFC adds narrower exclusions for its candidates.

The model excludes timing, resource exhaustion, debugger frames, tracing,
code-object/source inspection, and implementation-dependent allocation or
interning of newly computed immutable values. Suppress a candidate when its
changed immutable result has a visible identity-sensitive consumer such as `is`
or `id`; do not claim preservation of numeric or string interning in unknown
callers. Rules that introduce a frame or remove bindings must nevertheless
reject visible reflective use such as `locals`, `eval`, `exec`, or frame
inspection in the affected scope. Concurrent mutation and external
monkey-patching cannot receive an unconditional equivalence guarantee. The
documentation must state those limits; a visible source path that introduces
either invalidates the relevant proof.

### Closed effect model

The initial safe-expression grammar contains scalar literals, definitely bound
local-name loads, and individually specified operations on established exact
built-ins. Scalar literals denote exact `NoneType`, `bool`, `int`, `float`,
`complex`, `str`, or `bytes` values. A container display requires an explicit
rule-specific model of its elements; the word "literal" alone does not admit
opaque references, calls, or unpacking inside a display. Each operation's model
states possible exceptions, allocation, mutation, callbacks, and result
identity. Attribute access, descriptors, unknown calls, arbitrary
subscriptions, and overloaded arithmetic are unknown unless a rule establishes
a narrower model.

Structural matching must distinguish literal payload types as well as values:
`True`, `1`, and `1.0` are different source constants despite comparing equal.

Purity alone is insufficient for movement: a pure expression may raise or
allocate a distinct mutable value. Movement and reuse therefore require
separate facts about totality on the supported domain and identity. A
definitely bound name load can be safe even when the object's type is unknown;
using that object in a truth test or operator needs further evidence.

Do not import or execute linted modules. Analysis uses source, tokens, and
bounded Astroid queries only. Catch documented inference failures at their
boundary and record an unknown result. Do not swallow checker programming
errors as if they were harmless inference misses.

## Analysis and implementation boundary

Reuse `_chains.py` for supported if-chain traversal and `_expressions.py` for
its existing syntactic/binding predicates. Neither helper proves effects. The
strict import-resolution and module-local caching patterns in the dataclass
checker provide precedents, not a ready-made refactoring engine. If multiple
implemented rules need the same proof, extract a policy-neutral helper with
direct tests; do not make all nine proposals depend on a general whole-program
analyser.[^1]

Each implementation must publish finite limits for nodes, inference results,
and candidate windows. Reaching a limit suppresses affected candidates and
cannot change an unknown fact to established. Cache only within one module
analysis and include scope, binding, and program-point context in keys, or
explicitly invalidate every dependent cached fact after a relevant write or
escape. Cross-module speculative execution and repository-wide clone searches
are outside the first release.

## Diagnostic contract

- Register accepted checkers through `df12_python_lints.register` and Pylint's
  normal checker interface. Use ordinary `add_message` reporting.[^4]
- Keep every new message disabled by default, independently enableable by
  symbolic name. Proposed names in RFCs are review identifiers; allocate unique
  numeric message IDs only in an implementation change after checking current
  and pending allocations.
- Gate syntax-dependent checks on Pylint's `py-version`, not the host
  interpreter alone. Support the declared Pylint range without silently
  changing the repository's dependency bounds.
- Emit no automatic source edits in the first release. A diagnostic identifies
  the concrete pattern and the suggested operation. A later fixer requires a
  separate design for comments, formatting, pragmas, and semantic safety.
- Respect Pylint's message enablement and inline/file suppression. Existing
  explanation requirements for suppression pragmas continue to apply.
- Use Pylint `HIGH` confidence for direct syntactic proofs and `INFERENCE`
  when the proof uses bounded binding/type inference. Both require complete
  eligibility evidence; confidence must not substitute for missing proof.
- Anchor one message at the first transformed expression or statement and
  supply the full candidate end span where the supported Pylint API permits.
  Include a target name or operation when that makes the advice actionable.
- Report deterministically by source location and symbolic name. Check one
  candidate once, including when a branch head and its nested nodes are
  visited. Preserve independent messages while suppressing smaller proposals
  that the same accepted replacement completely subsumes. Record each
  cross-rule precedence explicitly in the owning RFCs. Apply precedence only
  when the owning diagnostic actually emits; a disabled or suppressed new
  message must not hide an existing diagnostic.
- Test plugin reload and `--jobs` behaviour. The registration-deduplication
  proposal in PR 65 is pending and must not be assumed present on this base.
  Implementations must either depend on its accepted fix or prove equivalent
  idempotent behaviour before release.[^5]

The plugin must not infer which Ruff rules another process enabled, disable
upstream checks, or rewrite project configuration. The individual RFCs document
exact residual patterns and existing owners. Confirm that boundary against
pinned upstream fixtures when implementing each checker; a newly expanded
upstream matcher may remove the need for a candidate.

## Verification and rollout

Each implementation must provide:

1. Unit tests for proof kernels, including explicit unknown and contradicted
   results, invalidation, inference failures, and exhausted budgets.
2. Positive and negative checker examples for every accepted syntax shape,
   plus one near-miss for each precondition.
3. Property tests over a bounded, documented supported domain, comparing
   values, types, selected identities, effects, exceptions, and live bindings.
   Source-text equality or whole-document snapshots do not prove semantics.
4. Adversarial fixtures with stateful truth methods, subclasses, descriptors,
   throwing operations, aliases, empty iterables, and live loop variables.
5. End-to-end Pylint tests for opt-in defaults, symbols, spans, confidence,
   suppression, `py-version`, supported dependency endpoints, and serial versus
   worker execution.
6. Upstream-overlap fixtures and deterministic repeat-run output. Metamorphic
   checks must prevent advice that oscillates between equivalent spellings.

A bounded property test supports the stated domain; it does not establish
equivalence for arbitrary Python objects. The source-evidence argument and the
runtime counterexamples are complementary review artefacts.

Roll out one rule family at a time. Review false positives on representative
repositories before enabling a family in downstream policy. Adding these
documents changes no installed checker, default, dependency, or public command.

## Provenance

Sourcery's public catalogue supplies candidate names, examples, and semantic
inspiration.[^6] The proposals independently specify conservative Python
semantics; they include no Sourcery implementation code. Ruff, Pylint,
Whitaker, and Perflint receive specific attribution where they inform an RFC.
Do not copy a documented transformation without checking its preconditions.

[^1]: [Plugin registration](https://github.com/leynos/df12-python-lints/blob/4a85457d862fe62f6fb9590a6d77cfcc23ab509c/df12_python_lints/__init__.py)
    and [developer guide](https://github.com/leynos/df12-python-lints/blob/4a85457d862fe62f6fb9590a6d77cfcc23ab509c/docs/developers-guide.md).
[^2]: [RFC 0001 proposal, PR 64](https://github.com/leynos/df12-python-lints/pull/64)
    and [RFC 0002 proposal, PR 83](https://github.com/leynos/df12-python-lints/pull/83).
[^3]: Python 3.12:
      [evaluation order](https://docs.python.org/3.12/reference/expressions.html#evaluation-order)
    and [Boolean operations](https://docs.python.org/3.12/reference/expressions.html#boolean-operations).
[^4]: Pylint:
      [writing a checker](https://pylint.readthedocs.io/en/stable/development_guide/how_tos/custom_checkers.html).
[^5]: [Idempotent plugin registration, PR 65](https://github.com/leynos/df12-python-lints/pull/65).
[^6]: Sourcery:
      [Python refactoring catalogue](https://docs.sourcery.ai/reference/refactorings/).
