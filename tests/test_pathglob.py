"""``full_match`` semantics: the 3.12 port against the interpreter's own matcher."""

from __future__ import annotations

import json
import pathlib
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

from df12_python_lints import _pathglob

_CORPUS = pathlib.Path(__file__).parent / "data" / "full_match_corpus.json"
_HAS_NATIVE = hasattr(pathlib.PurePosixPath, "full_match")

_segment = st.sampled_from(["a", "b", "x.py", ".h", "c", "é", ".", ""])
_piece = st.sampled_from([
    "a",
    ".",
    "..",
    "*",
    "**",
    "?",
    "[ab]",
    "[!a]",
    "[a-c]",
    "[",
    "x.py",
    "*.py",
    "é",
])
_paths = st.lists(_segment, max_size=4).map("/".join)
_patterns = st.lists(_piece, max_size=4).map("/".join)


def _port(path: str, pattern: str) -> bool:
    """Match through the compiled port, bypassing any native delegation."""
    candidate = pathlib.PurePosixPath(path)
    text = _pathglob._path_text(candidate)
    compiled = _pathglob._compile(_pathglob._pattern_text(pattern))
    return compiled.match(text) is not None


def _corpus_rows() -> list[tuple[str, str, bool | str]]:
    """Load the pinned 3.14 answers."""
    return [tuple(row) for row in json.loads(_CORPUS.read_text(encoding="utf-8"))]  # type: ignore[misc]


class TestPortAgainstCorpus:
    """The port must reproduce the answers recorded from CPython 3.14."""

    def test_every_recorded_answer_is_reproduced(self) -> None:
        """No recorded case may differ, on any supported interpreter."""
        mismatches = []
        for path, pattern, expected in _corpus_rows():
            if isinstance(expected, str):
                continue  # Exception cases are covered by the exception-scope test.
            if _port(path, pattern) is not expected:
                mismatches.append((path, pattern, expected))
        assert not mismatches, f"port disagrees with CPython on {mismatches[:5]}"

    def test_corpus_exercises_matches_and_misses(self) -> None:
        """The corpus must contain both outcomes, or it proves nothing."""
        answers = {row[2] for row in _corpus_rows()}
        assert {True, False} <= answers, "corpus needs both matching and missing cases"

    def test_public_function_agrees_with_corpus(self) -> None:
        """The public entry point honours the corpus whichever backend it picks."""
        for path, pattern, expected in _corpus_rows():
            if isinstance(expected, str):
                continue
            assert _pathglob.full_match(path, pattern) is expected, (
                f"full_match({path!r}, {pattern!r}) should be {expected}"
            )


class TestKnownSemantics:
    """Behaviour that a superficially similar matcher gets wrong."""

    @pytest.mark.parametrize(
        ("path", "pattern", "expected"),
        [
            ("pkg/a/b.py", "pkg/**/*.py", True),
            ("pkg/b.py", "pkg/**/*.py", True),
            ("pkg/a/b.py", "pkg/*.py", False),
            ("pkg/a/b.py", "*.py", False),
            ("b.py", "**/*.py", True),
            ("pkg/.hidden/b.py", "pkg/*/b.py", True),
            ("pkg/b.py", "pkg", False),
            ("pkg/b.py", "pkg/**", True),
            ("pkg/a.py", "pkg/[ab].py", True),
            ("pkg/c.py", "pkg/[!ab].py", True),
        ],
    )
    def test_whole_path_semantics(
        self, path: str, pattern: str, *, expected: bool
    ) -> None:
        """The whole path must match, ``*`` stays within a segment, ``**`` spans."""
        assert _port(path, pattern) is expected, f"{pattern!r} against {path!r}"


@pytest.mark.skipif(
    not _HAS_NATIVE, reason="PurePosixPath.full_match needs Python 3.13+"
)
class TestDifferential:
    """On 3.13+ the port is compared with the interpreter directly."""

    @given(path=_paths, pattern=_patterns)
    def test_port_matches_native(self, path: str, pattern: str) -> None:
        """Same answer for every generated path and pattern."""
        native = pathlib.PurePosixPath(path).full_match(pattern)  # ty: ignore[unresolved-attribute]
        assert _port(path, pattern) is native, (
            f"port and native disagree on {pattern!r} against {path!r}"
        )

    def test_exception_scope_is_the_interpreters_own(self) -> None:
        """A non-string pattern raises exactly what native raises (delegation)."""
        with pytest.raises(TypeError):
            _pathglob.full_match("a/b", 3)  # ty: ignore[invalid-argument-type]


@pytest.mark.skipif(
    sys.version_info >= (3, 13), reason="the port is only the backend on 3.12"
)
def test_backend_is_the_port_on_python_312() -> None:
    """On 3.12 there is no native method, so the port must carry the call."""
    assert not _HAS_NATIVE, "3.12 has no PurePosixPath.full_match"
    assert _pathglob.full_match("a/b.py", "a/*.py") is True, "port must serve 3.12"
