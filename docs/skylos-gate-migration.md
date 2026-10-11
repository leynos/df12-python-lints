# Migrating to df12-skylos

This guide moves a repository that carries its own Skylos Makefile plumbing and
copied contract suites onto the installed `df12-skylos` command. The
project-specific policy stays local: `[tool.skylos]`, its documented exceptions
and runtime entry points, and the reason for each. The invocation, the
configuration validation, the exception editor and the generic boundary tests
move into this package.

## Command changes

| Makefile construct                                                                     | Installed command                                               |
| -------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `SKYLOS_CLI = uv tool run --python 3.14 --from 'skylos==...' skylos`                   | the `skylos` extra, provisioned in an isolated tool environment |
| `$(SKYLOS) $(SKYLOS_PRODUCTION_TARGETS) --exclude ... --category dead_code --gate ...` | `df12-skylos check --repository .`                              |
| `SKYLOS_PRODUCTION_TARGETS ?= pkg`                                                     | `[tool.df12_skylos] roots = ["pkg"]`                            |
| `SKYLOS_EXCLUDE_FOLDERS ?= tests`                                                      | native `[tool.skylos] exclude = ["tests"]`                      |
| `skylos-allow` with `SYMBOL=` and `REASON=`                                            | `df12-skylos allow --symbol NAME --reason TEXT`                 |
| `flock .skylos-whitelist.lock ...`                                                     | the shared per-manifest lock inside the command                 |

Add `python = "<minimum>"` to `[tool.df12_skylos]` from the interpreter the
Makefile pins today (3.14 for most consumers; Lading follows its project
baseline). Move any exclusion list from a Make variable into the native
`exclude` setting, and confirm on the same commit that the findings are
unchanged.

## Behaviour corrections

- The gate fails closed on a root with no Python files, which Skylos reports
  only as a warning on a zero exit.
- A non-strict gate, a blank reason and an entry-point rule that selects nothing
  are now rejected with the offending key, where Skylos silently accepts them.
- `allow` writes through a comment-preserving editor under a lock; native
  `skylos whitelist` substitutes text without quoting.
- A wildcard or dotted symbol is refused rather than becoming a silent pattern.

## Makefile and CI shape

```make
SKYLOS = $(UV_GATE) tool --python 3.14 \
  --from 'git+https://github.com/leynos/df12-python-lints.git@$(DF12_PYTHON_LINTS_REF)' \
  --with 'skylos==$(SKYLOS_VERSION)' -- df12-skylos

skylos: ## Detect dead production code
	$(SKYLOS) check --repository .

skylos-allow: ## Record one documented exception (SYMBOL=name REASON=text)
	$(SKYLOS) allow --repository . --symbol '$(SYMBOL)' --reason '$(REASON)'
```

`SKYLOS_VERSION` must equal the package's pin; `df12-skylos check` fails with
the two versions named if it does not. Until the vendored `uv_gate` accepts
`'df12-python-lints[skylos] @ git+...@<sha>'`, the `--with` spelling above is
the pinned form it accepts; once it does, drop `--with` and the Make copy of
the version entirely. CI calls the same `make skylos` target.

## Deletion checklist

Delete only after `make skylos` passes through the installed command:

- [ ] The `SKYLOS_CLI`, `SKYLOS`, `SKYLOS_VERSION`, `SKYLOS_PRODUCTION_TARGETS`,
  `SKYLOS_EXCLUDE_FOLDERS` and `SKYLOS_WHITELIST_LOCK` variables and the old
  `skylos-allow` recipe.
- [ ] Copied implementation and boundary suites: the whitelist-boundary and
  allow-contract tests, and any generic Make or workflow parsing helper that
  only they used (`make_contract`, Makeutil provisioning, PyYAML parsing). Keep
  Makeutil and PyYAML where other callers remain.
- [ ] Literal Makefile assertions (variable spellings, recipe token mirrors).
- [ ] Any hard-coded copy of the whitelist or entry-point inventory.

Keep these:

- [ ] `[tool.skylos]` and `[tool.df12_skylos]`, with every exception and its
  reason.
- [ ] The tests that show why a framework callback needs its exception and that
  an unrelated unused neighbour still fails.
- [ ] A small contract that the lint target calls the installed command and that
  a failing gate fails the make target and CI.
- [ ] Application ADRs.

An exact inventory test (a set of expected exception names) is sometimes a
deliberate second review boundary. Name that purpose before removing it; the
shared command checks reasons and shapes, not which symbols a project has
chosen to except.

## Pilot parity evidence

Run the old and the new gate on the same commit with the same pinned Skylos,
and compare the normalized findings, the exit status, the selected roots and
the before and after configuration. Two zero exits are not evidence. Explain
intentional corrections separately and do not except findings to complete a
migration.
