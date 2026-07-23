# df12-python-lints

A pylint plugin providing df12 house-style checkers:

- `prefer-structural-pattern-matching` (R9101) — `isinstance` dispatch on
  one subject should be a `match` statement with class patterns.
- `assert-missing-message` (C9102) — every `assert` should carry a failure
  message naming the violated expectation.
- `prefer-match-over-constant-chain` (R9103) — `if`/`elif` chains comparing
  one subject with constants, enum members, or literals should be a `match`
  statement over an enumeration.
- `trivial-attribute-wrapper` (R9104) — functions with no logic beyond
  attribute access or a proxied call should be removed or made properties.
- `reexport-by-assignment` (C9105) — re-export with
  `from ... import ... as ...` rather than assignment.
- `lint-suppression-without-explanation` (C9106) and
  `typecheck-suppression-without-explanation` (C9107) — every suppression
  pragma must record a reason.
- `prefer-snapshot-assertion` (R9108) and `prefer-snapshot-substring`
  (R9109) — tests asserting against large inline literals or repeatedly probing
  substrings should use a syrupy snapshot.

It also ships `ambrleaks`, a standalone scanner (installable with
`uv tool install df12-python-lints`) that finds unredacted hex strings, UUIDs,
emails, phone numbers, URLs, and absolute paths in syrupy `.ambr` snapshot
files, with config- and baseline-based suppression that survives snapshot
regeneration.

Load the plugin with `pylint --load-plugins=df12_python_lints`, or from
`pyproject.toml`:

```toml
[tool.pylint.main]
load-plugins = ["df12_python_lints"]
```

See the [users' guide](docs/users-guide.md) for details of each checker.
