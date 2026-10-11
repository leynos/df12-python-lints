"""Validation helpers for consumed TOML tables and detector reports.

Each helper raises :class:`~df12_python_lints._errors.ToolConfigError`
with the configuration path in the message, so a consumer can find the
offending key.
"""

from __future__ import annotations

import collections.abc as cabc
import pathlib
import typing as typ

from ._errors import ToolConfigError

if typ.TYPE_CHECKING:
    from ._compat import TypeIs


def is_non_empty_string(value: object) -> TypeIs[str]:
    """Report whether ``value`` is a string with a non-blank character.

    Examples
    --------
    >>> is_non_empty_string("a"), is_non_empty_string("  "), is_non_empty_string(1)
    (True, False, False)
    """
    return isinstance(value, str) and bool(value.strip())


def is_integer(value: object) -> TypeIs[int]:
    """Report whether ``value`` is an integer rather than a boolean.

    Examples
    --------
    >>> is_integer(3), is_integer(True)
    (True, False)
    """
    return isinstance(value, int) and not isinstance(value, bool)


def is_sequence(value: object) -> TypeIs[cabc.Sequence[object]]:
    """Report whether ``value`` is a non-string sequence."""
    return isinstance(value, cabc.Sequence) and not isinstance(value, (str, bytes))


def is_escaping_path(path: str) -> bool:
    r"""Report whether a configured path is absolute, escapes upward or uses ``\``.

    Examples
    --------
    >>> is_escaping_path("src/pkg"), is_escaping_path("../x"), is_escaping_path("/etc")
    (False, True, True)
    """
    parts = pathlib.PurePosixPath(path).parts
    return path.startswith("/") or ".." in parts or "\\" in path


def require_table(value: object, *, context: str) -> cabc.Mapping[str, object]:
    """Validate one TOML table before configuration logic consumes it.

    Parameters
    ----------
    value : object
        Candidate TOML value.
    context : str
        Configuration path used in the diagnostic.

    Returns
    -------
    collections.abc.Mapping[str, object]
        The validated table.

    Raises
    ------
    ToolConfigError
        If ``value`` is not a table with string keys.
    """
    if not isinstance(value, cabc.Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        msg = f"{context} must be a table with string keys"
        raise ToolConfigError(msg)
    return typ.cast("cabc.Mapping[str, object]", value)


def require_string(value: object, *, context: str) -> str:
    """Validate one required non-blank configuration string.

    Raises
    ------
    ToolConfigError
        If ``value`` is not a non-blank string.

    Examples
    --------
    >>> require_string("x", context="tool.nose.mode")
    'x'
    """
    if not is_non_empty_string(value):
        msg = f"{context} must be a non-empty string"
        raise ToolConfigError(msg)
    return value


def require_string_tuple(value: object, *, context: str) -> tuple[str, ...]:
    """Validate one configuration array of non-blank strings.

    Raises
    ------
    ToolConfigError
        If ``value`` is not an array of non-blank strings.
    """
    if not is_sequence(value):
        msg = f"{context} must be an array of strings"
        raise ToolConfigError(msg)
    return tuple(require_string(item, context=f"{context}[]") for item in value)


def require_integer(value: object, *, context: str, minimum: int) -> int:
    """Validate one configuration integer that is at least ``minimum``.

    Raises
    ------
    ToolConfigError
        If ``value`` is not an integer, or is below ``minimum``.
    """
    if not is_integer(value) or value < minimum:
        kind = "a positive integer" if minimum == 1 else f"an integer >= {minimum}"
        msg = f"{context} must be {kind}"
        raise ToolConfigError(msg)
    return value
