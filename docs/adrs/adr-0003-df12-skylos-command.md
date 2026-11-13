# Architectural decision record (ADR) 003: The df12-skylos command

## Status

Accepted. Native Skylos stays the analysis and gating authority; the package
validates, invokes and adapts.

## Date

2026-10-11.

## Context and problem statement

Consumers carried Makefile plumbing, a lock that did not coordinate with the
duplication editor, and copied contract suites for Skylos. Probing the pinned
release (4.33.2) showed silent failures: a gate without `strict = true` exits
`0` with findings, a root with no Python files only logs a warning on a zero
exit, entry-point rules without a selector or reason are dropped, and
`skylos whitelist` edits the manifest with unquoted text substitution.

## Decision drivers

- Never reimplement Skylos's analysis or thresholds.
- A failed analysis must never read as clean.
- A source tree must not be able to influence the scanner that judges it.
- One authoritative backend pin, one authoring lock.

## Decision outcome

### Adapter

`backend.py` builds one argument vector, runs it through the shared subprocess
boundary and maps the native status: `0` clean, `1` blocking, `2` failed
analysis (invalid configuration or `SKY-ANALYSIS-INCOMPLETE`), anything else an
error. A zero exit that logged an empty root is refused.

### Isolation

The scan runs `skylos.cli:main` in a child of `sys.executable` with `-I`, so
neither the current directory nor `PYTHON*` variables reach `sys.path`. A
`skylos` package committed in the scanned checkout cannot shadow the pinned
installation (tested with a decoy on disk and on `PYTHONPATH`).

### Configuration

Native settings, reasons and exceptions stay in `[tool.skylos]`, validated
fail-closed by `config.py`. A single wrapper table, `[tool.df12_skylos]`, holds
the production roots and the minimum interpreter, because the native schema
cannot. Roots are scanned in one invocation so cross-root references count.
Exclusions use the native `exclude`.

### Pin and interpreter

The `skylos` extra is the one authoritative pin; `check` requires the installed
backend to equal it and the interpreter to meet `tool.df12_skylos.python`. The
dev group repeats the pin for the coverage lane, and a test asserts the two
agree.

### Authoring

`allow` writes `[tool.skylos.whitelist.documented]` through the shared manifest
transaction (ADR 002). Only a plain identifier is accepted: the native match is
`fnmatch` on the simple name, so a wildcard would silently excuse many names.
It never creates a runtime entry-point exemption, and an existing value that is
not a string is refused rather than treated as unchanged.

## Consequences

- Consumer migration is a deletion checklist; the tests that show why a
  framework hook needs its exception stay local.
- A new Skylos release needs a re-probe of the facts above and a pin change in
  two places guarded by a test.
- Native Windows is not supported for authoring.
