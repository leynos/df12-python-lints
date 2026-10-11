r"""POSIX ``PurePath.full_match`` semantics for Python 3.12.

``PurePosixPath.full_match`` arrived in Python 3.13. On 3.13 and later this
module delegates to it unchanged, so behaviour and exception scope are the
interpreter's own. On 3.12 it applies a port of CPython's ``glob.translate``
(``recursive=True``, ``include_hidden=True``) and ``fnmatch._translate``,
which is what ``full_match`` compiles on 3.14. The port is a translation of
the CPython sources (Copyright (c) Python Software Foundation, PSF licence
version 2); the only change is ``\\Z`` for the end anchor, which Python
spells ``\\z`` from 3.14 and which means the same thing.

``tests/data/full_match_corpus.json`` pins the 3.14 answers so the port is
checked on 3.12, and a differential test compares it with the native method
wherever that exists.
"""

from __future__ import annotations

import functools
import pathlib
import re
import typing as typ

_SEPARATOR = "/"
_NOT_SEPARATOR = "[^/]"
_ONE_LAST_SEGMENT = f"{_NOT_SEPARATOR}+"
_ONE_SEGMENT = f"{_ONE_LAST_SEGMENT}/"
_ANY_SEGMENTS = "(?:.+/)?"
_ANY_LAST_SEGMENTS = ".*"
_SETOPS = re.compile(r"([&~|])").sub


def full_match(path: str, pattern: str) -> bool:
    """Report whether a POSIX ``path`` matches the whole glob ``pattern``.

    ``*`` and ``?`` do not cross ``/``; ``**`` as a complete segment matches
    any number of segments; dotted segments are matched like any other.

    Parameters
    ----------
    path : str
        Repository-relative POSIX path.
    pattern : str
        Glob pattern, normalized as ``pathlib`` normalizes a path.

    Returns
    -------
    bool
        ``True`` when the pattern matches the entire path.

    Examples
    --------
    >>> full_match("pkg/a/b.py", "pkg/**/*.py"), full_match("pkg/a/b.py", "*.py")
    (True, False)
    """
    candidate = pathlib.PurePosixPath(path)
    native = getattr(candidate, "full_match", None)
    if native is not None:
        return typ.cast("bool", native(pattern))
    return _compile(_pattern_text(pattern)).match(_path_text(candidate)) is not None


def _path_text(path: pathlib.PurePosixPath) -> str:
    """Return the matchable text of a path; an empty path is the empty string."""
    return str(path) if path.parts else ""


def _pattern_text(pattern: str) -> str:
    """Normalize a pattern the way ``PurePosixPath`` normalizes a path."""
    return _path_text(pathlib.PurePosixPath(pattern))


@functools.lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern[str]:
    """Compile a normalized pattern to a case-sensitive regular expression."""
    return re.compile(_translate(pattern))


def _translate(pattern: str) -> str:
    """Translate a normalized glob into a regular expression (``glob.translate``)."""
    parts = pattern.split(_SEPARATOR)
    last = len(parts) - 1
    regexes = (_part_regex(parts, index, last) for index in range(len(parts)))
    return rf"(?s:{''.join(regexes)})\Z"


def _part_regex(parts: list[str], index: int, last: int) -> str:
    """Return the regular expression for the path segment at ``index``."""
    part = parts[index]
    if part == "*":
        return _ONE_SEGMENT if index < last else _ONE_LAST_SEGMENT
    if part == "**":
        return _recursive_regex(parts, index, last)
    body = "".join(_translate_segment(part))
    return body if index == last else f"{body}/"


def _recursive_regex(parts: list[str], index: int, last: int) -> str:
    """Return the expression for a ``**`` segment; adjacent ones collapse."""
    if index == last:
        return _ANY_LAST_SEGMENTS
    return "" if parts[index + 1] == "**" else _ANY_SEGMENTS


def _translate_segment(part: str) -> list[str]:
    """Translate one path segment (``fnmatch._translate`` for ``glob``).

    ``*`` becomes ``[^/]*`` and ``?`` becomes ``[^/]``; bracket expressions
    keep fnmatch's range, negation and set-operation escaping rules.
    """
    res: list[str] = []
    i = 0
    while i < len(part):
        c = part[i]
        i += 1
        if c == "*":
            res.append(f"{_NOT_SEPARATOR}*")
            i = _skip_stars(part, i)
        elif c == "[":
            i = _translate_set(part, i, res)
        else:
            res.append(_NOT_SEPARATOR if c == "?" else re.escape(c))
    return res


def _skip_stars(part: str, index: int) -> int:
    """Return the index after any run of ``*`` characters starting at ``index``."""
    while index < len(part) and part[index] == "*":
        index += 1
    return index


def _translate_set(part: str, start: int, res: list[str]) -> int:
    """Append one bracket expression opening before ``start``; return the next index."""
    end = _closing_bracket(part, start)
    if end is None:
        res.append("\\[")
        return start
    res.append(_set_expression(_set_body(part, start, end)))
    return end + 1


def _closing_bracket(part: str, start: int) -> int | None:
    """Return the index of the ``]`` closing a set opened before ``start``."""
    index = start
    if part[index : index + 1] == "!":
        index += 1
    if part[index : index + 1] == "]":
        index += 1
    found = part.find("]", index)
    return None if found < 0 else found


def _set_expression(stuff: str) -> str:
    """Wrap an escaped set body as a regular-expression character class."""
    if not stuff:
        return "(?!)"
    if stuff == "!":
        return "."
    stuff = _SETOPS(r"\\\1", stuff)
    if stuff[0] == "!":
        return "[^" + stuff[1:] + "]"
    return "[\\" + stuff + "]" if stuff[0] in {"^", "["} else f"[{stuff}]"


def _set_body(part: str, start: int, end: int) -> str:
    """Return the escaped body of the bracket expression ``part[start:end]``."""
    stuff = part[start:end]
    if "-" not in stuff:
        return _escape_backslash(stuff)
    chunks = _merge_ranges(_range_chunks(part, start, end))
    return "-".join(_escape_backslash(c).replace("-", r"\-") for c in chunks)


def _escape_backslash(text: str) -> str:
    """Escape backslashes for use inside a regular-expression set."""
    return text.replace("\\", r"\\")


def _range_chunks(part: str, start: int, end: int) -> list[str]:
    """Split a set body at the hyphens that form ranges."""
    chunks: list[str] = []
    index = start
    found = start + 2 if part[start] == "!" else start + 1
    while True:
        found = part.find("-", found, end)
        if found < 0:
            break
        chunks.append(part[index:found])
        index = found + 1
        found += 3
    tail = part[index:end]
    if tail:
        chunks.append(tail)
    else:
        chunks[-1] += "-"
    return chunks


def _merge_ranges(chunks: list[str]) -> list[str]:
    """Drop empty ranges, which are invalid in a regular expression."""
    for index in range(len(chunks) - 1, 0, -1):
        if chunks[index - 1][-1] > chunks[index][0]:
            chunks[index - 1] = chunks[index - 1][:-1] + chunks[index][1:]
            del chunks[index]
    return chunks
