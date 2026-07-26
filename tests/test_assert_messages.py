"""Tests for the assert failure-message checker."""

from __future__ import annotations

import typing as typ

import astroid
from pylint import testutils

from df12_python_lints.assert_messages import AssertMessageChecker


def _extract_assert(code: str) -> astroid.nodes.Assert:
    """Extract the ``#@``-marked ``assert`` statement from *code*."""
    return typ.cast("astroid.nodes.Assert", astroid.extract_node(code))


class TestAssertMessageChecker(testutils.CheckerTestCase):
    """Exercise detection of asserts lacking a failure message."""

    CHECKER_CLASS = AssertMessageChecker

    def test_flags_bare_assert(self) -> None:
        """An assert without a message is reported."""
        node = _extract_assert("assert is_pinned(ref, path)  #@")
        message = testutils.MessageTest("assert-missing-message", node=node)
        with self.assertAddsMessages(message, ignore_position=True):
            self.checker.visit_assert(node)

    def test_flags_bare_negated_assert(self) -> None:
        """A negated assert without a message is reported."""
        node = _extract_assert("assert not is_pinned(ref, other)  #@")
        message = testutils.MessageTest("assert-missing-message", node=node)
        with self.assertAddsMessages(message, ignore_position=True):
            self.checker.visit_assert(node)

    def test_ignores_assert_with_message(self) -> None:
        """An assert carrying a failure message passes."""
        node = _extract_assert(
            'assert is_pinned(ref, path), "exact path pin must match"  #@'
        )
        with self.assertNoMessages():
            self.checker.visit_assert(node)

    def test_ignores_assert_with_computed_message(self) -> None:
        """A non-literal failure message still counts as a message."""
        node = _extract_assert("assert same_shape(a, b), describe_mismatch(a, b)  #@")
        with self.assertNoMessages():
            self.checker.visit_assert(node)
