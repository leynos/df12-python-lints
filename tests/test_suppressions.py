"""Tests for the suppression explanation checkers."""

from __future__ import annotations

import io
import tokenize

import pytest
from pylint import testutils

from df12_python_lints.suppressions import SuppressionCommentChecker


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
                "# ruff: disable[E741, F841,]\nx = 1\n",
                _lint_message(1),
                id="ruff-disable",
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

    def test_ignores_ruff_enable_directive(self) -> None:
        """A directive ending a suppression range needs no reason."""
        code = "# ruff: enable[E501]\n"
        with self.assertNoMessages():
            self.checker.process_tokens(_tokens(code))

    def test_ruff_enable_does_not_explain_next_suppression(self) -> None:
        """A range terminator is not prose explaining the next pragma."""
        code = "# ruff: enable[E501]\nx = 1  # ruff: ignore[F841]\n"
        with self.assertAddsMessages(_lint_message(2), ignore_position=True):
            self.checker.process_tokens(_tokens(code))

    def test_flags_both_kinds_in_one_comment(self) -> None:
        """A comment mixing lint and type pragmas reports both."""
        code = "y = obj.attr  # noqa: A001  # type: ignore[attr-defined]\n"
        with self.assertAddsMessages(
            _lint_message(1), _type_message(1), ignore_position=True
        ):
            self.checker.process_tokens(_tokens(code))
