"""Command-line interface for the ambrleaks snapshot scanner.

Suppression never touches the ``.ambr`` files themselves — syrupy
rewrites them wholesale on ``--snapshot-update``, so inline markers
would be destroyed. Instead:

- an ``ambrleaks.toml`` configuration enables or disables rules and
  allowlists values, test names, and paths; and
- a baseline file records the fingerprints of accepted findings so
  existing snapshots can be grandfathered while new findings still fail.

Examples
--------
Scan the current tree, then baseline the existing findings::

    ambrleaks
    ambrleaks --write-baseline .ambrleaks-baseline.json
    ambrleaks --baseline .ambrleaks-baseline.json
"""

from __future__ import annotations

import argparse
import collections
import fnmatch
import json
import pathlib
import re
import sys
import tomllib
import typing as typ

from .rules import DEFAULT_RULES, Rule
from .scanner import Finding, scan_file

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_CONFIG_NAMES: typ.Final = ("ambrleaks.toml", ".ambrleaks.toml")


class ConfigError(ValueError):
    """Raised when a configuration file is structurally invalid."""


class Config(typ.NamedTuple):
    """Loaded configuration for a scan run.

    Examples
    --------
    ``default_config()`` gives the defaults: shipped rule states and
    empty allowlists.
    """

    rule_states: tuple[tuple[str, bool], ...]
    allow_values: tuple[str, ...]
    allow_tests: tuple[str, ...]
    allow_paths: tuple[str, ...]


def default_config() -> Config:
    """Return the configuration used when no file is present.

    Examples
    --------
    ``default_config().allow_values`` is empty.
    """
    return Config(rule_states=(), allow_values=(), allow_tests=(), allow_paths=())


def _validate_rules(rules: object) -> None:
    """Ensure ``[rules]`` is a table of tables with boolean ``enabled``."""
    if not isinstance(rules, dict):
        message = "[rules] must be a table"
        raise ConfigError(message)
    for rule_id, entry in rules.items():
        if not isinstance(entry, dict):
            message = f"[rules.{rule_id}] must be a table"
            raise ConfigError(message)
        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            message = f"[rules.{rule_id}] enabled must be a boolean"
            raise ConfigError(message)


def _validate_allowlist(allowlist: object) -> None:
    """Ensure ``[allowlist]`` is a table of string lists."""
    if not isinstance(allowlist, dict):
        message = "[allowlist] must be a table"
        raise ConfigError(message)
    for key, value in allowlist.items():
        if key not in {"values", "tests", "paths"}:
            continue
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            message = f"[allowlist] {key} must be a list of strings"
            raise ConfigError(message)


def parse_config(text: str) -> Config:
    r"""Parse *text* as an ``ambrleaks`` TOML configuration.

    This is the pure configuration core: it decodes and structurally
    validates *text* without any filesystem access, so callers can test
    it against literal TOML. :func:`read_config` is the filesystem
    boundary that supplies *text* from a file.

    Raises
    ------
    ConfigError
        If the configuration is structurally invalid.
    tomllib.TOMLDecodeError
        If *text* is not valid TOML.

    Examples
    --------
    ``parse_config("[rules.snapshot-phone]\\nenabled = true\\n")``
    switches the phone rule on.
    """
    data = tomllib.loads(text)
    rules = data.get("rules", {})
    allowlist = data.get("allowlist", {})
    _validate_rules(rules)
    _validate_allowlist(allowlist)
    return Config(
        rule_states=tuple(
            (rule_id, bool(entry.get("enabled", True)))
            for rule_id, entry in rules.items()
        ),
        allow_values=tuple(allowlist.get("values", ())),
        allow_tests=tuple(allowlist.get("tests", ())),
        allow_paths=tuple(allowlist.get("paths", ())),
    )


def read_config(path: pathlib.Path | None) -> Config:
    """Read *path* as TOML configuration, or defaults when ``None``.

    Thin filesystem boundary over :func:`parse_config`: it reads *path*
    as UTF-8 and delegates decoding and validation. Read and decode
    failures propagate to the caller; the CLI reports them at its
    boundary.

    Raises
    ------
    ConfigError
        If the configuration is structurally invalid.
    OSError
        If the file cannot be read.
    UnicodeDecodeError
        If the file is not valid UTF-8.
    tomllib.TOMLDecodeError
        If the file is not valid TOML.

    Examples
    --------
    Given an ``ambrleaks.toml`` containing ``[rules.snapshot-phone]``
    with ``enabled = true``, ``read_config(path)`` switches the phone
    rule on.
    """
    if path is None:
        return default_config()
    return parse_config(path.read_text(encoding="utf-8"))


def select_rules(config: Config) -> tuple[Rule, ...]:
    """Return the shipped rules filtered by *config* overrides.

    Examples
    --------
    With no overrides, every rule enabled by default is returned and
    the opt-in phone rule is not.
    """
    states = dict(config.rule_states)
    return tuple(
        rule
        for rule in DEFAULT_RULES
        if states.get(rule.rule_id, rule.enabled_by_default)
    )


def _is_allowed(finding: Finding, config: Config) -> bool:
    """Return whether *finding* matches a configuration allowlist entry."""
    posix_path = pathlib.PurePath(finding.path).as_posix()
    return (
        any(re.search(pattern, finding.value) for pattern in config.allow_values)
        or any(fnmatch.fnmatch(finding.test_name, glob) for glob in config.allow_tests)
        or any(fnmatch.fnmatch(posix_path, glob) for glob in config.allow_paths)
    )


def discover(paths: cabc.Iterable[pathlib.Path]) -> list[pathlib.Path]:
    """Collect ``.ambr`` files under each of *paths*.

    Examples
    --------
    A directory argument yields every ``.ambr`` file beneath it; a file
    argument yields itself.
    """
    collected: list[pathlib.Path] = []
    for path in paths:
        if path.is_dir():
            collected.extend(sorted(path.rglob("*.ambr")))
        else:
            collected.append(path)
    return collected


def _default_config_path() -> pathlib.Path | None:
    """Return the first conventional configuration file that exists."""
    for name in _CONFIG_NAMES:
        candidate = pathlib.Path(name)
        if candidate.is_file():
            return candidate
    return None


def _parse_arguments(argv: cabc.Sequence[str] | None) -> argparse.Namespace:
    """Parse command-line *argv* into a namespace."""
    parser = argparse.ArgumentParser(
        prog="ambrleaks",
        description=(
            "Scan syrupy .ambr snapshots for unredacted hex strings, "
            "UUIDs, emails, phone numbers, URLs, and absolute paths."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=pathlib.Path,
        default=[pathlib.Path()],
        help="files or directories to scan (default: current directory)",
    )
    parser.add_argument(
        "--config",
        type=pathlib.Path,
        default=None,
        help="TOML configuration (default: ./ambrleaks.toml if present)",
    )
    parser.add_argument(
        "--baseline",
        type=pathlib.Path,
        default=None,
        help="JSON baseline of accepted finding fingerprints to skip",
    )
    parser.add_argument(
        "--write-baseline",
        type=pathlib.Path,
        default=None,
        help="write the current findings as a baseline and exit",
    )
    return parser.parse_args(argv)


def _collect_findings(
    arguments: argparse.Namespace, config: Config, base_dir: pathlib.Path
) -> list[Finding]:
    """Scan the requested paths and apply configuration allowlists.

    *base_dir* is the CLI's resolved base directory; it is injected into
    every :func:`scan_file` call so scanning never derives paths from the
    ambient working directory.
    """
    rules = select_rules(config)
    findings = [
        finding
        for path in discover(arguments.paths)
        for finding in scan_file(path, rules, base_dir=base_dir)
    ]
    return [f for f in findings if not _is_allowed(f, config)]


def apply_baseline(
    findings: list[Finding], accepted: cabc.Mapping[str, int]
) -> list[Finding]:
    """Drop findings the baseline accepts, one per recorded occurrence.

    Pure counterpart to :func:`read_baseline`: *accepted* maps a
    finding fingerprint to the number of occurrences the baseline
    grandfathers. Each matching finding consumes one occurrence, so a
    fingerprint recorded *n* times suppresses only the first *n*
    findings and any beyond that still surface.

    Examples
    --------
    With ``accepted`` counting a fingerprint once, the first finding
    sharing it is dropped and a second identical finding is kept.
    """
    remaining_quota = collections.Counter(accepted)
    remaining: list[Finding] = []
    for finding in findings:
        fingerprint = finding.fingerprint()
        if remaining_quota[fingerprint] > 0:
            remaining_quota[fingerprint] -= 1
        else:
            remaining.append(finding)
    return remaining


def read_baseline(path: pathlib.Path) -> collections.Counter[str]:
    """Read *path* as a JSON list of accepted finding fingerprints.

    Thin filesystem boundary over :func:`apply_baseline`: it reads and
    decodes the baseline, counting repeated fingerprints as repeated
    occurrences. Read and decode failures propagate to the caller; the
    CLI reports them at its boundary.
    """
    return collections.Counter(json.loads(path.read_text(encoding="utf-8")))


def _run(arguments: argparse.Namespace) -> int:
    """Execute the scan described by *arguments* and return an exit code.

    The CLI resolves its base directory once here (the working directory
    at invocation) and injects it into scanning, so the scanner core
    never reads the ambient ``cwd`` itself.
    """
    config = read_config(arguments.config or _default_config_path())
    base_dir = pathlib.Path.cwd()
    findings = _collect_findings(arguments, config, base_dir)
    if arguments.write_baseline is not None:
        fingerprints = sorted(f.fingerprint() for f in findings)
        arguments.write_baseline.write_text(
            json.dumps(fingerprints, indent=2) + "\n", encoding="utf-8"
        )
        print(f"ambrleaks: baselined {len(fingerprints)} finding(s)")
        return 0
    if arguments.baseline is not None:
        findings = apply_baseline(findings, read_baseline(arguments.baseline))
    for finding in findings:
        print(
            f"{finding.path}:{finding.line}: [{finding.rule_id}] "
            f"{finding.test_name}: {finding.value}"
        )
    if findings:
        print(f"ambrleaks: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    return 0


def main(argv: cabc.Sequence[str] | None = None) -> int:
    """Run the scanner; return a process exit code.

    Examples
    --------
    ``main(["tests"])`` returns ``0`` for a clean tree and ``1`` when
    findings remain after allowlists and the baseline.
    """
    arguments = _parse_arguments(argv)
    try:
        return _run(arguments)
    except (
        ConfigError,
        OSError,
        UnicodeDecodeError,
        tomllib.TOMLDecodeError,
        json.JSONDecodeError,
    ) as err:
        print(f"ambrleaks: error: {err}", file=sys.stderr)
        return 2
