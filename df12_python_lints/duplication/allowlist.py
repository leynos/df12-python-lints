"""Reasoned exceptions to the duplication gate.

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
import tomllib
import typing as typ

from df12_python_lints import _validate
from df12_python_lints._errors import ToolConfigError
from df12_python_lints._manifest import edit_manifest
from df12_python_lints._pathglob import full_match

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    import tomlkit

    from .schema import Finding, Location

_MINIMUM_MEMBER_COUNT = 2
_EXTRA = "duplication"


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


def load_allowlist(pyproject: pathlib.Path) -> tuple[AllowEntry, ...]:
    """Load the reasoned allow entries from ``[tool.duplication_gate]``.

    Raises
    ------
    ToolConfigError
        If the file is unreadable, a table has the wrong shape, or an entry
        lacks a reason or names neither a unit nor members.
    """
    try:
        with pyproject.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        msg = f"cannot load duplication allowlist from {pyproject}: {error}"
        raise ToolConfigError(msg) from error
    tool = _validate.require_table(data.get("tool", {}), context="tool")
    gate = _validate.require_table(
        tool.get("duplication_gate", {}), context="tool.duplication_gate"
    )
    return _entries(gate.get("allow", ()))


def _entries(raw: object) -> tuple[AllowEntry, ...]:
    """Validate the ``allow`` array of tables."""
    if not _validate.is_sequence(raw):
        msg = "tool.duplication_gate.allow must be an array of tables"
        raise ToolConfigError(msg)
    return tuple(_entry(item, index=index) for index, item in enumerate(raw))


def _entry(raw: object, *, index: int) -> AllowEntry:
    """Validate and normalize one TOML allow entry."""
    context = f"tool.duplication_gate.allow[{index}]"
    table = _validate.require_table(raw, context=context)
    reason = table.get("reason", "")
    if not _validate.is_non_empty_string(reason):
        msg = f"{context} requires a non-empty reason"
        raise ToolConfigError(msg)
    return AllowEntry(keys=_entry_keys(table, context=context), reason=reason)


def _entry_keys(table: cabc.Mapping[str, object], *, context: str) -> tuple[str, ...]:
    """Extract and validate the location keys named by one entry."""
    unit, members = table.get("unit"), table.get("members")
    if (unit is None) == (members is None):
        msg = f"{context} must set exactly one of 'unit' or 'members'"
        raise ToolConfigError(msg)
    if unit is not None:
        if not isinstance(unit, str):
            msg = f"{context} unit must be a 'path[::name]' string"
            raise ToolConfigError(msg)
        return (validate_key(unit, context=f"{context} unit"),)
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


def record_allow_entry(
    pyproject: pathlib.Path, *, members: cabc.Sequence[str], reason: str
) -> str:
    """Record one exception covering a whole family, idempotently.

    The write happens under the shared manifest lock. An entry already
    naming the same set of keys has only its reason updated; nothing is
    written when the reason is unchanged.

    Parameters
    ----------
    pyproject : pathlib.Path
        The target manifest.
    members : collections.abc.Sequence[str]
        One or more location keys, repeated and unordered input accepted.
    reason : str
        Reviewable justification; must not be blank.

    Returns
    -------
    str
        ``"added"``, ``"updated"`` or ``"unchanged"``.

    Raises
    ------
    ToolConfigError
        If the reason or a key is invalid, or the manifest is malformed.
        The manifest is left untouched.
    """
    if not _validate.is_non_empty_string(reason):
        msg = "--reason must not be empty"
        raise ToolConfigError(msg)
    keys = tuple(
        dict.fromkeys(validate_key(key, context="--member") for key in members)
    )
    if not keys:
        msg = "at least one --member is required"
        raise ToolConfigError(msg)
    outcome: list[str] = []

    def edit(document: tomlkit.TOMLDocument) -> bool:
        """Apply the request inside the locked transaction."""
        outcome.append(_apply(document, keys, reason))
        return outcome[-1] != "unchanged"

    edit_manifest(pyproject, edit, extra=_EXTRA)
    return outcome[0]


def _apply(document: tomlkit.TOMLDocument, keys: tuple[str, ...], reason: str) -> str:
    """Add or update the entry for ``keys`` inside a parsed manifest."""
    import tomlkit
    import tomlkit.items

    tool = document.setdefault("tool", tomlkit.table(is_super_table=True))
    gate = tool.setdefault("duplication_gate", tomlkit.table())
    entries = gate.setdefault("allow", tomlkit.aot())
    if not isinstance(entries, tomlkit.items.AoT):
        msg = (
            "tool.duplication_gate.allow must use [[tool.duplication_gate.allow]] "
            "tables to be edited"
        )
        raise ToolConfigError(msg)
    for index, raw in enumerate(entries):
        existing = _entry(raw, index=index)
        if set(existing.keys) == set(keys):
            if existing.reason == reason:
                return "unchanged"
            raw["reason"] = reason
            return "updated"
    entry = tomlkit.table()
    if len(keys) == 1:
        entry["unit"] = keys[0]
    else:
        entry["members"] = list(keys)
    entry["reason"] = reason
    entries.append(entry)
    return "added"
