"""Reading and editing the duplication exceptions in ``pyproject.toml``.

The decisions live in :mod:`.policy`; this module is the infrastructure that
reads the ``[[tool.duplication_gate.allow]]`` tables and records new entries
through the shared comment-preserving manifest transaction.
"""

from __future__ import annotations

import tomllib
import typing as typ

from df12_python_lints import _validate
from df12_python_lints._errors import ToolConfigError
from df12_python_lints._manifest import edit_manifest

from .policy import AllowEntry, parse_entry, validate_key

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    import tomlkit

_EXTRA = "duplication"


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
    """Validate one TOML allow entry."""
    context = f"tool.duplication_gate.allow[{index}]"
    table = _validate.require_table(raw, context=context)
    return parse_entry(table, context=context)


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
