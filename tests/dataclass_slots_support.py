"""Shared test harness for dataclass-slots checker cases."""

from __future__ import annotations

import textwrap

import astroid
from astroid import nodes
from pylint import testutils

from df12_python_lints.dataclass_slots import DataclassSlotsChecker


def parse_module(code: str) -> nodes.Module:
    """Parse dedented *code* as one synthetic module."""
    return astroid.parse(textwrap.dedent(code))


def module_classes(module: nodes.Module) -> tuple[nodes.ClassDef, ...]:
    """Return all classes in source order, including nested classes."""
    return tuple(module.nodes_of_class(nodes.ClassDef))


def _message(node: nodes.ClassDef) -> testutils.MessageTest:
    """Build the expected decorator-attached diagnostic for *node*."""
    decorator = next(
        (
            candidate
            for candidate in (node.decorators.nodes if node.decorators else ())
            if _looks_like_dataclass(candidate)
        ),
        None,
    )
    if decorator is None:
        message = f"expected a dataclass decorator on {node.name}"
        raise AssertionError(message)
    return testutils.MessageTest(
        "prefer-slots-for-dataclass",
        line=decorator.fromlineno,
        node=decorator,
        args=(node.name,),
        col_offset=decorator.col_offset,
        end_line=decorator.end_lineno,
        end_col_offset=decorator.end_col_offset,
    )


def _looks_like_dataclass(decorator: nodes.NodeNG) -> bool:
    """Recognize test-fixture dataclass spelling independently of production."""
    target = decorator.func if isinstance(decorator, nodes.Call) else decorator
    if isinstance(target, nodes.Attribute):
        return target.attrname == "dataclass"
    return isinstance(target, nodes.Name) and target.name in {"dataclass", "record"}


class DataclassSlotsTestCase(testutils.CheckerTestCase):
    """Provide whole-module assertions for dataclass-slots cases."""

    CHECKER_CLASS = DataclassSlotsChecker

    def assert_reports(self, code: str, *names: str) -> None:
        """Assert that exactly the named dataclasses report."""
        module = parse_module(code)
        classes = module_classes(module)
        classes_by_name = {class_node.name: class_node for class_node in classes}
        unresolved = set(names) - classes_by_name.keys()
        if unresolved:
            message = f"requested classes were not parsed: {sorted(unresolved)}"
            raise AssertionError(message)
        expected = tuple(_message(classes_by_name[name]) for name in names)
        with self.assertAddsMessages(*expected):
            self.checker.visit_module(module)
            for class_node in classes:
                self.checker.visit_classdef(class_node)

    def assert_silent(self, code: str) -> None:
        """Assert that no class in *code* reports."""
        module = parse_module(code)
        with self.assertNoMessages():
            self.checker.visit_module(module)
            for class_node in module_classes(module):
                self.checker.visit_classdef(class_node)
