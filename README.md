# 🔎 df12-python-lints

*Opinionated pylint checkers for code that says what it means.*

A pylint plugin encoding the df12 house style: prefer `match` statements over
imperative type dispatch, make assertions explain themselves, and never silence
a diagnostic without saying why. It also ships `ambrleaks`, a scanner that
catches unredacted values hiding in syrupy snapshots.

______________________________________________________________________

## Why df12-python-lints?

Review feedback is cheapest when a machine gives it before a human has to:

- **Structure over ceremony**: `isinstance` ladders and constant
  comparison chains become `match`/`case`, which states the accepted shapes and
  values directly.
- **Assertions that testify**: a bare `assert` failure echoes an
  expression; an assert with a message names the violated expectation —
  invaluable when a property test shrinks to a counterexample.
- **No silent suppressions**: every `noqa`, `pylint: disable`, or
  `type: ignore` must record a reason the next reader can audit.
- **Snapshots kept honest**: big inline expected values move into syrupy
  snapshots, and the snapshots themselves are swept for hex ids, emails, URLs,
  and absolute paths that should have been redacted.

______________________________________________________________________

## Quick start

### Installation

```bash
uv add --dev df12-python-lints
```

### Basic usage

Load the plugin in `pyproject.toml`:

```toml
[tool.pylint.main]
load-plugins = ["df12_python_lints"]
```

Then run pylint as usual:

```bash
pylint my_package tests
```

A dispatch chain like this:

```python
if isinstance(value, dict):
    handle_mapping(value)
elif isinstance(value, list):
    handle_sequence(value)
```

is reported as:

```text
R9101: Type dispatch on 'value' would be clearer as a match statement
(prefer-structural-pattern-matching)
```

To sweep syrupy snapshots, install the package as a tool and point `ambrleaks`
at your tests:

```bash
uv tool install df12-python-lints
ambrleaks tests
```

______________________________________________________________________

## Features

Twelve pylint messages:

- `prefer-structural-pattern-matching` (R9101) — `isinstance` dispatch on
  one subject should be a `match` statement with class patterns.
- `assert-missing-message` (C9102) — every `assert` carries a failure
  message naming the violated expectation.
- `prefer-match-over-constant-chain` (R9103) — `if`/`elif` chains
  comparing one subject with constants, enum members, or literals should be a
  `match` statement over an enumeration.
- `trivial-attribute-wrapper` (R9104) and `trivial-alias-wrapper`
  (R9110) — functions with no logic beyond attribute access, a proxied call, or
  forwarding to another function add a name without adding behaviour.
- `reexport-by-assignment` (C9105) — re-export with
  `from ... import ... as ...` rather than assignment.
- `lint-suppression-without-explanation` (C9106) and
  `typecheck-suppression-without-explanation` (C9107) — suppression pragmas
  must record a reason.
- `prefer-snapshot-assertion` (R9108) and `prefer-snapshot-substring`
  (R9109) — tests asserting against large inline literals or repeatedly probing
  substrings should use a syrupy snapshot.
- `prefer-type-statement` (R9111) — module-level type aliases should use
  the PEP 695 `type` statement on a 3.12+ baseline.
- `redundant-future-annotations` (C9112) — `from __future__ import annotations`
  should be removed on a 3.14+ baseline, where deferred evaluation is the
  default.

Both baseline-gated messages respect pylint's `py-version` option.

And one companion tool:

- `ambrleaks` — scans syrupy `.ambr` snapshot files for unredacted hex
  strings, UUIDs, emails, phone numbers, URLs, and absolute paths, with entropy
  gating, allowlists, and a baseline that survives snapshot regeneration.

______________________________________________________________________

## Learn more

- [Users' Guide](docs/users-guide.md) — every checker, every rule, and
  how to suppress findings without touching your snapshots
- [Developers' Guide](docs/developers-guide.md) — contributing and
  development workflow
- [Documentation contents](docs/contents.md) — the full documentation set

______________________________________________________________________

## Licence

ISC — see [LICENSE](LICENSE) for details.

______________________________________________________________________

## Contributing

Contributions welcome! Please see [AGENTS.md](AGENTS.md) for guidelines, and run
`make all` before proposing a change.
