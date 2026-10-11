"""Regenerate ``full_match_corpus.json`` from the interpreter's own matcher.

Run with Python 3.13 or later::

    python tests/data/generate_full_match_corpus.py

The corpus records what ``PurePosixPath.full_match`` answers (or the
exception type it raises), so the Python 3.12 port in
``df12_python_lints._pathglob`` can be checked against it on every
supported interpreter.
"""

from __future__ import annotations

import json
import pathlib
import random

_SEGMENTS = ["a", "b", "x.py", ".h", "c", "é", ".", ""]
_PIECES = [
    "a", "b", ".", "..", "*", "**", "?", "[ab]", "[!a]", "[a-c]", "[", "]",
    "x.py", "*.py", ".h", "", "-", "[]]", "[a-", "é", "*.p?", "**.py", "a*",
]  # fmt: skip
_COUNT = 4000


def _answer(path: str, pattern: str) -> bool | str:
    """Return the native answer, or the name of the exception it raises."""
    try:
        return pathlib.PurePosixPath(path).full_match(pattern)  # ty: ignore[unresolved-attribute]
    except Exception as error:  # ruff: ignore[blind-except] - recording the exception type is the point.
        return type(error).__name__


def main() -> None:
    """Write the corpus next to this script."""
    rng = random.Random(20261011)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - deterministic corpus, not security.
    cases: set[tuple[str, str]] = set()
    while len(cases) < _COUNT:
        path = "/".join(rng.choice(_SEGMENTS) for _ in range(rng.randint(0, 4)))
        pattern = "/".join(rng.choice(_PIECES) for _ in range(rng.randint(0, 4)))
        cases.add((path, pattern))
    rows = [[path, pattern, _answer(path, pattern)] for path, pattern in sorted(cases)]
    target = pathlib.Path(__file__).with_name("full_match_corpus.json")
    target.write_text(
        json.dumps(rows, ensure_ascii=False, indent=0) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
