"""Tests for the re-export by assignment checker."""

from __future__ import annotations

import typing as typ

import astroid
from pylint import testutils

from df12_python_lints.reexports import ReexportAssignmentChecker


def _extract_assign(code: str) -> astroid.nodes.Assign:
    """Extract the ``#@``-marked assignment statement from *code*."""
    return typ.cast("astroid.nodes.Assign", astroid.extract_node(code))


def _reexport_message(node: astroid.nodes.Assign, target: str) -> testutils.MessageTest:
    """Build the expected message for a re-export report on *node*."""
    return testutils.MessageTest("reexport-by-assignment", node=node, args=(target,))


class TestReexportAssignmentChecker(testutils.CheckerTestCase):
    """Exercise detection of import aliases created by assignment."""

    CHECKER_CLASS = ReexportAssignmentChecker

    def test_flags_module_attribute_alias(self) -> None:
        """Aliasing an attribute of an imported module is reported."""
        node = _extract_assign(
            """
            import os.path

            join = os.path.join  #@
            """
        )
        with self.assertAddsMessages(
            _reexport_message(node, "join"), ignore_position=True
        ):
            self.checker.visit_assign(node)

    def test_flags_imported_name_alias(self) -> None:
        """Aliasing a from-imported name is reported."""
        node = _extract_assign(
            """
            from json import dumps

            serialize = dumps  #@
            """
        )
        with self.assertAddsMessages(
            _reexport_message(node, "serialize"), ignore_position=True
        ):
            self.checker.visit_assign(node)

    def test_ignores_call_result(self) -> None:
        """Binding a call result is configuration, not re-export."""
        node = _extract_assign(
            """
            import logging

            logger = logging.getLogger(__name__)  #@
            """
        )
        with self.assertNoMessages():
            self.checker.visit_assign(node)

    def test_ignores_alias_of_local_definition(self) -> None:
        """Aliasing a name defined in the module is not a re-export."""
        node = _extract_assign(
            """
            def process(value):
                return value

            handler = process  #@
            """
        )
        with self.assertNoMessages():
            self.checker.visit_assign(node)

    def test_ignores_assignment_inside_function(self) -> None:
        """Only module-level assignments are re-exports."""
        node = _extract_assign(
            """
            import os.path

            def resolve():
                join = os.path.join  #@
                return join
            """
        )
        with self.assertNoMessages():
            self.checker.visit_assign(node)

    def test_ignores_multiple_targets(self) -> None:
        """Chained assignment is not a simple re-export."""
        node = _extract_assign(
            """
            from json import dumps

            first = second = dumps  #@
            """
        )
        with self.assertNoMessages():
            self.checker.visit_assign(node)
