"""Tests for the constant-comparison chain checker."""

from __future__ import annotations

import typing as typ

import astroid
from pylint import testutils

from df12_python_lints.constant_chain import ConstantChainChecker


def _extract_if(code: str) -> astroid.nodes.If:
    """Extract the ``#@``-marked ``if`` statement from *code*."""
    return typ.cast("astroid.nodes.If", astroid.extract_node(code))


def _chain_message(node: astroid.nodes.NodeNG, subject: str) -> testutils.MessageTest:
    """Build the expected message for a constant-chain report on *node*."""
    return testutils.MessageTest(
        "prefer-match-over-constant-chain", node=node, args=(subject,)
    )


class TestConstantChainChecker(testutils.CheckerTestCase):
    """Exercise detection of constant-only comparison chains."""

    CHECKER_CLASS = ConstantChainChecker

    def test_flags_string_equality_chain(self) -> None:
        """A chain of string equality comparisons is reported."""
        node = _extract_if(
            """
            def dispatch(command):
                if command == "start":  #@
                    return 1
                elif command == "stop":
                    return 2
                return 0
            """
        )
        with self.assertAddsMessages(
            _chain_message(node, "command"), ignore_position=True
        ):
            self.checker.visit_if(node)

    def test_flags_enum_member_chain(self) -> None:
        """A chain comparing with enumeration members is reported."""
        node = _extract_if(
            """
            def react(colour):
                if colour == Colour.RED:  #@
                    return "stop"
                elif colour == Colour.GREEN:
                    return "go"
                return "wait"
            """
        )
        with self.assertAddsMessages(
            _chain_message(node, "colour"), ignore_position=True
        ):
            self.checker.visit_if(node)

    def test_flags_membership_in_literal_set(self) -> None:
        """Membership tests against literal sets count as constants."""
        node = _extract_if(
            """
            def classify(state):
                if state == "idle":  #@
                    return 1
                elif state in {"stopping", "stopped"}:
                    return 2
                return 0
            """
        )
        with self.assertAddsMessages(
            _chain_message(node, "state"), ignore_position=True
        ):
            self.checker.visit_if(node)

    def test_flags_or_combined_equalities(self) -> None:
        """An `or` of constant equalities on one subject is eligible."""
        node = _extract_if(
            """
            def classify(state):
                if state == "a" or state == "b":  #@
                    return 1
                elif state == "c":
                    return 2
                return 0
            """
        )
        with self.assertAddsMessages(
            _chain_message(node, "state"), ignore_position=True
        ):
            self.checker.visit_if(node)

    def test_flags_reversed_constant_equality(self) -> None:
        """A constant on the left-hand side still identifies the subject."""
        node = _extract_if(
            """
            def dispatch(command):
                if "start" == command:  #@
                    return 1
                elif command == "stop":
                    return 2
                return 0
            """
        )
        with self.assertAddsMessages(
            _chain_message(node, "command"), ignore_position=True
        ):
            self.checker.visit_if(node)

    def test_ignores_chain_with_variable_comparison(self) -> None:
        """A branch comparing two variables disqualifies the chain."""
        node = _extract_if(
            """
            def check(value, other):
                if value == "a":  #@
                    return 1
                elif value == other:
                    return 2
                return 0
            """
        )
        with self.assertNoMessages():
            self.checker.visit_if(node)

    def test_ignores_chain_on_different_subjects(self) -> None:
        """Branches comparing different subjects are not one dispatch."""
        node = _extract_if(
            """
            def check(left, right):
                if left == "a":  #@
                    return 1
                elif right == "b":
                    return 2
                return 0
            """
        )
        with self.assertNoMessages():
            self.checker.visit_if(node)

    def test_ignores_single_comparison(self) -> None:
        """A lone if/else with one comparison is not a chain."""
        node = _extract_if(
            """
            def check(value):
                if value == "a":  #@
                    return 1
                else:
                    return 0
            """
        )
        with self.assertNoMessages():
            self.checker.visit_if(node)

    def test_ignores_membership_in_variable_container(self) -> None:
        """Membership in a name-bound container is not a literal chain."""
        node = _extract_if(
            """
            def check(value, allowed):
                if value == "a":  #@
                    return 1
                elif value in allowed:
                    return 2
                return 0
            """
        )
        with self.assertNoMessages():
            self.checker.visit_if(node)

    def test_ignores_ordering_comparisons(self) -> None:
        """Ordering comparisons cannot become case patterns."""
        node = _extract_if(
            """
            def check(value):
                if value == 0:  #@
                    return 1
                elif value > 10:
                    return 2
                return 0
            """
        )
        with self.assertNoMessages():
            self.checker.visit_if(node)
