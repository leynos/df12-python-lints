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
    one_last_segment = f"{_NOT_SEPARATOR}+"
    one_segment = f"{one_last_segment}/"
    any_segments = "(?:.+/)?"
    any_last_segments = ".*"
    results: list[str] = []
    parts = pattern.split(_SEPARATOR)
    last_index = len(parts) - 1
    for index, part in enumerate(parts):
        if part == "*":
            results.append(one_segment if index < last_index else one_last_segment)
        elif part == "**":
            if index == last_index:
                results.append(any_last_segments)
            elif parts[index + 1] != "**":
                results.append(any_segments)
        else:
            if part:
                results.extend(_translate_segment(part))
            if index < last_index:
                results.append("/")
    return rf"(?s:{''.join(results)})\Z"


def _translate_segment(part: str) -> list[str]:
    """Translate one path segment (``fnmatch._translate`` for ``glob``).

    ``*`` becomes ``[^/]*`` and ``?`` becomes ``[^/]``; bracket expressions
    keep fnmatch's range, negation and set-operation escaping rules.
    """
    res: list[str] = []
    i, n = 0, len(part)
    while i < n:
        c = part[i]
        i += 1
        if c == "*":
            res.append(f"{_NOT_SEPARATOR}*")
            while i < n and part[i] == "*":
                i += 1
        elif c == "?":
            res.append(_NOT_SEPARATOR)
        elif c == "[":
            i = _translate_set(part, i, res)
        else:
            res.append(re.escape(c))
    return res


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
    n = len(part)
    j = start
    if j < n and part[j] == "!":
        j += 1
    if j < n and part[j] == "]":
        j += 1
    while j < n and part[j] != "]":
        j += 1
    return None if j >= n else j


def _set_expression(stuff: str) -> str:
    """Wrap an escaped set body as a regular-expression character class."""
    if not stuff:
        return "(?!)"
    if stuff == "!":
        return "."
    stuff = _SETOPS(r"\\\1", stuff)
    if stuff[0] == "!":
        stuff = "^" + stuff[1:]
    elif stuff[0] in {"^", "["}:
        stuff = "\\" + stuff
    return f"[{stuff}]"


def _set_body(part: str, start: int, end: int) -> str:
    """Return the escaped body of the bracket expression ``part[start:end]``."""
    stuff = part[start:end]
    if "-" not in stuff:
        return stuff.replace("\\", r"\\")
    chunks: list[str] = []
    i = start
    k = i + 2 if part[i] == "!" else i + 1
    while True:
        k = part.find("-", k, end)
        if k < 0:
            break
        chunks.append(part[i:k])
        i = k + 1
        k += 3
    chunk = part[i:end]
    if chunk:
        chunks.append(chunk)
    else:
        chunks[-1] += "-"
    for index in range(len(chunks) - 1, 0, -1):
        if chunks[index - 1][-1] > chunks[index][0]:
            chunks[index - 1] = chunks[index - 1][:-1] + chunks[index][1:]
            del chunks[index]
    return "-".join(c.replace("\\", r"\\").replace("-", r"\-") for c in chunks)
