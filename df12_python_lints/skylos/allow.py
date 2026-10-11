"""Safe authoring of one documented Skylos whitelist exception.

Native ``skylos whitelist`` rewrites ``pyproject.toml`` with text
substitution, so a reason containing a quote or a backslash corrupts the file,
and it takes no lock. This module writes the same native schema,
``[tool.skylos.whitelist.documented]``, through the shared comment-preserving
transaction and its single lock protocol.
"""

from __future__ import annotations

import collections.abc as cabc
import keyword
import typing as typ

from df12_python_lints import _validate
from df12_python_lints._errors import ToolConfigError
from df12_python_lints._manifest import edit_manifest

if typ.TYPE_CHECKING:
    import pathlib

    import tomlkit

_EXTRA = "skylos"


def validate_symbol(symbol: str) -> str:
    """Validate a symbol for the documented whitelist and return it.

    Native Skylos compares each whitelist key with ``fnmatch`` against a
    definition's *simple* name. A wildcard would silently excuse a whole
    family of names, and a dotted name can never match, so only a plain
    Python identifier is accepted. Qualified or pattern-based exemptions are
    runtime entry points, which are reviewed and recorded by hand.

    Raises
    ------
    ToolConfigError
        If ``symbol`` is blank, a keyword, or not a plain identifier.

    Examples
    --------
    >>> validate_symbol("_write_mode")
    '_write_mode'
    """
    if not symbol.strip():
        msg = "--symbol must not be empty"
        raise ToolConfigError(msg)
    if not symbol.isidentifier() or keyword.iskeyword(symbol):
        msg = (
            f"--symbol {symbol!r} must be a plain Python identifier: the native "
            "whitelist matches simple names and treats '*', '?' and '[' as "
            "wildcards. Use a typed runtime entry point for qualified names."
        )
        raise ToolConfigError(msg)
    return symbol


def record_whitelist_entry(pyproject: pathlib.Path, *, symbol: str, reason: str) -> str:
    """Record one documented whitelist exception, idempotently.

    Parameters
    ----------
    pyproject : pathlib.Path
        The target manifest.
    symbol : str
        A plain identifier; see :func:`validate_symbol`.
    reason : str
        Reviewable justification; must not be blank. Stored literally.

    Returns
    -------
    str
        ``"added"``, ``"updated"`` (a different reason replaced the old one)
        or ``"unchanged"``.

    Raises
    ------
    ToolConfigError
        If the request or the manifest is invalid; the manifest is untouched.
    """
    validate_symbol(symbol)
    if not _validate.is_non_empty_string(reason):
        msg = "--reason must not be empty"
        raise ToolConfigError(msg)
    outcome: list[str] = []

    def edit(document: tomlkit.TOMLDocument) -> bool:
        """Apply the request inside the locked transaction."""
        outcome.append(_apply(document, symbol, reason))
        return outcome[-1] != "unchanged"

    edit_manifest(pyproject, edit, extra=_EXTRA)
    return outcome[0]


def _apply(document: tomlkit.TOMLDocument, symbol: str, reason: str) -> str:
    """Add or update ``symbol`` under ``[tool.skylos.whitelist.documented]``."""
    import tomlkit

    tool = _table(document.get("tool"), "tool")
    skylos = _table(tool.get("skylos"), "tool.skylos")
    whitelist = skylos.get("whitelist")
    if whitelist is None:
        whitelist = skylos.setdefault("whitelist", tomlkit.table(is_super_table=True))
    whitelist = _table(whitelist, "tool.skylos.whitelist")
    created = "documented" not in whitelist
    documented = _table(
        whitelist.setdefault("documented", tomlkit.table()),
        "tool.skylos.whitelist.documented",
    )
    existing = documented.get(symbol)
    if existing is not None and str(existing) == reason:
        return "unchanged"
    documented[symbol] = reason
    if created:
        # Keep a blank line between the new table and whatever follows it.
        documented.add(tomlkit.nl())
    return "added" if existing is None else "updated"


def _table(value: object, context: str) -> typ.Any:  # ruff: ignore[any-type] - tomlkit container.
    """Require an existing table, so a wrong shape is refused, not rewritten."""
    if value is None:
        msg = f"{context} is missing; add [tool.skylos] before recording exceptions"
        if context in {"tool", "tool.skylos"}:
            msg = (
                "tool.skylos is required: add [tool.skylos] before recording exceptions"
            )
        raise ToolConfigError(msg)
    if not isinstance(value, cabc.MutableMapping):
        msg = f"{context} must be a table to record a whitelist exception"
        raise ToolConfigError(msg)
    return value
