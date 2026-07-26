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
import logging
import pathlib
import re
import sys
import tomllib
import typing as typ

from .config import Config, ConfigError, read_config, select_rules
from .scanner import Finding, scan_file

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_CONFIG_NAMES: typ.Final = ("ambrleaks.toml", ".ambrleaks.toml")

# Library-style logging: quiet unless the caller (or --verbose) attaches a
# handler, so default CLI output stays limited to findings and errors.
logger = logging.getLogger("ambrleaks")
logger.addHandler(logging.NullHandler())


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
    parser.add_argument(
        "--show-values",
        action="store_true",
        help=(
            "print each finding's full value; by default the value is "
            "masked so a scan report does not reproduce the secret"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log scan, configuration, and baseline boundary details to stderr",
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


_MIN_MASK_PREVIEW_LENGTH: typ.Final = 4


def _masked_value(value: str) -> str:
    """Return a masked preview of *value* for default output.

    Reveals only the first and last character of a value and masks the
    interior, so a scan report does not reproduce an unredacted secret
    verbatim (for example in shared CI logs). Values shorter than
    :data:`_MIN_MASK_PREVIEW_LENGTH` (four) characters are masked
    entirely. The full value is printed only under ``--show-values``.

    Examples
    --------
    ``"alice@realcorp.io"`` renders as ``"a***************o"``; ``"ab"``
    renders as ``"**"``.
    """
    if len(value) < _MIN_MASK_PREVIEW_LENGTH:
        return "*" * len(value)
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"


def _enable_verbose_logging() -> None:
    """Attach a stderr handler so boundary logs surface under ``--verbose``."""
    if any(not isinstance(h, logging.NullHandler) for h in logger.handlers):
        logger.setLevel(logging.INFO)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("ambrleaks: %(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _run(arguments: argparse.Namespace) -> int:
    """Execute the scan described by *arguments* and return an exit code.

    The CLI resolves its base directory once here (the working directory
    at invocation) and injects it into scanning, so the scanner core
    never reads the ambient ``cwd`` itself. Structured logs mark the
    configuration, scan, and baseline boundaries; they are silent unless
    ``--verbose`` (or a caller-attached handler) surfaces them.
    """
    config_path = arguments.config or _default_config_path()
    config = read_config(config_path)
    logger.info("loaded configuration from %s", config_path or "defaults")
    base_dir = pathlib.Path.cwd()
    findings = _collect_findings(arguments, config, base_dir)
    logger.info("scan produced %d finding(s) under %s", len(findings), base_dir)
    if arguments.write_baseline is not None:
        fingerprints = sorted(f.fingerprint() for f in findings)
        arguments.write_baseline.write_text(
            json.dumps(fingerprints, indent=2) + "\n", encoding="utf-8"
        )
        logger.info("wrote baseline of %d fingerprint(s)", len(fingerprints))
        print(f"ambrleaks: baselined {len(fingerprints)} finding(s)")
        return 0
    if arguments.baseline is not None:
        before = len(findings)
        findings = apply_baseline(findings, read_baseline(arguments.baseline))
        logger.info("baseline suppressed %d finding(s)", before - len(findings))
    for finding in findings:
        value = finding.value if arguments.show_values else _masked_value(finding.value)
        print(
            f"{finding.path}:{finding.line}: [{finding.rule_id}] "
            f"{finding.test_name}: {value}"
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
    if arguments.verbose:
        _enable_verbose_logging()
    try:
        return _run(arguments)
    except (
        ConfigError,
        OSError,
        UnicodeDecodeError,
        tomllib.TOMLDecodeError,
        json.JSONDecodeError,
    ) as err:
        logger.exception("scan failed")
        print(f"ambrleaks: error: {err}", file=sys.stderr)
        return 2
