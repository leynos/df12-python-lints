"""Tests for the PEP 695 type-statement checker."""

from __future__ import annotations

import typing as typ

import astroid
from pylint import testutils
from pylint.testutils import set_config

from df12_python_lints.type_aliases import TypeAliasChecker


def _extract_assign(code: str) -> astroid.nodes.Assign:
    """Extract the ``#@``-marked assignment statement from *code*."""
    return typ.cast("astroid.nodes.Assign", astroid.extract_node(code))


def _extract_annassign(code: str) -> astroid.nodes.AnnAssign:
    """Extract the ``#@``-marked annotated assignment from *code*."""
    return typ.cast("astroid.nodes.AnnAssign", astroid.extract_node(code))


def _alias_message(node: astroid.nodes.NodeNG, target: str) -> testutils.MessageTest:
    """Build the expected message for a type-alias report on *node*."""
    return testutils.MessageTest("prefer-type-statement", node=node, args=(target,))


class TestTypeAliasChecker(testutils.CheckerTestCase):
    """Exercise detection of pre-PEP 695 type aliases."""

    CHECKER_CLASS = TypeAliasChecker

    @set_config(py_version=(3, 14))
    def test_flags_aliased_module_subscript(self) -> None:
        """A collections.abc subscript under a module alias is reported."""
        node = _extract_assign(
            """
            import collections.abc as cabc
            import datetime as dt

            Clock = cabc.Callable[[], dt.datetime]  #@
            """
        )
        with self.assertAddsMessages(
            _alias_message(node, "Clock"), ignore_position=True
        ):
            self.checker.visit_assign(node)

    @set_config(py_version=(3, 14))
    def test_flags_from_imported_subscript(self) -> None:
        """A from-imported typing construct subscript is reported."""
        node = _extract_assign(
            """
            from typing import Callable

            Handler = Callable[[str], None]  #@
            """
        )
        with self.assertAddsMessages(
            _alias_message(node, "Handler"), ignore_position=True
        ):
            self.checker.visit_assign(node)

    @set_config(py_version=(3, 14))
    def test_flags_dotted_import_subscript(self) -> None:
        """A subscript reached through a plain dotted import is reported."""
        node = _extract_assign(
            """
            import collections.abc

            Producer = collections.abc.Iterator[int]  #@
            """
        )
        with self.assertAddsMessages(
            _alias_message(node, "Producer"), ignore_position=True
        ):
            self.checker.visit_assign(node)

    @set_config(py_version=(3, 14))
    def test_flags_builtin_generic_subscript(self) -> None:
        """A subscripted builtin generic such as ``dict`` is reported."""
        node = _extract_assign("Registry = dict[str, int]  #@")
        with self.assertAddsMessages(
            _alias_message(node, "Registry"), ignore_position=True
        ):
            self.checker.visit_assign(node)

    @set_config(py_version=(3, 14))
    def test_flags_type_alias_annotation(self) -> None:
        """A ``TypeAlias``-annotated assignment is reported."""
        node = _extract_annassign(
            """
            from typing import TypeAlias

            Pair: TypeAlias = "tuple[int, int]"  #@
            """
        )
        with self.assertAddsMessages(
            _alias_message(node, "Pair"), ignore_position=True
        ):
            self.checker.visit_annassign(node)

    @set_config(py_version=(3, 14))
    def test_flags_dotted_type_alias_annotation(self) -> None:
        """A ``typ.TypeAlias`` annotation under an alias is reported."""
        node = _extract_annassign(
            """
            import typing as typ

            Pair: typ.TypeAlias = "tuple[int, int]"  #@
            """
        )
        with self.assertAddsMessages(
            _alias_message(node, "Pair"), ignore_position=True
        ):
            self.checker.visit_annassign(node)

    @set_config(py_version=(3, 11))
    def test_silent_below_baseline(self) -> None:
        """Nothing is reported when the baseline predates PEP 695."""
        node = _extract_assign(
            """
            import collections.abc as cabc

            Clock = cabc.Callable[[], float]  #@
            """
        )
        with self.assertNoMessages():
            self.checker.visit_assign(node)

    @set_config(py_version=(3, 14))
    def test_ignores_value_subscript(self) -> None:
        """Indexing a runtime value is not an alias."""
        node = _extract_assign(
            """
            matrix = [[1, 2], [3, 4]]

            row = matrix[0]  #@
            """
        )
        with self.assertNoMessages():
            self.checker.visit_assign(node)

    @set_config(py_version=(3, 14))
    def test_ignores_non_typing_module_subscript(self) -> None:
        """Subscripting an unrelated module's attribute is not an alias."""
        node = _extract_assign(
            """
            import numpy as np

            Array = np.ndarray[float]  #@
            """
        )
        with self.assertNoMessages():
            self.checker.visit_assign(node)

    @set_config(py_version=(3, 14))
    def test_ignores_shadowed_builtin(self) -> None:
        """A rebinding of ``dict`` disqualifies the builtin-generic path."""
        node = _extract_assign(
            """
            dict = {"a": object}

            Registry = dict["a"]  #@
            """
        )
        with self.assertNoMessages():
            self.checker.visit_assign(node)

    @set_config(py_version=(3, 14))
    def test_ignores_function_scope_subscript(self) -> None:
        """Bindings inside a function are locals, not module aliases."""
        node = _extract_assign(
            """
            from typing import Callable

            def build():
                handler = Callable[[str], None]  #@
                return handler
            """
        )
        with self.assertNoMessages():
            self.checker.visit_assign(node)

    @set_config(py_version=(3, 14))
    def test_ignores_plain_annotated_assignment(self) -> None:
        """An ordinary annotation such as ``Final`` is not an alias."""
        node = _extract_annassign(
            """
            import typing as typ

            LIMIT: typ.Final[int] = 10  #@
            """
        )
        with self.assertNoMessages():
            self.checker.visit_annassign(node)

    @set_config(py_version=(3, 14))
    def test_ignores_unannotated_union_value(self) -> None:
        """A bare PEP 604 union stays unreported; it may be a value."""
        node = _extract_assign(
            """
            A = {1}
            B = {2}

            merged = A | B  #@
            """
        )
        with self.assertNoMessages():
            self.checker.visit_assign(node)
