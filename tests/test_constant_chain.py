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

    def _assert_constant_chain_reported(self, code: str, subject: str) -> None:
        """Assert that the marked chain reports its dispatch subject."""
        node = _extract_if(code)
        with self.assertAddsMessages(
            _chain_message(node, subject), ignore_position=True
        ):
            self.checker.visit_if(node)

    def _assert_no_constant_chain_diagnostic(self, code: str) -> None:
        """Assert that the marked chain produces no constant-chain diagnostic."""
        node = _extract_if(code)
        with self.assertNoMessages():
            self.checker.visit_if(node)

    def test_flags_string_equality_chain(self) -> None:
        """A chain of string equality comparisons is reported."""
        self._assert_constant_chain_reported(
            """
            def dispatch(command):
                if command == "start":  #@
                    return 1
                elif command == "stop":
                    return 2
                return 0
            """,
            "command",
        )

    def test_flags_enum_member_chain(self) -> None:
        """A chain comparing with enumeration members is reported."""
        self._assert_constant_chain_reported(
            """
            def react(colour):
                if colour == Colour.RED:  #@
                    return "stop"
                elif colour == Colour.GREEN:
                    return "go"
                return "wait"
            """,
            "colour",
        )

    def test_flags_membership_in_literal_set(self) -> None:
        """Membership tests against literal sets count as constants."""
        self._assert_constant_chain_reported(
            """
            def classify(state):
                if state == "idle":  #@
                    return 1
                elif state in {"stopping", "stopped"}:
                    return 2
                return 0
            """,
            "state",
        )

    def test_flags_or_combined_equalities(self) -> None:
        """An `or` of constant equalities on one subject is eligible."""
        self._assert_constant_chain_reported(
            """
            def classify(state):
                if state == "a" or state == "b":  #@
                    return 1
                elif state == "c":
                    return 2
                return 0
            """,
            "state",
        )

    def test_flags_negative_number_constants(self) -> None:
        """Negative literals parse as unary operations but are constants.

        Regression pinned from a Hypothesis counterexample: chains such
        as ``value == -1`` were missed because ``-1`` is a ``UnaryOp``
        node rather than a ``Const``.
        """
        self._assert_constant_chain_reported(
            """
            def check(value):
                if value == 0:  #@
                    return 1
                elif value == -1:
                    return 2
                return 0
            """,
            "value",
        )

    def test_flags_reversed_constant_equality(self) -> None:
        """A constant on the left-hand side still identifies the subject."""
        self._assert_constant_chain_reported(
            """
            def dispatch(command):
                if "start" == command:  #@
                    return 1
                elif command == "stop":
                    return 2
                return 0
            """,
            "command",
        )

    def test_ignores_chain_with_variable_comparison(self) -> None:
        """A branch comparing two variables disqualifies the chain."""
        self._assert_no_constant_chain_diagnostic(
            """
            def check(value, other):
                if value == "a":  #@
                    return 1
                elif value == other:
                    return 2
                return 0
            """
        )

    def test_ignores_chain_on_different_subjects(self) -> None:
        """Branches comparing different subjects are not one dispatch."""
        self._assert_no_constant_chain_diagnostic(
            """
            def check(left, right):
                if left == "a":  #@
                    return 1
                elif right == "b":
                    return 2
                return 0
            """
        )

    def test_ignores_single_comparison(self) -> None:
        """A lone if/else with one comparison is not a chain."""
        self._assert_no_constant_chain_diagnostic(
            """
            def check(value):
                if value == "a":  #@
                    return 1
                else:
                    return 0
            """
        )

    def test_ignores_membership_in_variable_container(self) -> None:
        """Membership in a name-bound container is not a literal chain."""
        self._assert_no_constant_chain_diagnostic(
            """
            def check(value, allowed):
                if value == "a":  #@
                    return 1
                elif value in allowed:
                    return 2
                return 0
            """
        )

    def test_ignores_ordering_comparisons(self) -> None:
        """Ordering comparisons cannot become case patterns."""
        self._assert_no_constant_chain_diagnostic(
            """
            def check(value):
                if value == 0:  #@
                    return 1
                elif value > 10:
                    return 2
                return 0
            """
        )

    def test_flags_capitalized_class_attribute(self) -> None:
        """A lowercase member of a capitalized class counts as an enum."""
        self._assert_constant_chain_reported(
            """
            def react(mode):
                if mode == Mode.active:  #@
                    return 1
                elif mode == Mode.idle:
                    return 2
                return 0
            """,
            "mode",
        )

    def test_flags_uppercase_name_constant(self) -> None:
        """An upper-case module constant counts as constant-like."""
        self._assert_constant_chain_reported(
            """
            def check(value):
                if value == MAX_RETRIES:  #@
                    return 1
                elif value == 0:
                    return 2
                return 0
            """,
            "value",
        )

    def test_ignores_or_combination_across_subjects(self) -> None:
        """An `or` mixing two subjects is not a single-subject chain."""
        self._assert_no_constant_chain_diagnostic(
            """
            def check(left, right):
                if left == 1 or right == 2:  #@
                    return 1
                elif left == 3:
                    return 2
                return 0
            """
        )

    def test_ignores_non_comparison_branch(self) -> None:
        """A branch testing a bare name is not a constant comparison."""
        self._assert_no_constant_chain_diagnostic(
            """
            def check(value, flag):
                if value == 1:  #@
                    return 1
                elif flag:
                    return 2
                return 0
            """
        )
