"""Hypothesis property tests for suppression pragma classification."""

from __future__ import annotations

import io
import tokenize

from hypothesis import given, settings
from hypothesis import strategies as st
from pylint import testutils

from df12_python_lints.suppressions import SuppressionCommentChecker

_WORDS = st.from_regex(r"[a-z]{2,8}", fullmatch=True)
_RUFF_DIRECTIVE_KINDS = st.sampled_from(("ignore", "file-ignore", "disable"))
_RUFF_SELECTORS = st.lists(
    st.one_of(
        st.from_regex(r"[A-Z]{1,3}[0-9]{2,4}", fullmatch=True),
        st.from_regex(r"[a-z]{2,8}(?:-[a-z]{2,8})?", fullmatch=True),
    ),
    min_size=1,
    max_size=3,
)
_RUFF_WHITESPACE = st.sampled_from(("", " ", "  ", "\t"))
_RUFF_SEPARATOR = st.sampled_from((",", ", ", " , "))
_RUFF_BARE_CASES = st.tuples(
    _RUFF_DIRECTIVE_KINDS,
    _RUFF_SELECTORS,
    _RUFF_WHITESPACE,
    _RUFF_WHITESPACE,
    _RUFF_SEPARATOR,
    st.booleans(),
)
_RUFF_EXPLAINED_CASES = st.tuples(
    _RUFF_DIRECTIVE_KINDS,
    _RUFF_SELECTORS,
    _RUFF_WHITESPACE,
    st.sampled_from(("inline", "preceding")),
    _WORDS,
    _WORDS,
)


def _token_symbols(code: str) -> list[str]:
    """Collect the suppression checker's symbols over *code*."""
    linter = testutils.UnittestLinter()
    checker = SuppressionCommentChecker(linter)
    tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    checker.process_tokens(tokens)
    return [message.msg_id for message in linter.release_messages()]


class TestSuppressionProperties:
    """Generated pragmas are classified uniformly."""

    @settings(deadline=None)
    @given(case=_RUFF_BARE_CASES)
    def test_bare_ruff_suppressions_always_fire(
        self,
        case: tuple[str, list[str], str, str, str, bool],
    ) -> None:
        """Every valid Ruff suppression opener without prose is reported."""
        kind, selectors, after_colon, before_bracket, separator, has_trailing_comma = (
            case
        )
        selector_list = separator.join(selectors)
        trailing_comma = "," if has_trailing_comma else ""
        directive = (
            f"# ruff:{after_colon}{kind}{before_bracket}"
            f"[{selector_list}{trailing_comma}]"
        )
        assert _token_symbols(f"{directive}\nx = 1\n") == [
            "lint-suppression-without-explanation"
        ], "every bare Ruff suppression grammar variant must be reported"

    @settings(deadline=None)
    @given(case=_RUFF_EXPLAINED_CASES)
    def test_prose_explains_every_ruff_suppression(
        self,
        case: tuple[str, list[str], str, str, str, str],
    ) -> None:
        """Inline or preceding prose explains every Ruff suppression form."""
        kind, selectors, before_bracket, explanation_placement, first, second = case
        directive = f"# ruff: {kind}{before_bracket}[{', '.join(selectors)}]"
        explanation = f"# {first} {second}"
        code = (
            f"{directive}  {explanation}\nx = 1\n"
            if explanation_placement == "inline"
            else f"{explanation}\n{directive}\nx = 1\n"
        )
        assert _token_symbols(code) == [], (
            "valid explanatory prose must take precedence over the directive"
        )

    @settings(deadline=None)
    @given(
        selectors=_RUFF_SELECTORS,
        before_bracket=_RUFF_WHITESPACE,
    )
    def test_ruff_enable_is_always_neutral(
        self, selectors: list[str], before_bracket: str
    ) -> None:
        """A Ruff range terminator neither fires nor explains a suppression."""
        selector_list = ", ".join(selectors)
        enable = f"# ruff: enable{before_bracket}[{selector_list}]"
        suppression = f"# ruff: ignore{before_bracket}[{selector_list}]"
        assert _token_symbols(f"{enable}\n") == [], (
            "a range terminator must not require an explanation"
        )
        assert _token_symbols(f"{enable}\n{suppression}\nx = 1\n") == [
            "lint-suppression-without-explanation"
        ], "a range terminator must not explain the next suppression"

    @settings(deadline=None)
    @given(
        codes=st.lists(
            st.from_regex(r"[A-Z]{1,3}[0-9]{2,4}", fullmatch=True),
            min_size=1,
            max_size=3,
        )
    )
    def test_bare_noqa_always_fires(self, codes: list[str]) -> None:
        """A noqa pragma with any code list and no prose is reported."""
        code = f"x = 1  # noqa: {', '.join(codes)}\n"
        assert _token_symbols(code) == ["lint-suppression-without-explanation"], (
            "a bare noqa must be reported whatever its code list"
        )

    @settings(deadline=None)
    @given(
        codes=st.lists(
            st.from_regex(r"[A-Z][0-9]{3}", fullmatch=True), min_size=1, max_size=3
        ),
        first=_WORDS,
        second=_WORDS,
    )
    def test_prose_always_explains(
        self, codes: list[str], first: str, second: str
    ) -> None:
        """Two-word prose after a second hash explains any pragma."""
        code = f"x = 1  # noqa: {', '.join(codes)}  # {first} {second}\n"
        assert _token_symbols(code) == [], (
            "prose after a second hash must count as an explanation"
        )

    @settings(deadline=None)
    @given(names=st.lists(_WORDS, min_size=1, max_size=3))
    def test_bare_pylint_disable_always_fires(self, names: list[str]) -> None:
        """A pylint disable pragma with any name list is reported."""
        code = f"x = 1  # pylint: disable={','.join(names)}\n"
        assert _token_symbols(code) == ["lint-suppression-without-explanation"], (
            "a bare pylint disable must be reported whatever its names"
        )
