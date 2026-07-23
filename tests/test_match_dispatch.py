"""Tests for the structural pattern matching dispatch checker."""

from __future__ import annotations

import typing as typ

import astroid
from pylint import testutils

from df12_python_lints.match_dispatch import MatchDispatchChecker


def _extract_if(code: str) -> astroid.nodes.If:
    """Extract the ``#@``-marked ``if`` statement from *code*."""
    return typ.cast("astroid.nodes.If", astroid.extract_node(code))


def _extract_function(code: str) -> astroid.nodes.FunctionDef:
    """Extract the ``#@``-marked function definition from *code*."""
    return typ.cast("astroid.nodes.FunctionDef", astroid.extract_node(code))


def _dispatch_message(
    node: astroid.nodes.NodeNG, subject: str
) -> testutils.MessageTest:
    """Build the expected message for a dispatch report on *node*."""
    return testutils.MessageTest(
        "prefer-structural-pattern-matching", node=node, args=(subject,)
    )


class TestMatchDispatchChecker(testutils.CheckerTestCase):
    """Exercise dispatch detection over elif chains and guard runs."""

    CHECKER_CLASS = MatchDispatchChecker

    def test_flags_isinstance_elif_chain(self) -> None:
        """An if/elif chain dispatching on one subject is reported."""
        node = _extract_if(
            """
            def walk(value):
                if isinstance(value, dict):  #@
                    return 1
                elif isinstance(value, list):
                    return 2
                return 3
            """
        )
        with self.assertAddsMessages(
            _dispatch_message(node, "value"), ignore_position=True
        ):
            self.checker.visit_if(node)

    def test_flags_compound_isinstance_tests(self) -> None:
        """Compound conditions still contribute their isinstance subject."""
        node = _extract_if(
            """
            def check(value):
                if isinstance(value, dict) and value:  #@
                    return 1
                elif isinstance(value, list) and len(value) > 1:
                    return 2
                return 3
            """
        )
        with self.assertAddsMessages(
            _dispatch_message(node, "value"), ignore_position=True
        ):
            self.checker.visit_if(node)

    def test_flags_consecutive_guard_ifs(self) -> None:
        """Sequential terminating guards on one subject are reported once."""
        func = _extract_function(
            """
            def same_shape(original, redacted):  #@
                if isinstance(original, dict):
                    return original.keys() == redacted.keys()
                if isinstance(original, list):
                    return len(original) == len(redacted)
                return type(original) is type(redacted)
            """
        )
        first_guard = func.body[0]
        with self.assertAddsMessages(
            _dispatch_message(first_guard, "original"), ignore_position=True
        ):
            self.walk(func)

    def test_ignores_single_isinstance_branch(self) -> None:
        """A lone isinstance test with an else block is not dispatch."""
        node = _extract_if(
            """
            def check(value):
                if isinstance(value, str):  #@
                    return value
                else:
                    return None
            """
        )
        with self.assertNoMessages():
            self.checker.visit_if(node)

    def test_ignores_guards_on_different_subjects(self) -> None:
        """Guards testing different subjects are unrelated, not dispatch."""
        func = _extract_function(
            """
            def check(left, right):  #@
                if isinstance(left, dict):
                    return 1
                if isinstance(right, list):
                    return 2
                return 3
            """
        )
        with self.assertNoMessages():
            self.walk(func)

    def test_ignores_non_terminating_guards(self) -> None:
        """Guards whose bodies fall through are not exclusive branches."""
        func = _extract_function(
            """
            def check(value):  #@
                if isinstance(value, dict):
                    value = dict(value)
                if isinstance(value, list):
                    value = list(value)
                return value
            """
        )
        with self.assertNoMessages():
            self.walk(func)

    def test_ignores_chain_without_repeated_subject(self) -> None:
        """An elif chain with one isinstance branch is not dispatch."""
        node = _extract_if(
            """
            def check(value, flag):
                if isinstance(value, dict):  #@
                    return 1
                elif flag:
                    return 2
                return 3
            """
        )
        with self.assertNoMessages():
            self.checker.visit_if(node)
