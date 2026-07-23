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


def load_config(path: pathlib.Path | None) -> Config:
    """Load *path* as TOML configuration, or defaults when ``None``.

    Examples
    --------
    A file containing ``[rules.snapshot-phone]`` with ``enabled = true``
    switches the phone rule on.
    """
    if path is None:
        return default_config()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    rules = data.get("rules", {})
    allowlist = data.get("allowlist", {})
    return Config(
        rule_states=tuple(
            (rule_id, bool(entry.get("enabled", True)))
            for rule_id, entry in rules.items()
        ),
        allow_values=tuple(allowlist.get("values", ())),
        allow_tests=tuple(allowlist.get("tests", ())),
        allow_paths=tuple(allowlist.get("paths", ())),
    )


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
    """Return whether *finding* matches a configuration allowlist entry.

    Examples
    --------
    A finding in ``test_legacy_export`` is allowed when the
    configuration lists the test glob ``test_legacy_*``.
    """
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
    """Return the first conventional configuration file that exists.

    Examples
    --------
    Returns ``ambrleaks.toml`` from the working directory when present.
    """
    for name in _CONFIG_NAMES:
        candidate = pathlib.Path(name)
        if candidate.is_file():
            return candidate
    return None


def _parse_arguments(argv: cabc.Sequence[str] | None) -> argparse.Namespace:
    """Parse command-line *argv* into a namespace.

    Examples
    --------
    ``_parse_arguments(["tests"])`` scans the ``tests`` tree.
    """
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


def _collect_findings(arguments: argparse.Namespace, config: Config) -> list[Finding]:
    """Scan the requested paths and apply configuration allowlists.

    Examples
    --------
    Returns an empty list for a tree with no ``.ambr`` files.
    """
    rules = select_rules(config)
    findings = [
        finding
        for path in discover(arguments.paths)
        for finding in scan_file(path, rules)
    ]
    return [f for f in findings if not _is_allowed(f, config)]


def _apply_baseline(
    findings: list[Finding], baseline_path: pathlib.Path
) -> list[Finding]:
    """Drop findings the baseline accepts, respecting multiplicity.

    Fingerprints exclude line numbers, so repeated values in one block
    share a fingerprint. The baseline is therefore treated as occurrence
    counts: each recorded fingerprint suppresses one occurrence, and any
    occurrence beyond the recorded count is retained so a newly
    introduced duplicate still fails the scan.

    Examples
    --------
    A finding recorded twice by ``--write-baseline`` suppresses two
    occurrences; a third occurrence of the same value is reported.
    """
    accepted = collections.Counter(
        json.loads(baseline_path.read_text(encoding="utf-8"))
    )
    remaining: list[Finding] = []
    for finding in findings:
        fingerprint = finding.fingerprint()
        if accepted[fingerprint] > 0:
            accepted[fingerprint] -= 1
        else:
            remaining.append(finding)
    return remaining


def main(argv: cabc.Sequence[str] | None = None) -> int:
    """Run the scanner; return a process exit code.

    Examples
    --------
    ``main(["tests"])`` returns ``0`` for a clean tree and ``1`` when
    findings remain after allowlists and the baseline.
    """
    arguments = _parse_arguments(argv)
    config = load_config(arguments.config or _default_config_path())
    findings = _collect_findings(arguments, config)
    if arguments.write_baseline is not None:
        fingerprints = sorted(f.fingerprint() for f in findings)
        arguments.write_baseline.write_text(
            json.dumps(fingerprints, indent=2) + "\n", encoding="utf-8"
        )
        print(f"ambrleaks: baselined {len(fingerprints)} finding(s)")
        return 0
    if arguments.baseline is not None:
        findings = _apply_baseline(findings, arguments.baseline)
    for finding in findings:
        print(
            f"{finding.path}:{finding.line}: [{finding.rule_id}] "
            f"{finding.test_name}: {finding.value}"
        )
    if findings:
        print(f"ambrleaks: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    return 0
