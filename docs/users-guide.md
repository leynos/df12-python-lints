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

Use `from os.path import join` instead, so importers and type checkers see a
real import binding. Call results, aliases of names defined in the same module,
and assignments inside functions are not flagged.

### Suppressions without explanations (C9106, C9107)

Two checkers require every suppression pragma to record a reason:

- `lint-suppression-without-explanation` (C9106) covers lint pragmas:
  `noqa`, `ruff: noqa`, `flake8: noqa`, `ruff: ignore`, `ruff: file-ignore`,
  the range directive `ruff: disable`, and `pylint: disable`.
- `typecheck-suppression-without-explanation` (C9107) covers type-check
  pragmas: `type: ignore`, `pyright: ignore`, `ty: ignore`, and `mypy:`.

Bare `noqa`, including inline `noqa` after code, is case-insensitive. The
`ruff: noqa` and `flake8: noqa` file-level aliases have case-sensitive prefixes
and must occupy standalone comments. Other Ruff directive keywords are also
case-sensitive: `ruff: file-ignore`, `ruff: disable`, and `ruff: enable` must
occupy a standalone comment; only `ruff: ignore` may follow code on the same
line.

`ruff: enable[...]` ends a suppression range rather than suppressing a
diagnostic itself. It therefore needs no explanation and does not count as an
explanation for a suppression on the next line.

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
runtime assignment to `__slots__` suppresses R9111 only when the checker
validates a valid, locally resolved slot value. Annotation-only declarations,
invalid values, unresolved names, and ambiguous values do not qualify. Use
`weakref_slot=True` alongside `slots=True` when instances require weak
references.[^1]

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
inheritance constraints.[^1][^2]

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

[^1]: [Python 3.12 `dataclasses.dataclass`](https://docs.python.org/3.12/library/dataclasses.html#dataclasses.dataclass)
[^2]: [Python data model notes on `__slots__`](https://docs.python.org/3.12/reference/datamodel.html#slots)

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

## The df12-duplication Gate

The package ships `df12-duplication`, a blocking code-duplication gate over the
[nose](https://github.com/corca-ai/nose)
detector. It is unrelated to the Python `nose` test framework, which is not a
dependency. The command runs the pinned detector with the policy in the
project's `pyproject.toml`, and fails while any duplication family is not
covered by a reasoned exception.

```bash
df12-duplication check --repository .
df12-duplication allow --repository . \
  --member 'src/a.py::parse' \
  --member 'src/b.py::parse' \
  --member 'src/c.py::parse' \
  --reason 'These independently versioned entry points deliberately retain this structure.'
df12-duplication install --repository .
```

`--repository` defaults to the invocation directory and selects the target
`pyproject.toml`. `--timeout <seconds>` (default 120) bounds each detector
invocation, including the version check that `check` runs and the one `install`
uses to prove the binary; a timeout is a failed analysis and exits `2`. The
command never derives the target from where it is installed, never changes the
process working directory, and ignores `PYTHONPATH`. Relative paths (the roots,
and a relative `--binary`) resolve against the selected repository. `--version`
prints the package version, and `--help` lists every option. `--verbose`
(before the subcommand) logs one record per operation and one per subprocess or
download to standard error.

### Exit status

- `0`: no blocking findings.
- `1`: at least one family is not covered by an exception.
- `2`: invalid invocation or configuration, or a failed analysis: a missing or
  wrong binary, a non-zero detector exit, a timeout, malformed JSON or schema,
  a missing root, or a scan whose roots contain no supported source. None of
  these can produce a green gate. Expected failures print one line, not a
  traceback.

### Policy in `[tool.nose]`

```toml
[tool.nose]
version = "0.20.0"            # the detector release the binary must report
roots = ["src"]               # all roots go to one detector query
mode = "syntax,semantic,near" # pinned, so nose defaults cannot widen the scan
min-size = 24                 # smallest reported unit, in nose IL tokens
surface = "all"               # "default" keeps nose's dashboard only
top = 30                      # report budget; 0 asks for every family
exclude = ["tests/**"]        # gitignore-style globs
```

Roots must be repository-relative, must exist and must stay inside the checkout.
`top` is the number of ranked families nose returns, and omitting it keeps
nose's own view size (30 in 0.20.0).

### Reasoned exceptions

```toml
[[tool.duplication_gate.allow]]
members = ["src/a.py::parse", "src/b.py::parse"]
reason = "These entry points are versioned independently."
```

An entry uses `unit = "..."` for one location or `members = [...]` for two or
more, and always records a reason. A key is a repository-relative path glob,
optionally followed by `::name` to require nose's unit name. Globs follow
`PurePosixPath.full_match`: `*` stays within one path segment and `**` spans
segments. A `::name` key never matches a fragment that nose reports without a
name.

One entry must cover **every** location of a family. Several partial entries
are never combined, so a third, unlisted copy makes the family block again.
Keys carry no line numbers, so moving code does not invalidate an entry.

`allow` accepts one or many `--member` values (the legacy `--first` and repeated
`--second` options still work), rejects a blank reason or malformed key before
touching the file, preserves comments, unrelated tables and file permissions,
and is idempotent: repeating a member set updates its reason instead of adding
a duplicate. Editing is serialized with an advisory lock, so concurrent `allow`
runs (and `df12-skylos allow` runs) on one manifest do not lose each other's
changes. The lock coordinates participating commands only, not arbitrary
editors, and needs POSIX `flock`: Linux and macOS. Native Windows is not
supported for authoring, and the command refuses rather than editing without a
lock. `check` has no such requirement.

### What the report means

- An allow entry that matched nothing prints *unmatched in this scan*. Ranking,
  the report budget, thresholds, file selection, or a family that grew can all
  cause this. Review it; the command never deletes or widens an exception.
- Exceptions are applied after nose ranks and caps its report, so allowed
  families consume places in the budget. When the detector returns fewer
  families than it found, the command warns, and if nothing blocks it **fails
  closed with status `2`**: a capped report that shows nothing blocking cannot
  prove the unseen families clean. Set `top = 0` (every family) or raise `top`
  above the total, and adjudicate the families that become visible.

### The detector binary

`check` never downloads anything. It looks for the binary at `--binary`, else
`$NOSE_BIN`, else `.tools/nose/nose` in the repository, else `nose` on `PATH`,
and requires it to report exactly `nose <version>`.

`install` fetches the release archive named by `[tool.nose].version` from
`github.com/corca-ai/nose`, verifies its SHA-256 against the digest table
shipped in the package, proves the executable reports the pinned version from a
scratch directory, and only then moves it into place atomically. It refuses
unsupported platforms (Linux with glibc and macOS, on x86-64 or AArch64), never
compiles anything and never runs an installer script. A version without
approved digests is rejected.

### Native nose configuration cannot add a second policy

nose reads `nose.toml`, `.nose.toml` and `nose.ignore.json` from its working
directory. The command passes an empty configuration and an empty ignore file
on every query, so only `[tool.nose]` and the allow entries apply. Inline
`nose-ignore` comments and `.gitignore` files inside the scanned roots are
source-level selection that nose applies itself, and remain in effect.

### Installation

```bash
# Provisioned and pinned, as a Makefile would run it (see the migration guide).
uv tool run --from 'git+https://github.com/leynos/df12-python-lints.git@<40-hex-commit>' \
  df12-duplication check --repository .
```

The command needs `tomlkit`, which Pylint already pulls in. The `duplication`
extra (`pip install 'df12-python-lints[duplication]'`) names that requirement
explicitly. Python 3.12 and later are supported: the `PurePosixPath.full_match`
semantics of Python 3.13 are provided on 3.12 by a tested port, and the Pylint
plugin and `ambrleaks` never import any of this. See the
[duplication gate migration guide](duplication-gate-migration.md) for the
consumer migration.

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
- `spelling`: check Markdown against the shared en-GB-oxendict dictionary using
  the shared spelling gate.
- `audit`: run `pip-audit` and, when Rust is enabled, `cargo audit`.

The `lint-python` target runs Ruff, then Interrogate with
`interrogate --fail-under 100 $(PYTHON_TARGETS)` to enforce 100% docstring
coverage for the Python targets, then a pinned Pylint (`PYLINT_VERSION`) on
uv-managed PyPy 3.12 (`PYLINT_PYTHON`), installed through `uv tool run`.
`syntax-error` stays enabled, so a module that PyPy cannot parse fails the lint
rather than being skipped.

The spelling target regenerates the tracked `typos.toml` from the live shared
dictionary and the `typos.local.toml` overlay on every run, so `typos.toml` is
never drift checked in CI. Run `make spelling` directly when updating
documentation, and record narrow project-specific exceptions in
`typos.local.toml`. The spelling gate itself needs Python 3.14 or newer: the
target passes `--python 3.14` to `uv`, which fetches that interpreter when the
host lacks one, independently of the Python version the project under test uses.

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
