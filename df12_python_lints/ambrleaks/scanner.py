"""Scanner core for syrupy ``.ambr`` snapshot files.

The Amber format is line-oriented: control lines start at column zero
with ``#`` (a serializer-version header, ``# name: <test-id>`` block
openers, and ``# ---`` terminators) while snapshot bodies are indented.
The scanner attributes every finding to the enclosing test block.

The module separates a pure core from its filesystem boundary:
:func:`scan_text` performs all block attribution and rule matching over
an in-memory string, while :func:`scan_file` is a thin boundary that
reads a file and delegates to it. Both require an explicit *base_dir* so
reported paths never depend on the process working directory.

Examples
--------
Scan one snapshot file with the default rules::

    findings = scan_file(path, DEFAULT_RULES, base_dir=repo_root)
"""

from __future__ import annotations

import collections
import hashlib
import math
import typing as typ

from .rules import DEFAULT_RULES, Rule

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

__all__ = [
    "DEFAULT_RULES",
    "Finding",
    "Rule",
    "scan_file",
    "scan_text",
    "shannon_entropy",
]


class Finding(typ.NamedTuple):
    """A single unredacted value detected in a snapshot file.

    Examples
    --------
    ``Finding("tests/__snapshots__/t.ambr", 4, "test_user",
    "snapshot-email", "alice@realcorp.io")``
    """

    path: str
    line: int
    test_name: str
    rule_id: str
    value: str

    def fingerprint(self) -> str:
        """Return a stable identifier for baseline bookkeeping.

        The line number is deliberately excluded so a baseline survives
        blocks moving around when snapshots are regenerated.

        Examples
        --------
        Two findings for the same value in the same test share a
        fingerprint even if the value moves to a different line.
        """
        payload = "|".join((self.path, self.test_name, self.rule_id, self.value))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def shannon_entropy(text: str) -> float:
    """Return the Shannon entropy of *text* in bits per character.

    Examples
    --------
    ``shannon_entropy("aaaa")`` is ``0.0``; random 32-character hex
    strings score close to ``4.0``.
    """
    if not text:
        return 0.0
    counts = collections.Counter(text)
    total = len(text)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _canonical_path(path: pathlib.Path, base_dir: pathlib.Path) -> str:
    """Render *path* relative to *base_dir* when it lies within.

    A relative *path* is anchored to *base_dir* rather than the process
    working directory, so the canonical form is fully determined by the
    two arguments and never shifts when the caller's ``cwd`` changes.
    """
    base = base_dir.resolve()
    anchored = path if path.is_absolute() else base / path
    resolved = anchored.resolve()
    if resolved.is_relative_to(base):
        return resolved.relative_to(base).as_posix()
    return resolved.as_posix()


def _line_findings(line: str, rule: Rule) -> cabc.Iterator[str]:
    """Yield the values in *line* that violate *rule*."""
    for match in rule.pattern.finditer(line):
        value = match.group()
        if any(allowed.search(value) for allowed in rule.allow):
            continue
        if shannon_entropy(value) < rule.min_entropy:
            continue
        yield value


def scan_text(
    text: str,
    path: pathlib.Path,
    rules: cabc.Sequence[Rule],
    *,
    base_dir: pathlib.Path,
) -> list[Finding]:
    r"""Scan snapshot *text* attributed to *path* with *rules*.

    This is the pure scanning core: it performs Amber block attribution
    and rule matching over an in-memory string and never touches the
    filesystem for *text*. Control lines (column-zero ``#`` lines) carry
    block structure and are never scanned; body lines are attributed to
    the most recent ``# name:`` block. Findings report *path*
    canonicalised against *base_dir* (see :func:`_canonical_path`), so
    the output is fully determined by the arguments and independent of
    the process working directory.

    Examples
    --------
    ``scan_text("# name: t\\n  alice@realcorp.io\\n",
    pathlib.Path("t.ambr"), DEFAULT_RULES, base_dir=repo_root)`` returns
    the email finding attributed to test ``t``.
    """
    findings: list[Finding] = []
    test_name = "<module>"
    canonical = _canonical_path(path, base_dir)
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("#"):
            if line.startswith("# name:"):
                test_name = line.removeprefix("# name:").strip()
            continue
        findings.extend(
            Finding(canonical, line_number, test_name, rule.rule_id, value)
            for rule in rules
            for value in _line_findings(line, rule)
        )
    return findings


def scan_file(
    path: pathlib.Path,
    rules: cabc.Sequence[Rule],
    *,
    base_dir: pathlib.Path,
) -> list[Finding]:
    """Read the ``.ambr`` file at *path* and scan it with *rules*.

    Thin filesystem boundary over :func:`scan_text`: it reads *path* as
    UTF-8 and delegates all parsing and matching. *base_dir* is required
    and injected explicitly so reported paths never depend on the
    process working directory. Read failures (``OSError``,
    ``UnicodeDecodeError``) propagate to the caller; the CLI reports them
    at its boundary.

    Examples
    --------
    ``scan_file(pathlib.Path("__snapshots__/t.ambr"), DEFAULT_RULES,
    base_dir=repo_root)`` returns a list of findings in file order.
    """
    text = path.read_text(encoding="utf-8")
    return scan_text(text, path, rules, base_dir=base_dir)
