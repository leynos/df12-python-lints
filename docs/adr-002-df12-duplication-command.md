# Architectural decision record (ADR) 002: The df12-duplication command

## Status

Accepted. The nose duplication gate ships as the `df12-duplication` console
command with a pure policy core, an explicit run context, one shared manifest
transaction and a digest-verified, binary-only installer.

## Date

2026-10-11.

## Context and problem statement

Several repositories vendored a copy of the Episodic duplication gate: a
detector adapter, an exception editor, an installer and a test suite. Each copy
required Python 3.14 and repeated the same defects: an empty effective scan
could pass, ambient native nose configuration could suppress findings silently,
the unmatched-entry message claimed the duplication was gone, and the editor
took a lock that no other tool shared. The package must offer one maintained
implementation without raising its Python 3.12 floor or burdening users of the
Pylint plugin.

## Decision drivers

- A gate must fail closed: no failure may read as a clean scan.
- Consumers keep policy (`[tool.nose]`, exceptions, reasons); the package keeps
  mechanism.
- The Pylint plugin and `ambrleaks` stay light and platform-neutral.
- Authoring must be safe under concurrent use, including by the Skylos command.
- Provisioning must be explicit, pinned and verifiable.

## Options considered

- Keep vendoring and fix defects in each consumer.
- Extract a sibling distribution with a 3.14 floor.
- Import into this distribution behind an optional extra, supporting 3.12.

## Decision outcome

Import into this distribution (`df12_python_lints/duplication/`), supporting
Python 3.12, with these decisions.

### Subsystem boundaries

- `policy.py` is the pure domain: allow keys, whole-family matching and the
  partition of findings. It reads no files and runs no processes.
- `allowlist.py` and `settings.py` read and validate the manifest tables;
  `allowlist.py` also records entries through the shared transaction.
- `detector.py` adapts the nose process: it builds one argument vector, runs it
  through an injected boundary and normalizes the report. It writes nothing;
  the command boundary (`commands.py`) owns the lifecycle of the empty native
  configuration files that neutralize ambient nose configuration.
- `release.py` and `install.py` provision the binary; `check` never calls them.
- `cli.py` builds the explicit run context once and dispatches.

### Shared abstractions

The manifest transaction, atomic replacement, validators, error vocabulary and
the `full_match` port live at the package root so `df12-skylos` reuses them
rather than copying them. A helper moves to the root only when a second command
needs it.

### Manifest locking and atomic writes

One advisory `flock` on a stable `.<name>.df12.lock` sidecar of the resolved
manifest is held across read, validation, edit and replacement, so every
spelling of one file (including symlinks) takes the same lock, and the lock
inode never changes while the manifest is replaced. Replacement writes a synced
temporary sibling, preserves the mode and renames it, removing the temporary on
every failure. The lock coordinates participating commands only. Platforms
without `fcntl` fail closed.

### Installer verification

Only archives whose SHA-256 appears in the bundled `releases.json` are
accepted; the URL must be the official GitHub release path; the archive is read
in memory and must hold exactly one regular, path-safe executable; and the
executable must report the pinned version from a scratch location before it
replaces anything. There is no compilation, no installer script and no "latest".

### Python 3.12 and `full_match`

`PurePosixPath.full_match` exists from Python 3.13. On 3.13 and later the
command delegates to it. On 3.12 a port of CPython's `glob.translate` and
`fnmatch` translation provides the same semantics, so exception scope does not
change; a pinned corpus of 4000 answers recorded on CPython 3.14 checks it on
every interpreter, and a differential test compares it with the native method.
`typing.TypeIs` appears only in annotations behind `TYPE_CHECKING`.

### Observability

The commands are short-lived tools. They log one structured record per
operation (operation, repository, outcome, exit status, elapsed time) and debug
records for each subprocess and download through the standard `logging` module,
silent by default and enabled by `--verbose`.

## Consequences

- One implementation, one test suite and one provisioning path replace several
  vendored copies; consumer migration is a deletion checklist.
- The report budget is reported, not changed: enforcement stays bounded until a
  repository chooses `top = 0` as a reviewed policy change.
- Native Windows is not supported for authoring.
- A new nose release needs a reviewed digest entry and a test run against the
  real binary.
