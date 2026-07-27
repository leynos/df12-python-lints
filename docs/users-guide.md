# df12-python-lints Users' Guide

## Provided Lints

The package is a pylint plugin. Load it from a pylint configuration:

```toml
[tool.pylint.main]
load-plugins = ["df12_python_lints"]
```

or from the command line:

```bash
pylint --load-plugins=df12_python_lints my_package
```

Loading the plugin registers thirteen messages.

### `prefer-structural-pattern-matching` (R9101)

Reports `isinstance` dispatch on a single subject, in either of two shapes:

- an `if`/`elif` chain whose branch tests call `isinstance` on the same
  subject.
- consecutive guard `if` statements (no `else`, each body ending in
  `return`, `raise`, `continue`, or `break`) whose tests call `isinstance` on
  the same subject.

Both decompose the subject's shape imperatively. A `match` statement with class
patterns states the accepted shapes directly:

```python
match value:
    case dict():
        handle_mapping(value)
    case list():
        handle_sequence(value)
```

### `assert-missing-message` (C9102)

Reports `assert` statements without a failure message. A bare `assert` that
fails reports only the falsy expression; attaching a message names the violated
expectation. This matters most when a property-based test shrinks to a minimal
counterexample and the reader must work out which invariant broke:

```python
assert _is_pinned_action(ref, path), "exact path pin must match"
```

The checker applies to every `assert` it sees. Projects that only want it
enforced for test suites should enable the message for their test paths in the
pylint configuration.

### `prefer-match-over-constant-chain` (R9103)

Reports `if`/`elif` chains where every branch compares one subject with
constants, enumeration members, or literals — by equality, by membership in a
literal collection, or by an `or` combination of such comparisons. Such chains
are clearer as a `match` statement over an enumeration of the accepted values:

```python
match colour:
    case Colour.RED:
        stop()
    case Colour.AMBER | Colour.GREEN:
        go()
```

Branches that compare against variables, call results, or name-bound containers
disqualify the chain, as do ordering comparisons because they cannot become
`case` patterns.

### `trivial-attribute-wrapper` (R9104)

Reports functions with no logic beyond forwarding: a body that only returns an
attribute of one of the function's parameters, or calls through such an
attribute while passing the function's own parameters along unchanged:

```python
def get_name(user):
    return user.profile.name


def send(self, message):
    return self._client.send(message)
```

Access the attribute or bound method directly at the call site, or expose it as
a property when the indirection is deliberate. Decorated functions are exempt
because decorators such as `property` or `functools.cache` make the forwarding
deliberate. Supplying new arguments, transforming an argument, or adding any
further statement disqualifies the function, as does reordering, repeating, or
omitting a parameter — those adapt the call, which is behaviour.

### `trivial-alias-wrapper` (R9110)

Reports functions whose body only calls another module-level or imported
function with the wrapper's own parameters forwarded unchanged:

```python
def foo(qux):
    return bar(qux)
```

Call the target directly, or alias it with `from mymodule import bar as foo`
when a different name is wanted. The checker only fires when the target
resolves to a module-level function, or to an import that astroid infers to a
function: calling through a parameter is higher-order code, and wrapping a
class constructor or a builtin — local or imported — is a factory with a
deliberate name, so neither is reported. Decorated functions are exempt, as for
R9104.

### `reexport-by-assignment` (C9105)

Reports module-level names bound by assigning an imported name or an attribute
reached through an imported module:

```python
import os.path

join = os.path.join  # flagged
```

Use `from os.path import join` instead, so
importers and type checkers see a real import binding. Call results, aliases of
names defined in the same module, and assignments inside functions are not
flagged.

### Suppressions without explanations (C9106, C9107)

Two checkers require every suppression pragma to record a reason:

- `lint-suppression-without-explanation` (C9106) covers lint pragmas:
  `noqa`, `ruff: noqa`, and `pylint: disable`.
- `typecheck-suppression-without-explanation` (C9107) covers type-check
  pragmas: `type: ignore`, `pyright: ignore`, `ty: ignore`, and `mypy:`.

An explanation may sit after a second `#` in the same comment, as trailing
prose in the pragma segment, or as a standalone comment on the line above:

```python
value = eval(text)  # noqa: S307  # input is a vetted config literal
```

A pragma on the preceding line does not count as an explanation.

### Snapshot-worthy assertions (R9108, R9109)

Two checkers report assertions in `test_`-named functions that would carry
their contract more clearly as a syrupy snapshot:

- `prefer-snapshot-assertion` (R9108) reports equality against a large
  inline literal: a collection with eight or more constant or name leaves, or a
  string with three or more newlines or 200 or more characters (including one
  wrapped in `textwrap.dedent`).
- `prefer-snapshot-substring` (R9109) reports three or more
  `assert "..." in subject` probes against the same subject in one test.

```python
def test_report(report, snapshot):
    assert report.render() == snapshot
```

Comparisons with names (an `expected` fixture or parameter), small literals,
and asserts outside test functions are never reported. Leaf counting works on
the AST, so reformatting a literal does not change whether it fires.

### `prefer-slots-for-dataclass` (R9111)

Standard-library dataclasses that describe closed instance state should request
generated slots:

```python
import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class Coordinate:
    latitude: float
    longitude: float
```

The rule recognizes the real `dataclasses.dataclass` through lexical import
bindings, including module and direct-import aliases. A local function named
`dataclass`, a shadowed import, pydantic, attrs, msgspec, and
`dataclass_transform`-based frameworks are outside its scope.

Only a lexically visible `slots=True` satisfies the generated-layout form.
`slots=False`, `slots=1`, a named constant, or `**options` still report because
the class layout should not vary through configuration or indirection. A local
runtime assignment to `__slots__` also satisfies the rule, whatever layout it
names; an annotation without a value does not. Use `weakref_slot=True` alongside
`slots=True` when instances require weak references.[^dataclass-slots]

The checker holds its tongue when the source contains hard evidence that
generated slots would be unsafe, ineffective, or misleading:

- a direct instance method requires dictionary-backed or undeclared state
  through `cached_property`, `__dict__`, `vars`, dynamic attribute operations,
  or assignment to an undeclared instance attribute;
- the class is an explicit extension boundary through `abc.ABC`,
  `typing.Protocol`, `abstractmethod`, `__init_subclass__`, an explicit
  metaclass, or other class-header keywords;
- a decorator below `dataclass` might retain the original class object;
- a direct method uses zero-argument `super()` or closes over `__class__` on
  the supported Python 3.12 and 3.13 runtimes; or
- an inherited layout is unknown, already supplies an instance dictionary,
  cannot accept non-empty slots, or would create conflicting non-empty slot
  lineages through multiple inheritance.

Assignments to actual dataclass fields, including `field(init=False)` values
populated in `__post_init__`, and to explicit inherited slots remain
slot-compatible. Plain class attributes, `ClassVar`, and `InitVar` declarations
do not create instance storage. An outer decorator is also safe because it sees
the replacement class returned by `dataclass(slots=True)`.

Public naming, export through `__all__`, and the absence of `typing.final` do
not suppress the message. Keep an intentionally open or compatibility-bound
class unslotted with a narrow, explained suppression beside the decorator:

```python
# Compatibility: consumers attach adapter state dynamically.
@dataclasses.dataclass  # pylint: disable=prefer-slots-for-dataclass
class LegacyRecord:
    value: str
```

The `lint-suppression-without-explanation` rule requires that local reason. See
Python's dataclass and slot-layout documentation for the replacement-class and
inheritance constraints.[^dataclass-slots][^data-model-slots]

### `prefer-type-statement` (R9112)

Module-level type aliases should use the PEP 695 `type` statement, which names
the intent and defers evaluation of the aliased expression:

```python
import collections.abc as cabc

Clock = cabc.Callable[[], dt.datetime]    # flagged
Pair: TypeAlias = "tuple[int, int]"       # flagged

type Clock = cabc.Callable[[], dt.datetime]  # preferred
```

A plain assignment counts as an alias when its value subscripts a construct from
`typing`, `typing_extensions`, or `collections.abc` (resolved through the
module's imports, so aliased imports such as `import collections.abc as cabc`
are recognized), or an unshadowed builtin generic such as `dict[str, int]`.
`TypeAlias`-annotated assignments always count. Bindings inside functions,
subscripts of runtime values, and unannotated PEP 604 unions (`X = int | str`)
are never reported.

The check respects pylint's `py-version` option and stays silent when the
configured baseline predates Python 3.12, the first release with the `type`
statement.

### `redundant-future-annotations` (C9112)

`from __future__ import annotations` should be removed once the project
baseline reaches Python 3.14. Deferred evaluation of annotations is the default
there, and the future import is not a harmless no-op: it forces the older
stringified semantics instead of 3.14's lazily evaluated annotation objects,
which runtime annotation consumers can observe.

The check respects pylint's `py-version` option; projects whose configured
baseline still includes 3.13 or older keep the import without noise.

[^dataclass-slots]: [Python 3.12 `dataclasses.dataclass`](https://docs.python.org/3.12/library/dataclasses.html#dataclasses.dataclass)
[^data-model-slots]: [Python data model notes on `__slots__`](https://docs.python.org/3.12/reference/datamodel.html#slots)

## The ambrleaks Snapshot Scanner

The package also ships `ambrleaks`, a standalone scanner for syrupy `.ambr`
snapshot files. Pylint only lints Python modules, so unredacted values inside
snapshot files need a file-level tool. Install it as a standalone tool or run
it from the project environment:

```bash
uv tool install df12-python-lints
ambrleaks tests
```

The scanner walks the given paths for `.ambr` files and reports values that
should have been redacted with a syrupy `matcher` before the snapshot was
recorded, attributing each finding to its `# name:` test block. Rules follow
the gitleaks model — a strict pattern, an optional Shannon-entropy floor, and
built-in allowlists:

| Rule                    | Detects                                                                  | Default |
| ----------------------- | ------------------------------------------------------------------------ | ------- |
| `snapshot-hex`          | Hex strings of 32+ characters, entropy-gated                             | on      |
| `snapshot-uuid`         | UUID literals                                                            | on      |
| `snapshot-email`        | Email addresses (RFC 2606 domains allowlisted)                           | on      |
| `snapshot-phone`        | E.164 numbers with a leading `+`                                         | off     |
| `snapshot-url`          | `http(s)` URLs (`example.com`, loopback, and namespace URIs allowlisted) | on      |
| `snapshot-posix-path`   | Absolute POSIX paths of three or more segments                           | on      |
| `snapshot-windows-path` | Drive-letter and UNC paths                                               | on      |

Each finding's value is masked by default (for example `a***************o`) so
reports can be shared safely, such as in CI logs; pass `--show-values` to print
the full unredacted value. Pass `-v` / `--verbose` to log the configuration,
scan, and baseline boundaries to stderr; these logs are silent otherwise.

Exit status is `0` for a clean tree, `1` when findings remain, and `2` for a
configuration, I/O, TOML, JSON, or decoding error.

### Suppressing Findings

Inline markers cannot be used: syrupy rewrites `.ambr` files wholesale on
`pytest --snapshot-update`, destroying any annotation. All suppression
therefore lives outside the snapshot and survives regeneration:

- **Configuration** — `ambrleaks.toml` (or `.ambrleaks.toml`) in the
  working directory, or `--config PATH`:

  ```toml
  [rules.snapshot-phone]
  enabled = true

  [allowlist]
  values = ['@realcorp\.example$']  # regexes matched against the value
  tests = ["test_legacy_*"]         # globs matched against # name: ids
  paths = ["tests/fixtures/*"]      # globs matched against file paths
  ```

- **Baseline** — grandfather existing findings while failing new ones:

  ```bash
  ambrleaks --write-baseline .ambrleaks-baseline.json
  ambrleaks --baseline .ambrleaks-baseline.json
  ```

  Fingerprints hash the file path, test name, rule, and value — not the line
  number — so a baseline survives blocks moving when snapshots are regenerated.
  Baselines are written as findings are scanned (one entry per occurrence), so
  entries follow scan order rather than a sorted order.

The lasting fix is redaction at record time with syrupy's
`matcher=path_type(...)` (including its regex `replacer` idiom for values
embedded in strings), then `pytest --snapshot-update`.

## Quality Gates

Generated projects use `make all` as the standard local quality gate. It runs
these targets in order:

- `build`: create the local virtual environment and install development
  dependencies with `uv sync --group dev`.
- `check-fmt`: check Ruff formatting for Python sources and, when Rust is
  enabled, `cargo fmt` for the Rust extension.
- `lint`: run `lint-python` and, when Rust is enabled, `lint-rust`.
- `typecheck`: run `ty check`.
- `test`: run pytest and, when Rust is enabled, Rust tests.
- `spelling`: generate shared en-GB-oxendict policy and check Markdown with the
  pinned `typos` version.
- `audit`: run `pip-audit` and, when Rust is enabled, `cargo audit`.

The `lint-python` target runs Ruff, then Interrogate with
`interrogate --fail-under 100 $(PYTHON_TARGETS)` to enforce 100% docstring
coverage for the Python targets, then Pylint via a PyPy-backed runner. The
Pylint runner is installed through `uv tool run` from the pinned
`pylint-pypy-shim` repository.

The spelling target keeps an ignored shared-base cache and a tracked generated
`typos.toml`. Run `make spelling` directly when updating documentation; a
populated cache remains usable when the shared source is temporarily offline.

Pytest discovery is limited to the top-level `tests/` tree. Keep generated
project unit tests there rather than in package module directories or
`unittests/` subdirectories, because CI coverage runs through xdist-backed
SlipCover support.

When the Rust extension is enabled, `lint-rust` runs:

- `cargo doc` with warnings denied;
- `cargo clippy` with the generated Clippy configuration; and
- Whitaker with `whitaker --all`.

The generated Makefile installs Whitaker on demand before local Rust linting
when it is not already available.

## Dependency Auditing

Run `make audit` to check generated project dependencies for known
vulnerabilities. All generated projects run `pip-audit` against the Python
environment created by `uv sync --group dev`. CI skips `make audit` for
Dependabot pull requests; a weekly scheduled audit on the default branch is the
compensating control. Rust-enabled projects also run `cargo audit` from the
`rust_extension` crate directory.

## Rust Test Behaviour

Rust-enabled projects use `cargo nextest run` when `cargo-nextest` is
available. If `cargo-nextest` is not installed, the generated `test` target
falls back to `cargo test`. Rust documentation tests still run through
`cargo test --doc`.

If cargo is missing from the local environment, generated Rust test targets
fail early with a clear error instead of falling through to an unusable `cargo`
invocation.

## Local GitHub Actions Validation

The generated Makefile supports optional local workflow validation using
[`act`](https://github.com/nektos/act). When `act` is installed and Docker is
available, pass `WITH_ACT=1` to the `test` target:

```bash
make test WITH_ACT=1
```

This sets `RUN_ACT_VALIDATION=1` for the pytest invocation, enabling the
act-based integration tests that run the generated CI workflow locally. Omitting
`WITH_ACT` (or setting it to `0`) skips act validation; the rest of the test
suite runs unchanged.

## Cleaning Local State

Run `make clean` to remove local build and cache outputs, including `.venv`,
`.uv-cache`, `.uv-tools`, Python cache directories, coverage outputs, and Rust
`target` output when the Rust extension is enabled.
