# Developer guide

This guide explains the contributor workflow for the generated project.

## Plugin architecture

Pylint discovers the plugin through `register()` in
`df12_python_lints/__init__.py`, the entry point pylint calls when
`load-plugins` names the package. It instantiates and registers the ten
checkers, each defined in its own module: `MatchDispatchChecker`,
`AssertMessageChecker`, `ConstantChainChecker`, `TrivialWrapperChecker`,
`ReexportAssignmentChecker`, `SuppressionCommentChecker`,
`SnapshotAssertionChecker`, `DataclassSlotsChecker`, `TypeAliasChecker`, and
`FutureAnnotationsChecker`. Between them, they expose thirteen messages. The
last two are gated on pylint's `py-version` option: the type-alias check needs
a 3.12+ baseline (PEP 695) and the future-annotations check a 3.14+ baseline
(PEP 749 deferred evaluation), so the end-to-end shim tests pass
`--py-version=3.14` explicitly — the shim runs under PyPy, whose interpreter
version would otherwise gate both checks off.

Reusable or substantial checker analysis lives in private helper modules:

- `_chains.py` holds the traversal used by the dispatch-oriented checkers to
  walk a head `if` statement and its `elif` chain. Its pure selection kernels
  (`repeated_subject`, `narrowing_prefix`) carry PEP 316 `pre:`/`post:`
  contracts so CrossHair can model-check them symbolically, separate from the
  astroid-bound checker classes that consume them.
- `_expressions.py` holds the attribute-chain and name-binding helpers — for
  example resolving the base `Name` of a pure `name.attr.deeper` chain — used
  by the wrapper and re-export checkers.
- `_dataclass_decorators.py` resolves `dataclasses.dataclass` and related
  decorators from active lexical import bindings. It deliberately avoids
  qualified-name spelling alone, inference that imports the linted program, and
  ambiguous lookup chains. This strict resolver is intentionally distinct from
  the type-alias checker's import recognition: a dataclass decorator is valid
  only when one unambiguous active binding proves its identity, while the
  type-alias checker conservatively classifies a name when its lookup chain
  contains a supported import. Keep the shared primitives policy-neutral if
  these implementations are consolidated; do not weaken either checker's
  ambiguity contract merely to remove similar traversal code.
- `_dataclass_state.py` distinguishes runtime `__slots__` assignments and real
  dataclass fields from class-only names. It is the shared source-state
  boundary for slot-layout and direct-method mutation analysis; keep
  inheritance and replacement-class decisions out of this module.
- `_dataclass_inference.py` resolves Astroid base candidates to unambiguous
  class definitions and defines the ordered layout classification used by
  inherited-layout and replacement-class hazard analysis.
- `_dataclass_analysis.py` classifies direct-method state evidence,
  replacement-class hazards, and inherited layouts for `DataclassSlotsChecker`.
  A `LayoutAnalyzer` is created once per module. It caches eligibility and
  per-class inherited layouts, and performs a reverse inheritance pass before
  class visits, so local dataclass bases later combined through multiple
  inheritance are suppressed before either base can report. The provisional
  caches are cleared after that reverse pass so final decisions include every
  discovered conflict.

The runtime dependency is bounded to `pylint>=3.3,<5`. Dataclass base inference
uses Astroid's private `Instance._proxied` bridge because no public API exposes
the underlying `ClassDef`; a new Pylint major version therefore requires the
focused inference and inherited-layout tests to be revalidated before widening
the range. [ADR 001](adr-001-conservative-dataclass-layout-analysis.md) records
the conservative analysis, caching, and compatibility decision.

The dataclass-slots decorator pass preserves source order. Decorators below
`dataclass` run first and suppress the check unless they are a proven
identity-preserving marker; decorators above it see the replacement class and
do not suppress. Direct-method analysis uses each method's first instance
parameter and ignores static methods. Open-state checks do not enter nested
executable scopes. Replacement-class checks scan nested executable scopes but
stop at nested `ClassDef` bodies: nested helper classes own their class cells,
so a helper's zero-argument `super()` is not an outer dataclass hazard.
Inference ambiguity is a reason to stay silent.

Inherited-layout analysis is transitive, including through a local dataclass
that already requests generated slots. `object` and proven empty-slot marker
bases are neutral; a single non-empty slotted lineage is safe; unslotted,
unknown, variable-length, or conflicting lineages suppress. Reverse analysis
suppresses local dataclass bases only when a direct multiple-inheritance shape
would combine more than one prospectively non-empty slot lineage. A local
dataclass that is itself eligible for R9111 is treated as prospectively
slotted, allowing a safe single-inheritance chain to report every missing
declaration in one run. The checker never imports or executes the linted
program and never mutates its AST.

`SuppressionCommentChecker` is token-based rather than AST-based: it inspects
comment tokens to find suppression pragmas and the explanations that may
accompany them, because a bare pragma carries no node in the abstract syntax
tree to attach a check to.

Its Ruff grammar follows Ruff 0.16.0:

- Bare `noqa` is case-insensitive, including when it follows code on the same
  line. The file-level `ruff: noqa` and `flake8: noqa` aliases are
  case-sensitive and must occupy standalone comments; they accept blanket
  suppression or rule-code lists.
- `ruff: ignore[...]`, `ruff: file-ignore[...]`, and `ruff: disable[...]`
  accept rule codes or preview rule names. Whitespace around the colon, before
  the opening bracket, and around comma separators is permitted, as is a
  trailing comma. Ruff keywords are case-sensitive; `file-ignore`, `disable`,
  and `enable` are recognized only in standalone comments, while `ignore` may
  follow code on the same line.
- `ruff: enable[...]` is a range terminator, not a suppression opener. It
  emits no C9106 diagnostic and is classified as a directive rather than
  explanatory prose.

A suppression opener is explained by non-directive prose in the same comment
segment, prose after a second `#`, or a standalone prose comment immediately
above it. Another pragma on the preceding line never explains it. This includes
`ruff: enable[...]`: the terminator is neutral, so it neither requires an
explanation nor supplies one for the next suppression.

The `ambrleaks` subpackage is a separate, standalone scanner exposed as its own
console script, split into four modules: `rules.py` pairs each detection
pattern with an optional entropy floor and allowlists, `scanner.py` walks
`.ambr` files line by line and attributes findings to their `# name:` test
block, `config.py` holds the `Config` model and its parser, and `cli.py`
provides the command-line entry point. Each module keeps a pure core behind a
thin filesystem boundary, so the reusable logic reads no files and never
consults the working directory: `scanner.py` pairs the pure `scan_text` with the
`scan_file` boundary, `config.py` pairs the pure `parse_config` with the
`read_config` boundary, and `cli.py` pairs `apply_baseline` with
`read_baseline`. Both scanner entry points take an explicit `base_dir`; the CLI
resolves it from the working directory once, at its own boundary, and injects
it into scanning, so path canonicalization stays deterministic. Suppression
lives in external configuration and baseline files rather than inline markers
because syrupy rewrites `.ambr` files wholesale on `--snapshot-update` and
would destroy any annotation.

### Observability

`ambrleaks` emits standard-library structured logs at its operational
boundaries — configuration load, scan (with a finding count), baseline
suppression (with a hit count), and scan failure — through the `ambrleaks`
logger. It follows the library convention of attaching a `NullHandler`, so the
logs are silent by default and never pollute the finding output; `-v` /
`--verbose` attaches a stderr handler at `INFO`, and an embedding process can
configure the `ambrleaks` logger to route the records anywhere. This keeps the
default run's user-facing contract unchanged: an exit status (`0` clean, `1`
findings remain, `2` a configuration, I/O, or decode error), one line per
finding on stdout (each tagged with its rule id), a finding-count summary and
any `ambrleaks: error:` message on stderr.

The tool deliberately stops there — no metrics backend, tracing, or alerting.
It is a synchronous, single-shot lint-style CLI (the class of `ruff`, `pylint`,
or `grep`) with no long-running process, network calls, or shared mutable state
to instrument; the boundary logs carry the bounded counts (findings, baseline
hits, failures) that a metrics layer would otherwise expose, and the invoking
shell or CI job captures the status and output. If `ambrleaks` ever grows a
long-running or service mode, revisit whether a metrics or tracing stack is
then warranted.

### Performance

The scan streams end to end and holds no whole-result collection in memory.
`discover` yields `.ambr` paths straight from the recursive walk (no sort, so
they arrive in filesystem order), and `_collect_findings` scans one file at a
time and applies the allowlist inline, so a file's findings surface before the
next file is read. Every mode consumes that stream incrementally:
`--write-baseline` (`write_baseline`) appends one JSON fingerprint entry per
finding as it arrives — building the array in a same-directory temporary file
that is atomically moved into place — and `--baseline` streams the findings
through `apply_baseline`, a generator that consumes one baselined occurrence
per matching fingerprint and yields the survivors immediately. Scanned and
suppressed counts are tallied incrementally for logging, never by materializing
or re-scanning. Baseline entries therefore follow discovery order rather than a
sorted order; occurrence semantics (a fingerprint recorded *n* times suppresses
the first *n* matches) are unchanged.

## The duplication command

`df12_python_lints/duplication/` implements `df12-duplication`. It is imported
by nothing else in the package, so the Pylint plugin and `ambrleaks` load none
of it.

| Module                        | Responsibility                                                                                  |
| ----------------------------- | ----------------------------------------------------------------------------------------------- |
| `cli.py`                      | argparse surface and the explicit context construction                                          |
| `context.py`                  | `RunContext`, the subprocess boundary and repository resolution                                 |
| `settings.py`                 | `[tool.nose]` validation                                                                        |
| `detector.py`                 | binary resolution, argument vector, containment arguments and report adaptation; writes nothing |
| `schema.py`                   | the consumed report fields and findings                                                         |
| `policy.py`                   | the pure domain: allow keys, whole-family matching, partition of findings                       |
| `allowlist.py`                | reading `[[tool.duplication_gate.allow]]` and recording entries                                 |
| `release.py`, `releases.json` | digest table, URL trust and archive verification                                                |
| `install.py`                  | explicit, digest-verified, binary-only provisioning                                             |
| `commands.py`                 | `check`, `allow` and `install`, the exit statuses and the neutral native-configuration files    |

Shared primitives live beside the package root so the Skylos command can reuse
them: `_manifest.py` (the comment-preserving edit transaction and its single
lock protocol: an advisory `flock` on a stable `.<name>.df12.lock` sidecar of
the resolved manifest, held across read, validation, edit and atomic
replacement), `_atomic.py`, `_validate.py`, `_errors.py`, `_log.py` (structured
boundary logging, silent unless `--verbose`) and `_pathglob.py`. The design
decisions are recorded in [ADR 002](adr-002-df12-duplication-command.md).

`_pathglob.py` supplies `PurePosixPath.full_match` on Python 3.12 by porting
CPython's `glob.translate` and `fnmatch` translation. On 3.13 and later it
delegates to the interpreter, so exception scope is the interpreter's own.
`tests/data/full_match_corpus.json` pins 3.14 answers for 4000 cases and a
Hypothesis differential test compares the port with the native method.
Regenerate the corpus with `tests/data/generate_full_match_corpus.py` on 3.13+.

The tests are layered: hermetic unit tests with a scripted subprocess boundary,
a handful of bounded tests against the real pinned binary (skipped unless
`NOSE_BIN` or `.tools/nose/nose` reports the pinned version; CI installs it with
`df12-duplication install`), and non-editable wheel installations for Python
3.12 and 3.14.

### Provenance

The implementation starts from the merged Episodic gate (`leynos/episodic` PR
276, merge commit `d9e5ac0d254f375e2986f52d91a3b88c117c833b`; ISC licence, same
copyright holder). It incorporates reviewed corrections from two unmerged
ports: Cuprum PR 510 (head `3b00cf719d64a1c11330d90755530739df86b347`:
empty-scan rejection through the detector's warning, repository-relative binary
resolution, and the unmatched-entry diagnostics) and Falcon Pachinko PR 225
(head `996b0f0d42c1f17493c9d39abcf2d5a69c074763`: explicit runtime contexts and
the checksummed official-release installer). Deliberately discarded: the
cyclopts front end and PEP 723 scripts, the `scripts` namespace imports, the
cargo-binstall provisioning, the donors' own file-walking source preflight
(`pathspec`), the per-file atomic-write module in favour of one shared helper,
and the duplication-specific lock.

## Local workflow

The public entrypoint for formatting, linting, typechecking, tests, and
spelling is `make all`. Narrower Make targets may be invoked when investigating
a specific failure, and changes should be reconciled with the aggregate gate
before being considered complete.

`make lint` runs Ruff, `interrogate --fail-under 100 $(PYTHON_TARGETS)` for
100% docstring coverage across `$(PYTHON_TARGETS)`, and Pylint.

Run `make audit` as the dependency vulnerability gate. It runs `pip-audit` for
Python dependencies, and Rust-enabled projects also run `cargo audit` from the
`rust_extension` crate directory.

## Automation scripts

The [Scripting standards](scripting-standards.md) document provides guidance
for adding or updating helper scripts. New and updated scripts are expected to
use `Cyclopts` for command-line interfaces, `cuprum` for typed and
catalogue-bound external command execution, `pathlib` for filesystem paths, and
`cmd-mox` for tests that mock external executables.

Script changes should update the scripting guide when they introduce a new
convention, command catalogue, testing pattern, or operational expectation that
future contributors need to follow.

## GitHub Actions

The generated repository includes GitHub Actions workflows and local composite
actions under `.github/`.

- `.github/workflows/ci.yml` runs on pushes to `main` and on pull requests. It
  sets up Python 3.13, installs `uv`, validates the generated `Makefile` with
  `mbake`, runs `make build`, `make check-fmt`, `make lint` (Ruff +
  `interrogate --fail-under 100 $(PYTHON_TARGETS)` + Pylint), `make typecheck`,
  `make spelling`, and `make audit` except for Dependabot pull requests via
  `if: github.actor != 'dependabot[bot]'`, then delegates coverage generation
  to the shared coverage action. When the Rust extension is enabled, it also
  sets up Rust, installs Rust lint and test tools, and passes
  `rust_extension/Cargo.toml` to coverage.
- Both coverage steps, in `ci.yml` and in `coverage-main.yml`, set
  `UV_PYTHON` to the version their job's `setup-python` step installs. The
  shared coverage action creates its venv with a bare `uv venv`, which would
  otherwise take whatever interpreter the latest uv discovers first, so pull
  requests and main could measure on different Pythons and the ratchet would
  compare unlike figures. `tests/test_coverage_interpreter.py` holds the two
  lanes to one pinned interpreter; it reads the workflows with PyYAML, which is
  a locked dev dependency for that reason.
- `.github/workflows/audit.yml` runs `make audit` against the default branch
  weekly as the compensating control for the Dependabot CI bypass.
- `.github/workflows/act-validation.yml` runs rendered workflow validation in a
  separate workflow. It installs `act`, checks Docker availability, and runs
  `make test WITH_ACT=1` outside the coverage path.
- `.github/workflows/release.yml` publishes wheels when a `v*.*.*` tag is
  pushed. It builds a pure Python wheel, creates a GitHub release with
  generated release notes, downloads wheel artefacts, and uploads them to the
  tag release.
- `.github/workflows/build-wheels.yml` is a reusable workflow for extension
  builds. It accepts a Python version and builds wheels across Linux, Windows,
  and macOS architectures via `.github/actions/build-wheels`.
- `.github/workflows/coverage-main.yml` runs on pushes to `main` and on
  dispatch, and is the only CodeScene caller. A
  `Check CodeScene token availability` step (id `codescene_token`) runs exactly
  `echo "available=${{ secrets.CS_ACCESS_TOKEN != '' }}" >> "$GITHUB_OUTPUT"`,
  with no `if:` and no `env`. The upload runs only when that output is `true`
  and `github.ref` is `refs/heads/main`, and takes the token as its
  `access-token` input, so no `env` holds it: the upload is a composite action
  whose nested steps inherit the calling step's `env`.
  `tests/test_codescene_publisher.py` holds the shape and requires the token to
  be named exactly at the check's command and the upload's input.
- `.github/workflows/get-codescene-sha.yml` is manually dispatched. It fetches
  the CodeScene coverage CLI installer, computes its SHA-256 digest, and writes
  the result to the `CODESCENE_CLI_SHA256` repository variable.
- `.github/actions/build-wheels` wraps `cibuildwheel` with `uvx` and uploads
  architecture-specific wheel artefacts.
- `.github/actions/pure-python-wheel` builds a pure Python wheel with
  `uv build --wheel` and uploads the resulting artefact.
- `.github/dependabot.yml` enables dependency update pull requests for GitHub
  Actions and Python packages. Rust-enabled projects also receive Cargo updates.

The `CS_ACCESS_TOKEN` secret must be configured when CodeScene coverage upload
is required. The `CODESCENE_CLI_SHA256` variable should be populated using the
refresh workflow, so CI can verify the downloaded CodeScene installer before
upload.

## Shared spelling configuration

Run `make spelling` to enforce en-GB-oxendict spelling. The gate regenerates
`typos.toml` on every run from the live shared dictionary in
`leynos/agent-helper-scripts` and the `typos.local.toml` overlay, so a word
added to the shared dictionary needs no change here. Because the dictionary is
live, `typos.toml` is never drift checked in continuous integration. Add only
narrow project-specific terms and exclusions to `typos.local.toml`; never edit
generated `typos.toml` by hand.

`TYPOS_CONFIG_BUILDER_VERSION` in the `Makefile` pins the
`typos-config-builder` release the gate runs (currently `v0.1.3`). Raise it
together with the regenerated `typos.toml`, never on its own. The builder
requires Python 3.14 or newer, so the target passes `--python 3.14` and `uv`
fetches that interpreter when the host lacks one; this is separate from the
Python 3.13 environment the CI job sets up for the repository's own tooling.

## Verification tiers

The test suite is layered, so each verification tier runs at the right cadence:

- **Example tests** (`make test`) run the pytest suites, including the
  Hypothesis property tests in `tests/test_properties.py`. The properties cover
  the checkers' decision kernels across whole input families — chain lengths,
  guard-run lengths, literal nesting, and generated pragma comments — and any
  shrunk counterexample should be promoted to a named regression test beside
  the checker's example suite.
- **Symbolic model checks** (`make crosshair`) run CrossHair over the
  pure selection kernels in `df12_python_lints/_chains.py`, which carry PEP 316
  contracts (`pre:`/`post:` docstring clauses). The `pre:` clauses deliberately
  bound the symbolic domain — short chains drawn from a two-symbol alphabet —
  so the search can *confirm* every `post:` clause over all paths rather than
  merely exhaust its budget. `tests/test_crosshair.py` requires those four
  confirmations (one in `repeated_subject`, three in `narrowing_prefix`) and
  treats a "Not confirmed" verdict as a failure; the bounds scope the proof
  only, while the Hypothesis tier covers the unbounded runtime domain. The gate
  is opt-in; run it on changes to the kernels rather than on every push.
- **End-to-end PyPy tests** (part of `make test`, `tests/test_e2e_pypy.py`)
  lint fixture modules with the pinned Pylint on managed PyPy and the plugin
  loaded, proving every checker fires — and stays silent on clean code — under
  the same PyPy-backed Pylint that the project's own lint gate uses.
  `PYLINT_PYTHON` and `PYLINT_VERSION` are read from the Makefile so the two
  cannot drift apart.

## Markdown formatting

Markdown follows the estate's `markdown-formatting-baseline` rule.

- `make fmt` rewrites Markdown with
  `mdtablefix --in-place --git --include-untracked --wrap --renumber --breaks
  --ellipsis --fences`,
  then runs `markdownlint-cli2 --fix "**/*.md"`.
- `make check-fmt` runs the same mdtablefix command with `--check` in place of
  `--in-place`, and fails when any file would change.
- `--git --include-untracked` selects the Markdown files Git tracks plus the
  untracked files Git does not ignore, so a new document is checked before it
  is staged.
- `.markdownlint-cli2.jsonc` carries the canonical markdownlint configuration.
  Keep its `config` entries and `ignores` globs; add repository-specific rules
  or globs beside them.
- CI installs mdtablefix 0.6.1 with the shared `install-mdtablefix` action
  before `make check-fmt`, and lints Markdown with
  `DavidAnson/markdownlint-cli2-action` over `**/*.md`.

Install mdtablefix 0.6.1 or later locally with
`cargo binstall --no-confirm mdtablefix@0.6.1`, or
`cargo install --locked mdtablefix@0.6.1`. Install markdownlint-cli2 with
`bun add --global markdownlint-cli2` or
`npm install --global markdownlint-cli2`.
