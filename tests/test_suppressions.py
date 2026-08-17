"""Tests for the suppression explanation checkers."""

from __future__ import annotations

import io
import tokenize

import pytest
from pylint import testutils

from df12_python_lints.suppressions import (
    SuppressionCommentChecker,
    _Comment,
    _directive_symbols,
)


def _tokens(code: str) -> list[tokenize.TokenInfo]:
    """Tokenize *code* for the token-based checker."""
    return list(tokenize.generate_tokens(io.StringIO(code).readline))


def _lint_message(line: int) -> testutils.MessageTest:
    """Build the expected lint-suppression message at *line*."""
    return testutils.MessageTest("lint-suppression-without-explanation", line=line)


def _type_message(line: int) -> testutils.MessageTest:
    """Build the expected type-check-suppression message at *line*."""
    return testutils.MessageTest("typecheck-suppression-without-explanation", line=line)


class TestSuppressionCommentChecker(testutils.CheckerTestCase):
    """Exercise detection of unexplained suppression pragmas."""

    CHECKER_CLASS = SuppressionCommentChecker

    @pytest.mark.parametrize(
        ("code", "message"),
        [
            pytest.param("x = 1  # noqa: E501\n", _lint_message(1), id="bare-noqa"),
            pytest.param(
                "x = 1  # noqa: E501 F841,\n",
                _lint_message(1),
                id="space-separated-noqa-with-trailing-comma",
            ),
            pytest.param(
                "# flake8: noqa: F401\n",
                _lint_message(1),
                id="flake8-file-noqa",
            ),
            pytest.param(
                "x = 1  # ruff: ignore[E501]\n",
                _lint_message(1),
                id="inline-ruff-ignore",
            ),
            pytest.param(
                "x = 1  # ruff: ignore [E501]\n",
                _lint_message(1),
                id="spaced-inline-ruff-ignore",
            ),
            pytest.param(
                "#ruff: ignore[unused-variable,]\nx = 1\n",
                _lint_message(1),
                id="preceding-ruff-ignore-with-rule-name",
            ),
            pytest.param(
                "# ruff: file-ignore[F401, ARG001,]\n",
                _lint_message(1),
                id="ruff-file-ignore",
            ),
            pytest.param(
                "# ruff: file-ignore [F401, ARG001,]\n",
                _lint_message(1),
                id="spaced-ruff-file-ignore",
            ),
            pytest.param(
                "# ruff: disable[E741, F841,]\nx = 1\n",
                _lint_message(1),
                id="ruff-disable",
            ),
            pytest.param(
                "# ruff: disable [E741, F841,]\nx = 1\n",
                _lint_message(1),
                id="spaced-ruff-disable",
            ),
            pytest.param(
                "# pylint: disable=too-many-branches\nx = 1\n",
                _lint_message(1),
                id="bare-pylint-disable",
            ),
            pytest.param(
                "# PYLINT: DISABLE=too-many-branches\nx = 1\n",
                _lint_message(1),
                id="uppercase-pylint-disable",
            ),
            pytest.param(
                "y = obj.attr  # type: ignore[attr-defined]\n",
                _type_message(1),
                id="bare-type-ignore",
            ),
            pytest.param(
                "y = obj.attr  # pyright: ignore[reportAny]\n",
                _type_message(1),
                id="bare-pyright-ignore",
            ),
        ],
    )
    def test_flags_bare_pragma_without_explanation(
        self, code: str, message: testutils.MessageTest
    ) -> None:
        """A suppression pragma without a recorded reason is reported."""
        with self.assertAddsMessages(message, ignore_position=True):
            self.checker.process_tokens(_tokens(code))

    def test_accepts_second_hash_explanation(self) -> None:
        """Prose after a second hash explains the pragma."""
        code = "x = eval(s)  # ruff: ignore[S307]  # input is a vetted literal\n"
        with self.assertNoMessages():
            self.checker.process_tokens(_tokens(code))

    def test_accepts_trailing_prose_in_pragma_segment(self) -> None:
        """Prose in the same segment as the pragma explains it."""
        code = "# ruff: file-ignore[E501] generated URLs cannot be wrapped\n"
        with self.assertNoMessages():
            self.checker.process_tokens(_tokens(code))

    def test_accepts_preceding_comment_explanation(self) -> None:
        """A standalone comment on the previous line explains a pragma."""
        code = (
            "# The upstream stub omits this attribute.\n"
            "y = obj.attr  # type: ignore[attr-defined]\n"
        )
        with self.assertNoMessages():
            self.checker.process_tokens(_tokens(code))

    def test_rejects_preceding_pragma_as_explanation(self) -> None:
        """A pragma on the previous line does not count as a reason."""
        code = "# pylint: disable=too-many-branches\nx = 1  # noqa: E501\n"
        with self.assertAddsMessages(
            _lint_message(1), _lint_message(2), ignore_position=True
        ):
            self.checker.process_tokens(_tokens(code))

    def test_ignores_plain_comments(self) -> None:
        """Comments without pragmas are never reported."""
        code = "# This value is measured in seconds.\nx = 30\n"
        with self.assertNoMessages():
            self.checker.process_tokens(_tokens(code))

    @pytest.mark.parametrize(
        "code",
        [
            pytest.param(
                "x = 1  # RUFF: ignore[F841]\n",
                id="uppercase-ruff",
            ),
            pytest.param(
                "x = 1  # ruff: file-ignore[F841]\n",
                id="inline-file-ignore",
            ),
            pytest.param(
                "x = 1  # ruff: disable[F841]\n",
                id="inline-disable",
            ),
        ],
    )
    def test_ignores_invalid_ruff_directives(self, code: str) -> None:
        """Text that Ruff does not treat as a suppression is not reported."""
        with self.assertNoMessages():
            self.checker.process_tokens(_tokens(code))

    @pytest.mark.parametrize(
        ("comment_text", "is_standalone"),
        [
            pytest.param("# ruff: ignore [", True, id="missing-selector"),
            pytest.param("# ruff: ignore[]", True, id="empty-selector"),
            pytest.param("# ruff: ignore [F401", True, id="missing-bracket"),
            pytest.param("# ruff: ignore[F401,,E501]", True, id="bad-separator"),
            pytest.param("# ruff: IGNORE[F401]", True, id="uppercase-ignore"),
            pytest.param("# ruff: FILE-IGNORE[F401]", True, id="uppercase-file-ignore"),
            pytest.param("# ruff: DISABLE[F401]", True, id="uppercase-disable"),
            pytest.param("# ruff: file-ignore[F401]", False, id="inline-file-ignore"),
            pytest.param("# ruff: disable[F401]", False, id="inline-disable"),
        ],
    )
    def test_does_not_classify_invalid_ruff_directives(
        self, comment_text: str, *, is_standalone: bool
    ) -> None:
        """Malformed, case-invalid, and inline-only forms are not pragmas."""
        assert not _directive_symbols(_Comment(comment_text, is_standalone))

    def test_ignores_ruff_enable_directive(self) -> None:
        """A directive ending a suppression range needs no reason."""
        code = "# ruff: enable [E501]\n"
        with self.assertNoMessages():
            self.checker.process_tokens(_tokens(code))

    def test_ruff_enable_does_not_explain_next_suppression(self) -> None:
        """A range terminator is not prose explaining the next pragma."""
        code = "# ruff: enable [E501]\nx = 1  # ruff: ignore [F841]\n"
        with self.assertAddsMessages(_lint_message(2), ignore_position=True):
            self.checker.process_tokens(_tokens(code))

    def test_ruff_enable_with_prose_does_not_explain_next_suppression(self) -> None:
        """Text trailing a range terminator does not explain a later pragma."""
        code = (
            "# ruff: enable [E501] linting resumes here\nx = 1  # ruff: ignore [F841]\n"
        )
        with self.assertAddsMessages(_lint_message(2), ignore_position=True):
            self.checker.process_tokens(_tokens(code))

    def test_flags_both_kinds_in_one_comment(self) -> None:
        """A comment mixing lint and type pragmas reports both."""
        code = "y = obj.attr  # noqa: A001  # type: ignore[attr-defined]\n"
        with self.assertAddsMessages(
            _lint_message(1), _type_message(1), ignore_position=True
        ):
            self.checker.process_tokens(_tokens(code))
