# RFC 0001: Baseline-aware Python 3.15 lint policies

## Preamble

- RFC number: 0001.
- Status: Proposed.
- Created: 2026-10-15.
- Scope: lint policy and delivery planning, not checker implementation.
- Delivery: [the project roadmap](../roadmap.md).

## 1. Summary

Extend df12-python-lints with conservative diagnostics for explicit lazy
imports, sentinels, and TypedDict openness. Offer narrower, opt-in checks for
frozen dataclass fields, immutable mapping construction, and regular-expression
API spelling. Keep comprehension flattening and annotation-format checks
experimental. Prefer configuring existing tools over maintaining duplicate
analyses.

Python 3.15 supplies the relevant lazy-import syntax, sentinel and frozendict
builtins, unpacking comprehensions, and TypedDict extra-item support.[^1]
These facilities justify reviewing the house style, not rewriting every older
idiom. Each proposal below defines a useful contract, detection limits, and
migration risks. This RFC changes no runtime behaviour, dependency pin, enabled
diagnostic, or supported Python version by itself.

## 2. Current state and problem

The [plugin entry point](../../df12_python_lints/__init__.py) registers ten
checkers and thirteen messages. Existing rules already cover type-alias syntax,
redundant future annotations, dataclass slots, and explained suppressions.
Their [documented architecture](../developers-guide.md#plugin-architecture)
uses Pylint and Astroid, with conservative lexical binding and dataclass-state
helpers. The new work should extend those boundaries, not introduce a second
analysis engine or configuration language.

The [package metadata](../../pyproject.toml) supports Python 3.12 or newer and
Pylint `>=3.3,<5`. The [Makefile](../../Makefile) runs Pylint 4.0.9 on
`pypy@3.12`. That is distinct from the baseline of a consuming project. A
Python 3.15 consumer needs a parser-capable lint interpreter and compatible
analysis dependencies; setting `py-version` alone cannot supply a newer
parser. The existing PyPy lane remains useful for older syntax.

The shared [typing guidance](../../.rules/python-typing.md) still recommends
future annotations unconditionally. Delivery must reconcile that text with
`redundant-future-annotations`, rather than adding another contradictory rule.

## 3. Goals and boundaries

The goal is useful, low-noise enforcement for Python 3.15 consumers without
breaking the plugin's Python 3.12 installation contract. Explicit import
timing, missing-value identity, and schema openness form the initial delivery.
Representation preferences remain independently selectable.

Do not implement type-checker assignability, deep-immutability proofs, a general
codemod engine, whole-program import-effect inference, or a new policy service.
Do not change the public API merely to make a lint pass. Keep existing
explicit-encoding requirements: UTF-8 defaults do not express a file contract,
and callers can disable UTF-8 mode.[^1]

Only accepted portions of this RFC authorize implementation. Record review
choices here; no additional approval machinery is required. Deferred proposals
need an explicit scope decision before implementation.

## 4. Ownership, gating, and common behaviour

### 4.1. Proposed rule inventory

Symbols are provisional, not installed messages. Allocate numeric identifiers
when implementing each accepted rule; preserve every existing identifier.
"Core" means recommended for an explicitly selected consumer profile, not
silently enabled for every project that loads the plugin. All new messages
initially require explicit enablement. "Optional" and "experimental" remain
off unless individually selected.

| Proposal | Minimum baseline | Initial policy | Owner |
| --- | --- | --- | --- |
| Lazy/eager module selection | 3.15 | Core | Ruff TID254 configuration |
| `prefer-syntactic-lazy-imports` | 3.15 | Core | Narrow df12 checker |
| `prefer-builtin-sentinel` | 3.15 | Core | df12 checker |
| `transient-sentinel-comparison` | 3.15 | Core | df12 checker |
| `explicit-typeddict-openness` | 3.15 | Core | df12 checker |
| `mutable-field-in-frozen-dataclass` | 3.12 | Optional | df12 checker |
| `prefer-frozendict-for-literal-proxy` | 3.15 | Optional | df12 checker |
| `prefer-prefixmatch` | 3.15 | Optional | Existing-tool configuration first |
| `prefer-unpacked-flattening` | 3.15 | Experimental | Existing-tool coverage first |
| `explicit-annotation-format` | 3.14 | Experimental | Narrow df12 checker |

_Table 1: Proposed ownership and consumer-baseline requirements._

Before implementing a custom rule, check the selected upstream releases for an
equivalent diagnostic. Where one exists, deliver configuration, examples, and
integration coverage instead. Do not reserve a df12 identifier for an
upstream-owned rule. Ruff TID254 already implements configurable lazy/eager
module selection, including compatibility declarations.[^2]

### 4.2. Baseline and parser contract

Use Pylint's existing `py-version` setting as the checker baseline. Keep that
value, Ruff's `target-version`, and the consumer's `requires-python` consistent
in documented configurations and integration fixtures. An omitted Pylint
setting retains Pylint's behaviour; the migration guide must therefore show an
explicit baseline, not imply automatic reading of project metadata.

Separate these three concerns:

- The plugin's own source and installation floor remain Python 3.12.
- A checker emits only when its configured consumer baseline permits it.
- The interpreter and Astroid must parse the actual source being analysed.

Add a CPython 3.15 consumer lane with a tested Pylint/Astroid combination and a
pinned Ruff release. Preserve the older installation and syntax lanes. Record
verified versions during implementation rather than assuming that the entire
existing dependency range understands Python 3.15. Document any required
version floor or conditional dependency precisely. Parser failures must remain
failures, not successful scans with the troublesome files omitted.

### 4.3. Analysis, diagnostics, and exceptions

Resolve imported APIs through active lexical bindings, including aliases and
shadowing. Unknown or conflicting bindings suppress speculative findings.
Reuse the strict dataclass resolver and field classification where appropriate;
do not weaken their contracts to share code. Bound and cache any inheritance
walk per module. Never import the target program, evaluate annotations, or
mutate its abstract syntax tree (AST) while linting.

Emit one finding at the actionable declaration or call, with the symbol,
location, reason, and suggested direction. Use Pylint's existing enable,
disable, and output mechanisms. Reuse the explained-suppression checker for
Pylint and Ruff comments. Do not invent a second allowlist. Non-comment Ruff
configuration exceptions require a nearby explanatory TOML comment and review;
the existing comment checker does not validate TOML.

Custom checkers initially provide diagnostics only. An example rewrite is not
an automatic-fix guarantee. Upstream unsafe fixes must not run unattended as
part of profile adoption. The installed-wheel integration suite must also
check that parallel Pylint workers do not multiply findings.

## 5. Explicit, syntactic lazy imports

### 5.1. Select import timing through Ruff

PEP 810 permits module-scope `lazy import` and `lazy from` statements, but not
function-local, class-body, protected `try` imports, star imports, or future
imports. Loading failures move to first use; registration and other import-time
effects can consequently move or disappear.[^3]

Use TID254 `require-lazy` and `ban-lazy` for module selection. Begin with
audited module lists. A consumer may later choose the documented `all`
selector with explicit eager exclusions, after checking its import-time
contracts.[^4] No package-wide default should make arbitrary third-party
imports lazy. Keep eager imports for registration, startup validation, and
other deliberately immediate effects, with local reasons.

For example, a consumer can require typing imports to be lazy while preserving
an application-specific registration import. The module names are illustrative:

```toml
[tool.ruff]
target-version = "py315"

[tool.ruff.lint]
extend-select = ["TID254"]

[tool.ruff.lint.flake8-tidy-imports]
require-lazy = ["typing"]
# This module registers handlers during application startup.
ban-lazy = ["application.registration"]
```

Do not mechanically hoist function-local or `TYPE_CHECKING` imports. Local
imports may deliberately catch optional-dependency failures, follow environment
setup, or occur after monkey-patching. Type-only imports can expose names that
do not exist at runtime. Validate each conversion with the consumer's runtime
annotation and startup behaviour. Retain genuine type-checking-only constructs.

### 5.2. Close the syntax-only policy gap

TID254 recognizes literal `__lazy_modules__` declarations, so satisfying it does
not establish that source uses the `lazy` keyword. Dynamic declarations also
fall outside its static analysis.[^2] Add `prefer-syntactic-lazy-imports` only
for this remaining representation policy.

The checker reports module-scope assignments, annotated assignments with a
value, and augmented assignments targeting `__lazy_modules__`. It reports even
when the value is dynamic: the finding concerns use of the compatibility
mechanism, not a claim to know which imports it affects. Annotation-only names,
reads, unrelated object attributes, and names local to a function or class do
not trigger it. Reflective dictionary writes and indirect mutations remain
outside the initial detection boundary.

On a 3.15-only baseline, prefer declarations at each import site:

```python
# Discouraged compatibility form on a 3.15-only baseline.
__lazy_modules__ = ["json"]
import json

# Preferred replacement, after reviewing timing and all declaration users.
lazy import json
```

Emit at the compatibility assignment, not once per affected import. Do not
suggest deleting a marker without converting every relevant import and checking
other uses. No automatic fix applies to dynamic lists, mutations, conditional
bindings, or mixed lazy/eager imports. Below Python 3.15, remain silent.

Global lazy mode, `sys.set_lazy_imports`, and runtime filters do not satisfy a
source-level contract. Do not ban them outright: embedding, compatibility
tests, and import-control tools can use them legitimately. General dynamic-mode
analysis and automatic local-import hoisting are deferred.

### 5.3. Evidence required for adoption

Exercise eager registration, delayed missing dependencies, ordinary and
`from` imports, aliasing, relative imports, mixed-member statements, protected
imports, and runtime annotation consumers. Check Ruff formatting and import
sorting together with TID254 and the new marker diagnostic. Illegal lazy
syntax belongs to the parser, not a redundant checker. Keep fixes disabled in
the normal gate; an intentionally authorized migration must converge rather
than oscillate between tools.

## 6. Sentinels and explicit schema contracts

### 6.1. Prefer the builtin for identifiable missing-value sentinels

`sentinel(name)` creates a fresh object whose copies retain identity. Correctly
named, importable definitions support pickling and type expressions.[^5]
`prefer-builtin-sentinel` reports a single, unreassigned module-level name
initialized by an unshadowed, zero-argument `object()` when local evidence shows
its use as an identity sentinel: an `is`/`is not` comparison or a parameter
default paired with such a comparison. Capitalization alone is insufficient.

A declaration changes as follows:

```python
MISSING = object()  # Candidate when identity-sentinel use is established.

# Preferred declaration in a Python 3.15 consumer.
MISSING = sentinel("MISSING")
```

Exclude ordinary object allocations, local per-call tokens, shadowed builtins,
ambiguous assignments, exported third-party sentinel objects, enums, and custom
sentinel classes. Do not assume a public constant is safe to replace: its
representation, exact type, copy behaviour, and serialization contract can be
observable. Keep the recommendation diagnostic-only and permit a reasoned
compatibility suppression. Establish evidence within the module; do not infer
missing-value intent from names elsewhere in the repository.

### 6.2. Detect comparisons against freshly constructed sentinels

`transient-sentinel-comparison` reports `is` or `is not` between an existing
name and a direct call to the resolved builtin `sentinel`. Creating the same
named sentinel again does not retrieve the earlier object.[^5]

The comparison must use the stored sentinel rather than recreate it:

```python
MISSING = sentinel("MISSING")

# Flag: the constructor does not intern by name.
if value is sentinel("MISSING"):
    handle_missing()

# Preferred.
if value is MISSING:
    handle_missing()
```

Recognize reversed operands as well. Start with simple, non-chained identity
comparisons. Exclude shadowed constructors, assignment expressions that bind
and reuse the freshly constructed object, and unsupported expression shapes.
Do not expand this rule to arbitrary equality methods. Intentional uniqueness
tests use an explained suppression. No automatic fix can safely guess which
existing sentinel the author intended.

### 6.3. Make TypedDict openness a declared choice

PEP 728 distinguishes open, closed, and typed-extra-item schemas. Neither
`total=False` nor read-only fields specifies openness. This is a static typing
contract, not a runtime validator.[^6]

`explicit-typeddict-openness` checks both class and functional TypedDict
construction, resolving `typing` and compatible `typing_extensions` aliases.
Require explicit `closed=True`, `closed=False`, or `extra_items=...` at schema
roots. A statically established, compatible inherited policy also qualifies.
Do not repeat a root's omission on every descendant. Leave invalid keyword
combinations and incompatible inheritance to the type checker; skip unresolved
bases and unknown keyword unpacking rather than invent an effective policy.

For example, all three declarations express a deliberate contract:

```python
import typing as typ

class ClosedEvent(typ.TypedDict, closed=True):
    kind: str

class OpenEvent(typ.TypedDict, closed=False):
    kind: str

class ExtendedEvent(typ.TypedDict, extra_items=str):
    kind: str
```

Do not automatically add `closed=True`, rewrite open schemas to
`extra_items=object`, or treat `ReadOnly` as runtime immutability. Test local
inheritance, functional syntax, generic schemas, aliases, and ambiguous bases.
Validate migration examples with the consumer's type checker. Lower-baseline
backport adoption is outside the initial rule, even when the imported backport
already exposes these features.

## 7. Optional value-object and API policies

### 7.1. Mutable fields in frozen dataclasses

`frozen=True` prevents ordinary field rebinding; it does not recursively freeze
field values.[^7] Offer `mutable-field-in-frozen-dataclass` as an optional
value-object policy, not a correctness error or proof of deep immutability.

Recognize the real standard-library decorator with literal `frozen=True` and
actual instance fields whose top-level annotation resolves to `list`, `dict`,
or `set`, including a simple union containing one of those types. Recognize
matching `field(default_factory=...)` evidence when the annotation does not
already produce a finding. Reuse existing field classification. Exclude
`ClassVar`, `InitVar`, properties, third-party dataclass-like decorators,
unknown aliases, and nested mutability beyond this initial scope.

A frozen value object can expose an immutable mapping deliberately:

```python
import dataclasses

@dataclasses.dataclass(frozen=True, slots=True)
class Configuration:
    options: frozendict[str, str]
```

The diagnostic may suggest tuple, frozenset, or, on Python 3.15+, frozendict,
but must not change constructors or annotations automatically. Annotating a
field as `Mapping` does not freeze the supplied object. Frozendict also leaves
mutable values mutable, and it is not a dict subclass.[^8] Document caches and
other deliberately mutable state as legitimate exceptions, not analysis bugs.

### 7.2. Prefer immutable snapshots only for isolated literal proxies

`prefer-frozendict-for-literal-proxy` recognizes
`types.MappingProxyType({...})` around a directly constructed dict literal,
with no assignment expression or escaping reference to that dict. Resolve
aliases, and exclude unknown argument expansions and constructor shadowing.

A mapping proxy reflects subsequent changes to its backing mapping.[^9]
Therefore never flag `MappingProxyType(existing_mapping)` under this rule.
Even the literal case changes runtime type, representation, and serialization
behaviour, so it remains an optional suggestion without an automatic fix.
Do not claim that either representation recursively freezes values.

### 7.3. Prefer explicit regular-expression prefix matching

Python 3.15 adds `re.prefixmatch` and `Pattern.prefixmatch`. The older `match`
name is soft deprecated, with no removal planned.[^10] Prefer upstream API-ban
configuration for resolved `re.match` uses. Add a custom `prefer-prefixmatch`
checker only for coverage that selected upstream tools demonstrably lack.

If that gap remains, cover direct imports and aliases, then calls on a receiver
proven to be a standard-library compiled pattern. Do not flag arbitrary
`.match()` methods, third-party regex APIs, or ambiguous receivers. Preserve
patterns, flags, `pos`, and `endpos`. Never substitute `search` or `fullmatch`.
Patch targets and compatibility wrappers may deliberately retain the old name;
allow explained exceptions. Avoid duplicate findings for upstream-owned uses.

## 8. Deferred experiments and non-AST work

### 8.1. Unpacked flattening

PEP 798 supports unpacking comprehensions.[^11] Evaluate
`prefer-unpacked-flattening` against existing Ruff coverage before allocating
a new rule. Start only with synchronous list comprehensions shaped exactly as
`[item for group in groups for item in group]`, with simple distinct target
names and no filters, projections, or assignment expressions. The candidate
replacement is `[*group for group in groups]`.

Treat readability as a hypothesis to test with examples, not an objective
correctness improvement. Custom iterables can expose iteration-protocol
behaviour; do not promise semantic equivalence or a safe automatic fix across
arbitrary implementations. Defer dictionaries, sets, generators, and async
forms until separately justified. In particular, replacing arbitrary `.items()`
calls with mapping unpacking needs more evidence than matching the spelling.

### 8.2. Explicit annotation formats

Evaluate `explicit-annotation-format` for calls resolving to
`annotationlib.get_annotations` without an explicit `format=` argument. Any
explicit format expression satisfies this policy; type checking owns its
validity. Skip unknown `**kwargs` rather than claiming the format is absent.
The baseline is Python 3.14 because that is when annotationlib appeared.[^12]

Accept deliberate `Format.VALUE`, `Format.FORWARDREF`, and `Format.STRING` use.
Do not require FORWARDREF, rewrite `typing.get_type_hints`, or ban direct
annotation access under this rule. None of these formats provides a sandbox:
annotation introspection can execute arbitrary code.[^12] Keep this opt-in for
introspection-heavy code and provide no automatic choice of format.

### 8.3. Packaging startup and excluded analyses

PEP 829 introduces `.start` files and deprecates executable import lines in
`.pth` files.[^13] A future packaging audit could identify owned distributions
that still ship executable `.pth` lines. That is not a Pylint AST rule. Do not
scan or modify the user's environment, execute startup files, or create a new
scanner under this RFC. Revisit only with a concrete packaging consumer and a
separately approved input and reporting contract.

Leave TypeForm semantics, disjoint bases, ordinary deprecated APIs, and general
assignability to maintained type checkers and linters. Global lazy-import
control, arbitrary compatibility-marker mutation, and automatic import
relocation also remain deferred. No delivery task should imply their approval.

## 9. Validation and adoption

Every implementation task includes its unit and behavioural tests, negative
examples, alias/shadowing cases, baseline boundaries, and user documentation.
Use property-based tests on real decision kernels where they add evidence;
do not build a duplicate model solely to claim verification.

Provide installed-wheel end-to-end (E2E) coverage for the interaction between
consumer baselines 3.12, 3.14, and 3.15, capable host interpreters, enabled and
disabled messages, explained suppressions, and single/parallel Pylint workers.
Run new syntax only on capable hosts. Exercise Ruff checking, formatting, and
import sorting alongside Pylint, and check import/annotation runtime behaviour
in small isolated fixture programs. A syntax failure is not a clean result.

Adopt the core rules first in explicitly selected consumers. Record each
finding as actionable, intentional, or incorrect. A default recommendation
requires no unexplained false positives in the reviewed pilot, stable output
across worker counts, and no duplicated upstream finding for the same policy.
A pilot with no real examples does not validate a rule; retain it as opt-in.
Publish the sample size and limitations rather than extrapolating certainty.

Migrate selected callers in focused changes. Correct the future-annotations
guidance with baseline-specific advice, and document how to select the newer
lint interpreter. Keep optional policies opt-in regardless of core adoption.
Update the user's guide only as functionality actually ships, clearly
separating examples of proposed configuration from installed capabilities.

## 10. Alternatives and outstanding decisions

A blanket demand for every new syntax form would create churn without proving
value. Conversely, relying exclusively on upstream tools leaves deliberate
house policies such as TypedDict openness and syntax-only lazy declarations
unenforced. A second configuration engine would add maintenance without solving
either problem. Prefer small Pylint checks where a measured gap remains and
ordinary upstream configuration everywhere else.

Before implementation, settle the initial consumer/module scope, select and
test the parser/tool versions, and check whether upstream rules now cover the
proposed gaps. Do not allocate custom message numbers or promote optional
rules merely because this RFC exists. A proposal can narrow its detection,
remain optional, or be rejected after the pilot.

The recommendation is to deliver the runtime/baseline foundation, explicit
imports, sentinel identity, and schema openness first. Deliver optional
value-object and regex policies separately. Keep the experiments and packaging
work out of the initial adoption path. The roadmap expresses those choices as
falsifiable phases and review-sized tasks, without calendar commitments.

[^1]: [Python 3.15 release changes](https://docs.python.org/3.15/whatsnew/3.15.html).
[^2]: [Ruff TID254](https://docs.astral.sh/ruff/rules/lazy-import-mismatch/).
[^3]: [PEP 810: Explicit lazy imports](https://peps.python.org/pep-0810/).
[^4]: [Ruff lazy-import settings](https://docs.astral.sh/ruff/settings/#lint_flake8-tidy-imports_require-lazy).
[^5]: [Python sentinel reference](https://docs.python.org/3.15/builtins/functions.html#sentinel).
[^6]: [TypedDict specification](https://typing.python.org/en/latest/spec/typeddict.html).
[^7]: [Frozen dataclass instances](https://docs.python.org/3.15/library/dataclasses.html#frozen-instances).
[^8]: [Frozen dictionaries](https://docs.python.org/3.15/builtins/stdtypes.html#frozendict).
[^9]: [MappingProxyType](https://docs.python.org/3.15/library/types.html#types.MappingProxyType).
[^10]: [Prefix matching versus match](https://docs.python.org/3.15/library/re.html#prefixmatch-vs-match).
[^11]: [PEP 798: Unpacking in comprehensions](https://peps.python.org/pep-0798/).
[^12]: [Annotation introspection and security](https://docs.python.org/3.15/library/annotationlib.html).
[^13]: [PEP 829: Package startup files](https://peps.python.org/pep-0829/).
