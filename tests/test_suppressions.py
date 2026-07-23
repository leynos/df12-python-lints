"""Tests for the suppression explanation checkers."""

from __future__ import annotations

import io
import tokenize

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

    def test_flags_bare_noqa(self) -> None:
        """A noqa pragma without a reason is reported."""
        code = "x = 1  # noqa: E501\n"
        with self.assertAddsMessages(_lint_message(1), ignore_position=True):
            self.checker.process_tokens(_tokens(code))

    def test_flags_bare_pylint_disable(self) -> None:
        """A pylint disable pragma without a reason is reported."""
        code = "# pylint: disable=too-many-branches\nx = 1\n"
        with self.assertAddsMessages(_lint_message(1), ignore_position=True):
            self.checker.process_tokens(_tokens(code))

    def test_flags_bare_type_ignore(self) -> None:
        """A type-ignore pragma without a reason is reported."""
        code = "y = obj.attr  # type: ignore[attr-defined]\n"
        with self.assertAddsMessages(_type_message(1), ignore_position=True):
            self.checker.process_tokens(_tokens(code))

    def test_flags_bare_pyright_ignore(self) -> None:
        """A pyright ignore pragma without a reason is reported."""
        code = "y = obj.attr  # pyright: ignore[reportAny]\n"
        with self.assertAddsMessages(_type_message(1), ignore_position=True):
            self.checker.process_tokens(_tokens(code))

    def test_accepts_second_hash_explanation(self) -> None:
        """Prose after a second hash explains the pragma."""
        code = "x = eval(s)  # noqa: S307  # input is a vetted literal\n"
        with self.assertNoMessages():
            self.checker.process_tokens(_tokens(code))

    def test_accepts_trailing_prose_in_pragma_segment(self) -> None:
        """Prose in the same segment as the pragma explains it."""
        code = "x = 1  # noqa: E501 the URL cannot be wrapped\n"
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

    def test_flags_both_kinds_in_one_comment(self) -> None:
        """A comment mixing lint and type pragmas reports both."""
        code = "y = obj.attr  # noqa: A001  # type: ignore[attr-defined]\n"
        with self.assertAddsMessages(
            _lint_message(1), _type_message(1), ignore_position=True
        ):
            self.checker.process_tokens(_tokens(code))
