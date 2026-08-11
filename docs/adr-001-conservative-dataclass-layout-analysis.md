# Architectural decision record (ADR) 001: Conservative dataclass layout analysis

## Status

Accepted. R9111 uses conservative source analysis with per-module caches and a
bounded Pylint compatibility range.

## Date

2026-08-03.

## Context and problem statement

`dataclass(slots=True)` returns a replacement class and can be unsafe or
ineffective when decorators retain the original class, methods capture its
class cell, or inherited layouts provide dictionaries or conflicting slots.
R9111 must report ordinary closed value types without speculating when Astroid
cannot prove that the replacement layout is safe. Transitive base analysis must
also remain efficient for modules containing deep inheritance chains.

## Decision drivers

- Prefer false negatives to unsafe slot suggestions.
- Do not import, execute, or mutate the linted program.
- Keep repeated base-layout analysis linear in the local class graph.
- Make reliance on Astroid's private `Instance._proxied` bridge explicit.

## Options considered

- Infer optimistically and report unless a known incompatibility is found.
- Recompute each complete base lineage for every class visit.
- Analyse conservatively and memoize eligibility and local inherited layouts.

## Decision outcome

In the context of R9111 analysis for standard-library dataclasses, facing
replacement-class hazards, incomplete inference, and deep inheritance chains,
conservative source analysis with per-module eligibility and layout caches was
chosen over optimistic inference or repeated lineage traversal, to achieve safe
diagnostics with linear repeated layout classification, accepting additional
false negatives and cache invalidation after the provisional
reverse-inheritance pass.

The package supports `pylint>=3.3,<5`. A new Pylint major version must preserve
the covered Astroid `Instance._proxied` behaviour before the upper bound moves.

## Consequences

- Unknown or ambiguous bases suppress R9111 rather than guessing.
- `LayoutAnalyzer` clears provisional eligibility and layout caches before
  final class visits incorporate reverse multiple-inheritance conflicts.
- Regression tests cover the private inference bridge and linear deep-chain
  layout classification.

## Known risks and limitations

- Cross-module reverse inheritance remains unknowable to a normal Pylint pass.
- Conservative inference may require an explained local suppression for safe
  classes whose layout cannot be proven.
