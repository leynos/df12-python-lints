"""Shared test harness for dataclass-slots checker cases."""

from __future__ import annotations

import textwrap

import astroid
from astroid import nodes
from pylint import testutils

from df12_python_lints._dataclass_decorators import find_dataclass_decorator
from df12_python_lints.dataclass_slots import DataclassSlotsChecker


def parse_module(code: str) -> nodes.Module:
    """Parse dedented *code* as one synthetic module."""
    return astroid.parse(textwrap.dedent(code))


def module_classes(module: nodes.Module) -> tuple[nodes.ClassDef, ...]:
    """Return all classes in source order, including nested classes."""
    return tuple(module.nodes_of_class(nodes.ClassDef))


def _message(node: nodes.ClassDef) -> testutils.MessageTest:
    """Build the expected decorator-attached diagnostic for *node*."""
    decorator = find_dataclass_decorator(node)
    if decorator is None:
        raise AssertionError
    return testutils.MessageTest(
        "prefer-slots-for-dataclass",
        node=decorator,
        args=(node.name,),
    )


class DataclassSlotsTestCase(testutils.CheckerTestCase):
    """Provide whole-module assertions for dataclass-slots cases."""

    CHECKER_CLASS = DataclassSlotsChecker

    def assert_reports(self, code: str, *names: str) -> None:
        """Assert that exactly the named dataclasses report."""
        module = parse_module(code)
        classes = module_classes(module)
        expected = tuple(
            _message(class_node) for class_node in classes if class_node.name in names
        )
        with self.assertAddsMessages(*expected, ignore_position=True):
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
