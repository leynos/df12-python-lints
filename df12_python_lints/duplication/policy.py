"""The duplication exception policy: keys, matching and whole-family coverage.

This is the pure domain of the gate. It knows nothing about TOML files, the
manifest lock or the detector process; it accepts plain values and decides.

Allow entries name locations by key rather than by line span, because spans
churn whenever code above them moves. A key is ``path`` (a glob matched
against the repository-relative path with ``PurePosixPath.full_match``
semantics) optionally suffixed with ``::name`` to require nose's unit name as
well; ``::name`` keys never match the fragment-level findings that nose
reports without a name. An entry names one key (``unit = "..."``) or several
(``members = ["...", ...]``) and silences a family only when *every* location
in that family matches one of its keys, so a third, unlisted copy still
blocks. Entries are never unioned to excuse a family. Every entry records a
reason so exceptions stay reviewable in version control.
"""

from __future__ import annotations

import dataclasses as dc
import typing as typ

from df12_python_lints import _validate
from df12_python_lints._errors import ToolConfigError
from df12_python_lints._pathglob import full_match

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from .schema import Finding, Location

_MINIMUM_MEMBER_COUNT = 2


@dc.dataclass(frozen=True, slots=True)
class AllowEntry:
    """One reasoned exception.

    Attributes
    ----------
    keys : tuple[str, ...]
        Location keys covered by this entry, each ``path`` or ``path::name``.
    reason : str
        Reviewable justification recorded with the entry.
    """

    keys: tuple[str, ...]
    reason: str

    def matches(self, finding: Finding) -> bool:
        """Report whether this entry covers every location in ``finding``."""
        return all(
            any(key_matches(key, location) for key in self.keys)
            for location in finding.locations
        )


def key_matches(key: str, location: Location) -> bool:
    """Report whether one allow key covers one reported location.

    Examples
    --------
    >>> from df12_python_lints.duplication.schema import Location
    >>> place = Location(file="pkg/a.py", start=1, end=2, name="run")
    >>> key_matches("pkg/*.py", place), key_matches("pkg/*.py::other", place)
    (True, False)
    """
    path_glob, _, name = key.partition("::")
    if name and location.name != name:
        return False
    return full_match(location.file, path_glob)


def _has_blank_name(separator: str, name: str) -> bool:
    """Report whether a ``::`` suffix names no unit."""
    return bool(separator) and not name.strip()


def validate_key(key: str, *, context: str) -> str:
    """Validate one allow key and return it unchanged.

    Raises
    ------
    ToolConfigError
        If the key is not a well-formed, repository-relative ``path[::name]``.

    Examples
    --------
    >>> validate_key("pkg/a.py::run", context="--member")
    'pkg/a.py::run'
    """
    path_glob, separator, name = key.partition("::")
    if not path_glob.strip() or _has_blank_name(separator, name):
        msg = f"{context} must be a 'path' or 'path::name' key, got {key!r}"
        raise ToolConfigError(msg)
    if _validate.is_escaping_path(path_glob):
        msg = f"{context} must be a repository-relative path key, got {key!r}"
        raise ToolConfigError(msg)
    return key


def parse_entry(table: cabc.Mapping[str, object], *, context: str) -> AllowEntry:
    """Validate and normalize one allow entry given as a plain mapping.

    Raises
    ------
    ToolConfigError
        If the reason is blank, or the entry does not set exactly one of
        ``unit`` and ``members`` correctly.
    """
    reason = table.get("reason", "")
    if not _validate.is_non_empty_string(reason):
        msg = f"{context} requires a non-empty reason"
        raise ToolConfigError(msg)
    return AllowEntry(keys=_entry_keys(table, context=context), reason=reason)


def _entry_keys(table: cabc.Mapping[str, object], *, context: str) -> tuple[str, ...]:
    """Extract the location keys of one entry, enforcing unit XOR members."""
    unit, members = table.get("unit"), table.get("members")
    if (unit is None) == (members is None):
        msg = f"{context} must set exactly one of 'unit' or 'members'"
        raise ToolConfigError(msg)
    if unit is not None:
        return (validate_key(_unit_text(unit, context), context=f"{context} unit"),)
    return _member_keys(members, context)


def _unit_text(unit: object, context: str) -> str:
    """Require a ``unit`` value to be a string."""
    if not isinstance(unit, str):
        msg = f"{context} unit must be a 'path[::name]' string"
        raise ToolConfigError(msg)
    return unit


def _member_keys(members: object, context: str) -> tuple[str, ...]:
    """Validate a ``members`` array of two or more key strings."""
    if not _validate.is_sequence(members) or len(members) < _MINIMUM_MEMBER_COUNT:
        msg = f"{context} members must be two or more 'path[::name]' strings"
        raise ToolConfigError(msg)
    return tuple(
        validate_key(_member_text(member, context), context=f"{context} members")
        for member in members
    )


def _member_text(member: object, context: str) -> str:
    """Require one ``members`` item to be a string."""
    if not isinstance(member, str):
        msg = f"{context} members must be two or more 'path[::name]' strings"
        raise ToolConfigError(msg)
    return member


def partition_findings(
    findings: cabc.Sequence[Finding], allowlist: cabc.Sequence[AllowEntry]
) -> tuple[list[Finding], list[Finding], list[AllowEntry]]:
    """Split findings into blocking and allowed, and find unmatched entries.

    Returns
    -------
    tuple[list[Finding], list[Finding], list[AllowEntry]]
        Blocking findings, findings silenced by an entry covering every one
        of their locations, and entries that matched no finding in this scan.
    """
    blocking: list[Finding] = []
    allowed: list[Finding] = []
    used: set[int] = set()
    for finding in findings:
        matched = {
            position
            for position, entry in enumerate(allowlist)
            if entry.matches(finding)
        }
        used |= matched
        (allowed if matched else blocking).append(finding)
    unmatched = [
        entry for position, entry in enumerate(allowlist) if position not in used
    ]
    return blocking, allowed, unmatched
