"""Tests for the PEP 695 type-statement checker."""

from __future__ import annotations

import typing as typ

import astroid
from pylint import testutils
from pylint.testutils import set_config

from df12_python_lints.type_aliases import (
    TypeAliasChecker,
    _assignment_import_origin,
    _from_import_binding_origin,
    _import_binding_origin,
)


def _extract_assign(code: str) -> astroid.nodes.Assign:
    """Extract the ``#@``-marked assignment statement from *code*."""
    return typ.cast("astroid.nodes.Assign", astroid.extract_node(code))


def _extract_statement(code: str) -> astroid.nodes.NodeNG:
    """Extract the ``#@``-marked statement from *code*."""
    return typ.cast("astroid.nodes.NodeNG", astroid.extract_node(code))


def _extract_import(code: str) -> astroid.nodes.Import:
    """Extract the ``#@``-marked ``import`` statement from *code*."""
    return typ.cast("astroid.nodes.Import", astroid.extract_node(code))


def _extract_import_from(code: str) -> astroid.nodes.ImportFrom:
    """Extract the ``#@``-marked ``from`` import statement from *code*."""
    return typ.cast("astroid.nodes.ImportFrom", astroid.extract_node(code))


def _extract_annassign(code: str) -> astroid.nodes.AnnAssign:
    """Extract the ``#@``-marked annotated assignment from *code*."""
    return typ.cast("astroid.nodes.AnnAssign", astroid.extract_node(code))


def _alias_message(node: astroid.nodes.NodeNG, target: str) -> testutils.MessageTest:
    """Build the expected message for a type-alias report on *node*."""
    return testutils.MessageTest("prefer-type-statement", node=node, args=(target,))


class TestTypeAliasChecker(testutils.CheckerTestCase):
    """Exercise detection of pre-PEP 695 type aliases."""

    CHECKER_CLASS = TypeAliasChecker

    def _assert_assign_alias_reported(self, code: str, target: str) -> None:
        """Assert that the marked assignment reports a type alias."""
        node = _extract_assign(code)
        with self.assertAddsMessages(
            _alias_message(node, target), ignore_position=True
        ):
            self.checker.visit_assign(node)

    def _assert_annassign_alias_reported(self, code: str, target: str) -> None:
        """Assert that the marked annotated assignment reports a type alias."""
        node = _extract_annassign(code)
        with self.assertAddsMessages(
            _alias_message(node, target), ignore_position=True
        ):
            self.checker.visit_annassign(node)

    def _assert_no_assign_alias_diagnostic(self, code: str) -> None:
        """Assert that the marked assignment produces no type-alias diagnostic."""
        node = _extract_assign(code)
        with self.assertNoMessages():
            self.checker.visit_assign(node)

    def _assert_no_annassign_alias_diagnostic(self, code: str) -> None:
        """Assert that the marked annotated assignment is not a type alias."""
        node = _extract_annassign(code)
        with self.assertNoMessages():
            self.checker.visit_annassign(node)

    @set_config(py_version=(3, 14))
    def test_flags_aliased_module_subscript(self) -> None:
        """A collections.abc subscript under a module alias is reported."""
        self._assert_assign_alias_reported(
            """
            import collections.abc as cabc
            import datetime as dt

            Clock = cabc.Callable[[], dt.datetime]  #@
            """,
            "Clock",
        )

    @set_config(py_version=(3, 14))
    def test_flags_from_imported_subscript(self) -> None:
        """A from-imported typing construct subscript is reported."""
        self._assert_assign_alias_reported(
            """
            from typing import Callable

            Handler = Callable[[str], None]  #@
            """,
            "Handler",
        )

    @set_config(py_version=(3, 14))
    def test_flags_dotted_import_subscript(self) -> None:
        """A subscript reached through a plain dotted import is reported."""
        self._assert_assign_alias_reported(
            """
            import collections.abc

            Producer = collections.abc.Iterator[int]  #@
            """,
            "Producer",
        )

    @set_config(py_version=(3, 14))
    def test_flags_builtin_generic_subscript(self) -> None:
        """A subscripted builtin generic such as ``dict`` is reported."""
        self._assert_assign_alias_reported(
            "Registry = dict[str, int]  #@",
            "Registry",
        )

    @set_config(py_version=(3, 14))
    def test_flags_type_alias_annotation(self) -> None:
        """A ``TypeAlias``-annotated assignment is reported."""
        self._assert_annassign_alias_reported(
            """
            from typing import TypeAlias

            Pair: TypeAlias = "tuple[int, int]"  #@
            """,
            "Pair",
        )

    @set_config(py_version=(3, 14))
    def test_flags_dotted_type_alias_annotation(self) -> None:
        """A ``typ.TypeAlias`` annotation under an alias is reported."""
        self._assert_annassign_alias_reported(
            """
            import typing as typ

            Pair: typ.TypeAlias = "tuple[int, int]"  #@
            """,
            "Pair",
        )

    @set_config(py_version=(3, 11))
    def test_silent_below_baseline(self) -> None:
        """Nothing is reported when the baseline predates PEP 695."""
        self._assert_no_assign_alias_diagnostic(
            """
            import collections.abc as cabc

            Clock = cabc.Callable[[], float]  #@
            """
        )

    @set_config(py_version=(3, 14))
    def test_ignores_value_subscript(self) -> None:
        """Indexing a runtime value is not an alias."""
        self._assert_no_assign_alias_diagnostic(
            """
            matrix = [[1, 2], [3, 4]]

            row = matrix[0]  #@
            """
        )

    @set_config(py_version=(3, 14))
    def test_ignores_non_typing_module_subscript(self) -> None:
        """Subscripting an unrelated module's attribute is not an alias."""
        self._assert_no_assign_alias_diagnostic(
            """
            import numpy as np

            Array = np.ndarray[float]  #@
            """
        )

    @set_config(py_version=(3, 14))
    def test_ignores_shadowed_builtin(self) -> None:
        """A rebinding of ``dict`` disqualifies the builtin-generic path."""
        self._assert_no_assign_alias_diagnostic(
            """
            dict = {"a": object}

            Registry = dict["a"]  #@
            """
        )

    @set_config(py_version=(3, 14))
    def test_ignores_function_scope_subscript(self) -> None:
        """Bindings inside a function are locals, not module aliases."""
        self._assert_no_assign_alias_diagnostic(
            """
            from typing import Callable

            def build():
                handler = Callable[[str], None]  #@
                return handler
            """
        )

    @set_config(py_version=(3, 14))
    def test_ignores_plain_annotated_assignment(self) -> None:
        """An ordinary annotation such as ``Final`` is not an alias."""
        self._assert_no_annassign_alias_diagnostic(
            """
            import typing as typ

            LIMIT: typ.Final[int] = 10  #@
            """
        )

    @set_config(py_version=(3, 14))
    def test_ignores_unannotated_union_value(self) -> None:
        """A bare PEP 604 union stays unreported; it may be a value."""
        self._assert_no_assign_alias_diagnostic(
            """
            A = {1}
            B = {2}

            merged = A | B  #@
            """
        )

    @set_config(py_version=(3, 11))
    def test_annassign_silent_below_baseline(self) -> None:
        """No annotated alias is reported when the baseline predates PEP 695."""
        self._assert_no_annassign_alias_diagnostic(
            """
            from typing import TypeAlias

            Pair: TypeAlias = "tuple[int, int]"  #@
            """
        )

    @set_config(py_version=(3, 14))
    def test_ignores_bare_annotation_without_value(self) -> None:
        """An annotation with no assigned value is not a type alias."""
        self._assert_no_annassign_alias_diagnostic("Pair: TypeAlias  #@")

    @set_config(py_version=(3, 14))
    def test_ignores_unimported_alias_annotation(self) -> None:
        """A ``TypeAlias`` annotation from no import resolves to nothing."""
        self._assert_no_annassign_alias_diagnostic(
            'Pair: TypeAlias = "tuple[int, int]"  #@'
        )

    @set_config(py_version=(3, 14))
    def test_ignores_subscript_of_call_result(self) -> None:
        """Subscripting a call result is not a typing construct."""
        self._assert_no_assign_alias_diagnostic(
            """
            def make():
                return list

            Registry = make()[str]  #@
            """
        )


class TestAssignmentImportOrigin:
    """Exercise the extracted per-assignment import classifier directly."""

    def test_aliased_dotted_import(self) -> None:
        """An aliased dotted import resolves to its full dotted path."""
        node = _extract_statement("import collections.abc as cabc  #@")
        assert _assignment_import_origin(node, "cabc") == "collections.abc"

    def test_unaliased_dotted_import_binds_top_level(self) -> None:
        """An unaliased dotted import binds and resolves its top-level name."""
        node = _extract_statement("import collections.abc  #@")
        assert _assignment_import_origin(node, "collections") == "collections"

    def test_from_import_with_alias(self) -> None:
        """A from-import alias resolves to the original dotted origin."""
        node = _extract_statement("from typing import Callable as C  #@")
        assert _assignment_import_origin(node, "C") == "typing.Callable"

    def test_from_import_without_alias(self) -> None:
        """A from-import resolves to the module-qualified original name."""
        node = _extract_statement("from typing import Callable  #@")
        assert _assignment_import_origin(node, "Callable") == "typing.Callable"

    def test_non_matching_bound_name_is_none(self) -> None:
        """An import that does not bind the name yields None."""
        node = _extract_statement("import os  #@")
        assert _assignment_import_origin(node, "sys") is None

    def test_non_import_assignment_is_none(self) -> None:
        """A binding that is not an import yields None."""
        node = _extract_statement("x = 1  #@")
        assert _assignment_import_origin(node, "x") is None


class TestImportBindingOrigin:
    """Exercise the ``import`` binding decoder directly."""

    def test_aliased_import_resolves_full_path(self) -> None:
        """An aliased import resolves to the full module path."""
        node = _extract_import("import collections.abc as cabc  #@")
        assert _import_binding_origin(node.names, "cabc") == "collections.abc"

    def test_unaliased_dotted_import_binds_top_level(self) -> None:
        """An unaliased dotted import binds and resolves its top-level name."""
        node = _extract_import("import collections.abc  #@")
        assert _import_binding_origin(node.names, "collections") == "collections"

    def test_non_matching_name_is_none(self) -> None:
        """A name matching no import entry yields None."""
        node = _extract_import("import os  #@")
        assert _import_binding_origin(node.names, "sys") is None


class TestFromImportBindingOrigin:
    """Exercise the ``from`` import binding decoder directly."""

    def test_aliased_from_import_resolves_original(self) -> None:
        """A from-import alias resolves to its module-qualified original."""
        node = _extract_import_from("from typing import Callable as C  #@")
        origin = _from_import_binding_origin(node.modname, node.names, "C")
        assert origin == "typing.Callable"

    def test_unaliased_from_import_resolves_original(self) -> None:
        """An unaliased from-import resolves to the same qualified name."""
        node = _extract_import_from("from typing import Callable  #@")
        origin = _from_import_binding_origin(node.modname, node.names, "Callable")
        assert origin == "typing.Callable"

    def test_non_matching_name_is_none(self) -> None:
        """A name matching no from-import entry yields None."""
        node = _extract_import_from("from typing import Callable  #@")
        assert _from_import_binding_origin(node.modname, node.names, "Mapping") is None
