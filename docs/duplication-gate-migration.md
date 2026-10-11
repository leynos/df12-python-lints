# Migrating to df12-duplication

This guide moves a repository that vendors the nose duplication gate (the
`scripts/duplication_gate.py` family from the Episodic adoption) onto the
installed `df12-duplication` command. Application policy stays in the
repository: `[tool.nose]`, the reasoned exceptions and their reasons. The gate
implementation, its exception editor, its installer and the copied test suites
move into this package.

## Command changes

| Vendored interface                          | Installed command                                              |
| ------------------------------------------- | -------------------------------------------------------------- |
| `uv run scripts/duplication_gate.py check`  | `df12-duplication check --repository .`                        |
| `... allow --first A --second B --reason R` | `df12-duplication allow --member A --member B --reason R`      |
| `make install-nose` (cargo-binstall)        | `df12-duplication install --repository .`                      |
| `NOSE_BIN=path`                             | `--binary path` or `NOSE_BIN=path`, relative to `--repository` |

`--first` and repeated `--second` remain as compatibility aliases. Do not keep
passing members through a single Make variable: repeat `--member` instead, so
one or many members need no splitting.

## Behaviour corrections

- A scan with no supported source, a missing root, a wrong binary, a timeout or
  a malformed report exits `2` and never passes.
- The stale-entry message is now *unmatched in this scan*, and explains that
  ranking, thresholds, selection or a grown family can cause it. Entries are
  never deleted or widened automatically.
- A saturated report budget with nothing blocking now fails closed (status 2)
  instead of passing, because unseen families would go unchecked. Migrating a
  repository whose report is saturated (Episodic returns 30 of 161 families)
  needs `top = 0` and adjudication of the newly visible families.
- Ambient `nose.toml`, `.nose.toml` and `nose.ignore.json` files are ignored.
- One lock protocol covers `allow` for both df12 commands.

## Makefile and CI shape

```make
DF12_PYTHON_LINTS_REF = <40-hex commit>
DUPLICATION = $(UV_GATE) tool --from \
  'git+https://github.com/leynos/df12-python-lints.git@$(DF12_PYTHON_LINTS_REF)' \
  -- df12-duplication

duplication: ## Run the blocking code-duplication gate
	$(DUPLICATION) install --repository .
	$(DUPLICATION) check --repository .

duplication-allow: ## Record one reasoned exception
	$(DUPLICATION) allow --repository . $(foreach m,$(MEMBERS),--member '$(m)') \
	  --reason '$(REASON)'
```

CI calls the same `make duplication` target, and caches `.tools/nose` keyed on
`[tool.nose].version`. A pinned Git source needs a full commit SHA until a
release exists.

## Deletion checklist

Delete only after `make duplication` passes through the installed command:

- [ ] `scripts/duplication_gate.py`, `scripts/nose_detector.py`,
  `scripts/nose_schema.py` and `scripts/duplication_allowlist.py`.
- [ ] The copied suites under `scripts/tests/` (`test_duplication_gate*.py`,
  `test_nose_detector.py`, `test_make_install_nose.py`) and their snapshots.
- [ ] The PEP 723 metadata block and the `cyclopts` and `tomlkit` pins that
  only the vendored gate used.
- [ ] The cargo-binstall install target and its CI step, replaced by
  `df12-duplication install`.
- [ ] Any duplicated copy of the nose version pin: `[tool.nose].version` is the
  only authority.

Keep these:

- [ ] `scripts/atomic_write.py` and other helpers that still have unrelated
  callers.
- [ ] The local `[tool.nose]` table, every allow entry and its reason.
- [ ] A small contract showing that the Makefile target calls the installed
  command and that a failing gate fails the make target and CI.

## Pilot parity evidence

For the pilot, run the vendored gate and the installed command on the same
commit with the same detector binary, and compare: the normalized families, the
blocking, allowed and unmatched partitions, and the exit status. Agreement of
two zero exits alone is not evidence. Explain every intentional difference, for
example the changed unmatched-entry wording, and do not allow new findings to
make the migration pass.
