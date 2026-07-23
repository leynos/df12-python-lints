# df12-python-lints

A pylint plugin providing df12 house-style checkers:

- `prefer-structural-pattern-matching` (R9101) — `isinstance` dispatch on
  one subject should be a `match` statement with class patterns.
- `assert-missing-message` (C9102) — every `assert` should carry a failure
  message naming the violated expectation.
- `prefer-match-over-constant-chain` (R9103) — `if`/`elif` chains comparing
  one subject with constants, enum members, or literals should be a `match`
  statement over an enumeration.

Load the plugin with `pylint --load-plugins=df12_python_lints`, or from
`pyproject.toml`:

```toml
[tool.pylint.main]
load-plugins = ["df12_python_lints"]
```

See the [users' guide](docs/users-guide.md) for details of each checker.
