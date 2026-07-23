"""Scanner core for syrupy ``.ambr`` snapshot files.

The Amber format is line-oriented: control lines start at column zero
with ``#`` (a serializer-version header, ``# name: <test-id>`` block
openers, and ``# ---`` terminators) while snapshot bodies are indented.
The scanner attributes every finding to the enclosing test block.

Examples
--------
Scan one snapshot file with the default rules::

    findings = scan_file(path, DEFAULT_RULES)
"""

from __future__ import annotations

import collections
import hashlib
import math
import pathlib
import typing as typ

from .rules import DEFAULT_RULES, Rule

if typ.TYPE_CHECKING:
    import collections.abc as cabc

__all__ = ["DEFAULT_RULES", "Finding", "Rule", "scan_file", "shannon_entropy"]


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


def _canonical_path(path: pathlib.Path) -> str:
    """Render *path* relative to the working directory when it lies within."""
    resolved = path.resolve()
    cwd = pathlib.Path.cwd().resolve()
    if resolved.is_relative_to(cwd):
        return resolved.relative_to(cwd).as_posix()
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


def scan_file(path: pathlib.Path, rules: cabc.Sequence[Rule]) -> list[Finding]:
    """Scan the ``.ambr`` file at *path* with *rules*.

    Control lines (column-zero ``#`` lines) carry block structure and
    are never scanned; body lines are attributed to the most recent
    ``# name:`` block. Reported paths are canonicalised so fingerprints
    do not depend on the working directory from which the scan is run.

    Examples
    --------
    ``scan_file(pathlib.Path("__snapshots__/t.ambr"), DEFAULT_RULES)``
    returns a list of findings in file order.
    """
    findings: list[Finding] = []
    test_name = "<module>"
    canonical = _canonical_path(path)
    text = path.read_text(encoding="utf-8")
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
