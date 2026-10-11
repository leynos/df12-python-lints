# Migrating to version 0.4.0

Version 0.4.0 adds two console commands and leaves the Pylint plugin and
`ambrleaks` unchanged. Nothing in 0.3.0 needs migrating unless a repository
adopts the new commands.

## New commands

- `df12-duplication` runs the blocking nose code-duplication gate. See the
  [duplication gate migration guide](duplication-gate-migration.md) for moving
  a vendored copy onto it.
- `df12-skylos` runs the Skylos dead-code gate. See the
  [Skylos gate migration guide](skylos-gate-migration.md) for moving Makefile
  plumbing and copied contract suites onto it.

## Optional extras

| Extra         | Installs                       | Needed by                                                            |
| ------------- | ------------------------------ | -------------------------------------------------------------------- |
| `duplication` | `tomlkit`                      | `df12-duplication allow`, which Pylint already provides transitively |
| `skylos`      | `tomlkit` and `skylos==4.33.2` | `df12-skylos`                                                        |

The `skylos` extra is the one authoritative Skylos pin; `check` fails if the
installed Skylos differs. Install nothing extra to keep using only the plugin
and `ambrleaks`.

## Configuration additions

- `df12-duplication` reads `[tool.nose]` and `[[tool.duplication_gate.allow]]`.
- `df12-skylos` reads the native `[tool.skylos]` tables plus
  `[tool.df12_skylos]` (`roots`, `python`).

## Behaviour to know about

- Both commands exit `0` (clean), `1` (blocking findings) or `2` (invalid
  invocation or configuration, or a failed analysis).
- `df12-duplication check` fails closed (status `2`) when the detector's report
  budget hides families and nothing blocks. Repositories with a saturated
  report set `tool.nose.top = 0` and adjudicate the newly visible families.
- `allow` rejects control characters in a reason, other than newline and tab.
- The Skylos scan runs in an isolated child interpreter.
- Authoring needs POSIX file locks (Linux and macOS); native Windows is not
  supported for `allow`.
