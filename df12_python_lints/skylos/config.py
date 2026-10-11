"""Validation of the native ``[tool.skylos]`` schema the gate consumes.

Skylos sanitizes its configuration silently: a runtime entry point with no
selector, or a typo in a table shape, is dropped without a word, and a gate
without ``strict = true`` exits ``0`` with findings. This module fails closed
instead, naming the offending key, and never changes the configuration.

Two kinds of exception are kept distinct. A *documented whitelist* entry
(``[tool.skylos.whitelist.documented]``) suppresses findings by symbol name; a
*runtime entry-point exemption* (``[[tool.skylos.dead_code.entrypoints]]``)
is a typed rule that records why a framework reaches a symbol dynamically.
Both need a non-blank reason.
"""

from __future__ import annotations

import typing as typ

from df12_python_lints import _validate
from df12_python_lints._errors import ToolConfigError

if typ.TYPE_CHECKING:
    import collections.abc as cabc

SELECTOR_KEYS = (
    "name",
    "full_name",
    "decorator",
    "decorators",
    "base_class",
    "base_classes",
)
_STRING_OR_LIST_KEYS = (*SELECTOR_KEYS, "type", "module", "path")


def validate_native(data: cabc.Mapping[str, object]) -> tuple[str, ...]:
    """Validate the consumed ``[tool.skylos]`` tables of a parsed manifest.

    Parameters
    ----------
    data : collections.abc.Mapping[str, object]
        The parsed ``pyproject.toml``.

    Returns
    -------
    tuple[str, ...]
        Advisory warnings for constructs that are valid natively but weaken
        review, such as undocumented whitelist names. Warnings never fail.

    Raises
    ------
    ToolConfigError
        If the gate is not strict, or a consumed table has the wrong shape,
        or an exception lacks a reason or a selector.
    """
    tool = _validate.require_table(data.get("tool", {}), context="tool")
    if "skylos" not in tool:
        msg = "tool.skylos is required: Skylos reads its policy from [tool.skylos]"
        raise ToolConfigError(msg)
    skylos = _validate.require_table(tool["skylos"], context="tool.skylos")
    _validate_gate(skylos.get("gate"))
    if "exclude" in skylos:
        _validate.require_string_tuple(skylos["exclude"], context="tool.skylos.exclude")
    warnings = list(_validate_whitelist(skylos.get("whitelist")))
    warnings.extend(_validate_entry_points(skylos.get("dead_code")))
    return tuple(warnings)


def _validate_gate(value: object) -> None:
    """Require the strict gate: a lax gate exits zero with findings."""
    gate = _validate.require_table(value, context="tool.skylos.gate")
    if gate.get("strict") is not True:
        msg = (
            "tool.skylos.gate.strict must be true: a non-strict gate exits 0 "
            "with findings"
        )
        raise ToolConfigError(msg)


def _validate_whitelist(value: object) -> cabc.Iterator[str]:
    """Validate the whitelist tables; yield advisory warnings."""
    if value is None:
        return
    whitelist = _validate.require_table(value, context="tool.skylos.whitelist")
    names = whitelist.get("names", [])
    if not _validate.is_sequence(names):
        msg = "tool.skylos.whitelist.names must be an array of strings"
        raise ToolConfigError(msg)
    for index, name in enumerate(names):
        _validate.require_string(name, context=f"tool.skylos.whitelist.names[{index}]")
    if names:
        yield (
            f"tool.skylos.whitelist.names holds {len(names)} entries with no reason; "
            "prefer documented entries"
        )
    documented = _validate.require_table(
        whitelist.get("documented", {}), context="tool.skylos.whitelist.documented"
    )
    for symbol, reason in documented.items():
        _validate.require_string(symbol, context="tool.skylos.whitelist.documented key")
        _validate.require_string(
            reason, context=f"tool.skylos.whitelist.documented[{symbol!r}] reason"
        )


def _validate_entry_points(value: object) -> cabc.Iterator[str]:
    """Validate typed runtime entry-point exemptions; yield advisory warnings."""
    if value is None:
        return
    dead_code = _validate.require_table(value, context="tool.skylos.dead_code")
    rules = dead_code.get("entrypoints", [])
    if not _validate.is_sequence(rules):
        msg = "tool.skylos.dead_code.entrypoints must be an array of tables"
        raise ToolConfigError(msg)
    for index, rule in enumerate(rules):
        context = f"tool.skylos.dead_code.entrypoints[{index}]"
        table = _validate.require_table(rule, context=context)
        _validate_rule(table, context=context)
        if "type" not in table:
            yield f"{context} has no type; the shared contract expects one"


def _validate_rule(table: cabc.Mapping[str, object], *, context: str) -> None:
    """Validate one entry-point rule's fields, selector and reason."""
    _validate.require_string(table.get("reason"), context=f"{context}.reason")
    for key in _STRING_OR_LIST_KEYS:
        if key in table:
            _require_string_or_list(table[key], context=f"{context}.{key}")
    parent = table.get("parent")
    if parent is not None:
        _validate.require_table(parent, context=f"{context}.parent")
    if not (parent or any(table.get(key) for key in SELECTOR_KEYS)):
        msg = (
            f"{context} selects nothing: Skylos silently drops a rule without "
            f"one of {', '.join(SELECTOR_KEYS)} or parent"
        )
        raise ToolConfigError(msg)


def _require_string_or_list(value: object, *, context: str) -> None:
    """Accept a non-blank string or a non-empty array of non-blank strings."""
    if isinstance(value, str):
        _validate.require_string(value, context=context)
        return
    if not _validate.is_sequence(value) or not value:
        msg = f"{context} must be a non-empty string or array of strings"
        raise ToolConfigError(msg)
    _validate.require_string_tuple(value, context=context)
