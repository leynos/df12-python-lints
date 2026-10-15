# df12-python-lints roadmap

This roadmap translates [RFC 0001] into delivery work for baseline-aware Python
3.15 lint policies. It covers that proposal, not a retrospective inventory of
the existing plugin or unrelated backlog. The goal is explicit import and data
contracts with low-noise diagnostics, while preserving Python 3.12 package
installation and avoiding duplicate upstream analyses. The RFC remains
Proposed; implementation depends on accepting the relevant scope.

Goals, Ideas, Steps, and Tasks (GIST) supply the structure. The goal guides
falsifiable phase ideas, steps answer delivery questions, and checkbox tasks
form review-sized execution units. The roadmap promises no dates. Each delivery
task includes unit and behavioural tests, relevant property tests, and user
and developer documentation. End-to-end (E2E) interaction suites have dedicated
tasks where their scope crosses individual features.

The planning format follows the [roadmap-doc skill] and its [conventions] at
revision `528fcdad5d6bd9750baa1b2e122a349eda5c22bf`, the canonical location
referenced by `leynos/agent-helper-scripts`. Existing implementation constraints
remain in the [developer guide](developers-guide.md#plugin-architecture) and
[ADR 001](adr-001-conservative-dataclass-layout-analysis.md). Tasks below record
implementation work, not approval by their mere appearance in this document.

## 1. Make newer consumer baselines usable without abandoning older hosts

Idea: if the plugin separates its installation floor, consumer policy baseline,
and parsing interpreter, Python 3.15 consumers can use the new policies without
breaking existing Python 3.12 users or silently skipping unsupported source.

This phase establishes a runnable consumer path before adding diagnostics. A
failed parser-capability or dependency-resolution check falsifies the proposed
compatibility promise and requires a narrower, documented supported matrix.

### 1.1. Settle the small set of choices that controls implementation

Which proposals need custom analysis, and which belong to existing tools? The
answer fixes ownership and prevents parallel implementations of the same rule.
See [RFC 0001] §§1-4 and §10.

- [ ] 1.1.1. Record accepted initial scope and an upstream ownership map in
  RFC 0001, including provisional symbols and consumer selection.
  - See [RFC 0001] §§3-4 and §10.
  - Success: each proposal has an implement, configure, or defer outcome;
    custom symbols do not duplicate selected upstream rules, and optional
    policies remain independently selectable. No numeric identifier is reused.

### 1.2. Deliver a parser-capable consumer validation path

Can the published wheel analyse 3.15 syntax while the package still installs
on its older supported hosts? The result determines real tooling requirements
and the migration instructions used by every later slice.
See [RFC 0001] §§2 and 4.2.

- [ ] 1.2.1. Add a CPython 3.15 consumer lane to the existing build and
  continuous integration workflow, with tested Pylint/Astroid and Ruff pins.
  - Requires 1.1.1.
  - See [RFC 0001] §§4.2-4.3 and §9.
  - Success: an installed wheel analyses lazy-import and unpacking syntax;
    malformed source fails the gate; existing older-host installation and
    syntax lanes still pass; any dependency-floor change is explicit.
- [ ] 1.2.2. Publish consistent baseline configuration examples and correct
  the shared future-annotations guidance.
  - Requires 1.2.1.
  - See [RFC 0001] §§2, 4.2, and 9.
  - Success: examples align `requires-python`, `py-version`, and Ruff's target;
    explain the separate lint interpreter; retain appropriate older-baseline
    guidance; and never present proposed diagnostics as already installed.

## 2. Make import timing explicit without changing startup contracts accidentally

Idea: if upstream module-selection policy and one narrow compatibility-marker
check suffice, consumers can express laziness at import sites without losing
intentional eager effects or maintaining another import-policy engine.

This slice delivers configuration and diagnostics together. Unexpected changes
to registration, failure timing, or annotation consumers require narrowing the
selected module scope rather than adding blanket exceptions.

### 2.1. Express audited lazy and eager choices in source

Does TID254 plus a syntax-only marker diagnostic close the stated policy gap?
The answer determines whether additional custom import analysis is justified.
See [RFC 0001] §§5.1-5.2.

- [ ] 2.1.1. Publish a tested Ruff TID254 consumer recipe with documented lazy
  module selection and explained eager exceptions.
  - Requires 1.2.1 and 1.2.2.
  - See [RFC 0001] §§4.1 and 5.1.
  - Success: audited lazy/eager examples yield expected diagnostics; protected,
    local, star, and future imports avoid invalid conversion advice; the
    recipe does not enable global laziness or unattended unsafe fixes.
- [ ] 2.1.2. Implement `prefer-syntactic-lazy-imports` for module-level
  compatibility-marker assignments and register it as an opt-in message.
  - Requires 1.2.1.
  - See [RFC 0001] §§4.3 and 5.2.
  - Success: simple, annotated-value, augmented, and dynamic assignments emit
    one actionable finding; reads, annotation-only names, unrelated attributes,
    local bindings, and pre-3.15 baselines do not; no automatic deletion occurs.

### 2.2. Establish that the complete import-policy loop preserves intended effects

Do formatting, import sorting, linting, and runtime annotation use agree on the
same source? This work informs whether the proposed module scope is safe to
recommend, not whether every import can theoretically become lazy.
See [RFC 0001] §§5.3 and 9.

- [ ] 2.2.1. Add an installed-wheel E2E import-policy suite that combines
  Ruff checking, formatting, sorting, and Pylint diagnostics.
  - Requires 2.1.1 and 2.1.2.
  - See [RFC 0001] §§4.3, 5.3, and 9.
  - Success: aliases, relative and mixed-member imports, protected optional
    dependencies, eager registration, and runtime annotation fixtures behave
    as specified; authorized migration examples converge without fix cycles.
- [ ] 2.2.2. Publish a reviewed import-policy pilot and migration guidance for
  the selected consumer scope.
  - Requires 2.2.1.
  - See [RFC 0001] §§5 and 9-10.
  - Success: every pilot finding has an actionable, intentional, or incorrect
    classification; the documented outcome retains or narrows scope; eager
    exceptions have reasons; no automatic local-import hoisting is prescribed.

## 3. State missing-value identity and schema openness explicitly

Idea: if local evidence identifies sentinel intent and explicit TypedDict
policies, the plugin can expose meaningful contract mistakes without replacing
a type checker or guessing public compatibility obligations.

Sentinel and schema checks form independent usable slices. Ambiguous binding
or inheritance results must stay silent. A pilot that needs broad exemptions
or duplicates type-checker errors argues against a core recommendation.

### 3.1. Detect sentinel construction and identity mistakes

Can the checker distinguish missing-value sentinels from ordinary object
allocations and intentional uniqueness tests? The answer controls how broadly
sentinel adoption can be recommended.
See [RFC 0001] §§6.1-6.2.

- [ ] 3.1.1. Implement `prefer-builtin-sentinel` with module-local identity-use
  evidence and conservative builtin resolution.
  - Requires 1.2.1.
  - See [RFC 0001] §§4.3 and 6.1.
  - Success: eligible single bindings report; capitalization alone, rebindings,
    local allocation, custom sentinels, and shadowed `object` do not; public
    compatibility warnings and explained suppressions appear in the guide.
- [ ] 3.1.2. Implement `transient-sentinel-comparison` for direct builtin
  construction compared with a stored name using `is` or `is not`.
  - Requires 1.2.1.
  - See [RFC 0001] §§4.3 and 6.2.
  - Success: both operand orders report; stored-sentinel comparisons,
    constructor shadowing, assignment-expression exceptions, and unsupported
    chained comparisons remain quiet; the diagnostic never guesses a fix.

### 3.2. Declare schema openness without constraining legitimate extension

Can class, functional, and inherited schemas state a deliberate contract
without defaulting everything to closed? The result sets the boundary between
house-style evidence and type-checker-owned assignability.
See [RFC 0001] §6.3.

- [ ] 3.2.1. Implement `explicit-typeddict-openness` for class and functional
  schema roots with resolved standard-library or backport bindings.
  - Requires 1.2.1.
  - See [RFC 0001] §§4.3 and 6.3.
  - Success: omitted policies report; explicit open, closed, or extra-item
    declarations qualify; `total=False` does not stand in for openness;
    unknown keyword unpacking stays quiet; migration examples type-check.
- [ ] 3.2.2. Extend the openness checker to locally resolvable inheritance
  while suppressing cascading and speculative findings.
  - Requires 3.2.1.
  - See [RFC 0001] §§4.3 and 6.3.
  - Success: compatible inherited policies qualify; a root omission reports
    once rather than on all descendants; conflicting and unresolved bases
    stay with the type checker; generic and alias cases preserve that boundary.

### 3.3. Establish a low-noise core consumer profile

Do the core rules remain predictable across version gates, suppressions,
parallel workers, and the import policies already delivered? This work decides
which rules earn recommendation and which remain experimental.
See [RFC 0001] §§4 and 9.

- [ ] 3.3.1. Add installed-wheel E2E coverage for the combined core profile
  across supported baselines, enablement states, and worker counts.
  - Requires 2.2.1, 3.1.1, 3.1.2, and 3.2.2.
  - See [RFC 0001] §§4.2-4.3 and 9.
  - Success: capable hosts exercise 3.12, 3.14, and 3.15 policy boundaries;
    disabling messages and explained suppression work; single and parallel
    runs yield equal finding multisets; parser failures cannot produce green.
- [ ] 3.3.2. Publish the reviewed core-rule pilot, migration examples, and
  consumer enablement recipe.
  - Requires 2.2.2 and 3.3.1.
  - See [RFC 0001] §§6, 9, and 10.
  - Success: the report states sample size, limitations, and finding outcomes;
    recommendations have no unexplained false positives or duplicate upstream
    findings; unexercised rules remain opt-in instead of claiming validation.

## 4. Offer representation policies without presenting them as correctness proofs

Idea: if value-object and API preferences remain narrow and opt-in, they can
improve explicitness without invalidating intentional caches, live mapping
views, or compatibility-facing APIs.

This phase does not gate the core release. Evidence of harmful churn or
ambiguous type resolution keeps a policy optional, narrows it, or rejects it.

### 4.1. Distinguish immutable snapshots from deliberately mutable state

Can field and literal-construction evidence support helpful recommendations
without claiming deep immutability? The answer controls the eligible shapes
and the exception guidance.
See [RFC 0001] §§7.1-7.2.

- [ ] 4.1.1. Implement the optional frozen-dataclass mutable-field check using
  existing decorator and instance-field classification.
  - Requires 1.2.1 and 3.3.1.
  - See [RFC 0001] §§4.3 and 7.1.
  - Success: direct builtin mutable fields and supported factories report once;
    `ClassVar`, `InitVar`, unknown types, and unrelated decorators do not;
    pre-3.15 hints never recommend frozendict; no deep-freeze claim appears.
- [ ] 4.1.2. Implement the optional literal-mapping-proxy recommendation.
  - Requires 1.2.1 and 3.3.1.
  - See [RFC 0001] §§4.3 and 7.2.
  - Success: isolated direct literal proxies report, while named live views,
    escaping references, and shadowed constructors do not; documentation
    explains representation changes and no automatic fix is offered.

### 4.2. Express regular-expression prefix intent without duplicating upstream rules

Does upstream configuration cover the required API spelling, and is any
compiled-pattern gap worth maintaining locally? This determines ownership
before adding another checker.
See [RFC 0001] §7.3.

- [ ] 4.2.1. Deliver the prefix-matching policy through upstream configuration,
  adding a custom checker only for a demonstrated residual coverage gap.
  - Requires 1.1.1 and 1.2.1.
  - See [RFC 0001] §§4.1, 7.3, and 10.
  - Success: resolved standard-library calls report exactly once; arbitrary
    `.match()` methods stay quiet; flags and pattern bounds retain their
    meaning; soft deprecation is not described as impending removal.

### 4.3. Keep optional policies useful in combination

Do the optional rules produce independent, actionable feedback when enabled
alongside core rules? This establishes adoption guidance without promoting
preferences into package-wide requirements.
See [RFC 0001] §§7 and 9.

- [ ] 4.3.1. Extend the installed-wheel interaction suite and publish an
  optional-policy pilot covering value objects and regex use.
  - Requires 4.1.1, 4.1.2, and 4.2.1.
  - See [RFC 0001] §§4.3, 7, and 9.
  - Success: independent enablement and suppressions work; legitimate mutable
    caches and live proxies remain supported; feedback records useful versus
    incorrect findings; every policy remains opt-in after the pilot.

## 5. Evaluate deferred extensions without enlarging the core promise

Idea: if the core contract is established first, readability experiments and
packaging proposals can justify themselves through concrete consumer value
instead of expanding the initial release by default.

These tasks are inactive until their scope receives explicit acceptance.
Retaining the current behaviour is a valid outcome. They do not block phases
2-4, and do not authorize general codemods or a new packaging scanner.

### 5.1. Test whether unpacked flattening improves real code

Does the new spelling improve the narrow supported cases beyond existing Ruff
coverage? The answer determines whether to configure upstream tooling, retain
an experimental rule, or omit this policy.
See [RFC 0001] §8.1.

- [ ] 5.1.1. Produce a bounded comparison corpus and opt-in prototype for
  synchronous list flattening, only after accepting the experiment's scope.
  - Requires 3.3.2.
  - See [RFC 0001] §§4.1, 8.1, and 10.
  - Success: the comparison covers ordinary lists and observable custom
    iterables; filters, projections, async forms, and dictionary merging stay
    excluded; an explicit keep, narrow, or reject decision records the result.

### 5.2. Test explicit annotation formats in an introspection consumer

Does naming the format improve an actual annotation-consuming API, rather than
merely adding repetition? The result controls whether this remains a targeted
opt-in policy or should be dropped.
See [RFC 0001] §8.2.

- [ ] 5.2.1. Deliver an experimental annotation-format checker and consumer
  examples after accepting that narrower scope.
  - Requires 3.3.2.
  - See [RFC 0001] §§4.3, 8.2, and 9.
  - Success: omitted formats report from baseline 3.14; explicit choices,
    shadowed APIs, and unknown keyword unpacking remain quiet; examples cover
    runtime evaluation without asserting that any format is a sandbox.

### 5.3. Establish whether owned package startup files need a separate audit

Is there a concrete packaging consumer that justifies a non-AST tool? This
step informs a separate proposal; it does not silently introduce a scanner.
See [RFC 0001] §8.3.

- [ ] 5.3.1. Document owned distribution examples and a go/no-go decision for
  auditing executable `.pth` lines alongside `.start` migration.
  - Requires 3.3.2.
  - See [RFC 0001] §§3, 8.3, and 10.
  - Success: a separate proposal defines inputs and reporting if justified;
    otherwise the work remains deferred; no environment scanning, startup-code
    execution, global lazy-mode checker, or import relocation is introduced.

[RFC 0001]: rfcs/0001-python-315-lints.md
[roadmap-doc skill]: https://github.com/leynos/df12-documentation-skills/blob/528fcdad5d6bd9750baa1b2e122a349eda5c22bf/skills/roadmap-doc/SKILL.md
[conventions]: https://github.com/leynos/df12-documentation-skills/blob/528fcdad5d6bd9750baa1b2e122a349eda5c22bf/skills/roadmap-doc/references/conventions.md
