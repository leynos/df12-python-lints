"""Tests for the snapshot assertion checker."""

from __future__ import annotations

import typing as typ

import astroid
from pylint import testutils

from df12_python_lints.snapshot_asserts import SnapshotAssertionChecker


def _extract_assert(code: str) -> astroid.nodes.Assert:
    """Extract the ``#@``-marked ``assert`` statement from *code*."""
    return typ.cast("astroid.nodes.Assert", astroid.extract_node(code))


def _extract_function(code: str) -> astroid.nodes.FunctionDef:
    """Extract the ``#@``-marked function definition from *code*."""
    return typ.cast("astroid.nodes.FunctionDef", astroid.extract_node(code))


_LARGE_DICT_TEST = """
def test_payload(result):
    assert result == {  #@
        "id": 1,
        "name": "alice",
        "roles": ["admin", "editor"],
        "active": True,
        "score": 12,
    }
"""

_SUBSTRING_TEST = """
def test_report(output):  #@
    assert "header" in output
    assert "row 1" in output
    assert "footer" in output
"""


class TestSnapshotAssertionChecker(testutils.CheckerTestCase):
    """Exercise detection of snapshot-worthy assertions."""

    CHECKER_CLASS = SnapshotAssertionChecker

    def test_flags_large_inline_dict(self) -> None:
        """Equality against a large dict literal is reported."""
        node = _extract_assert(_LARGE_DICT_TEST)
        message = testutils.MessageTest("prefer-snapshot-assertion", node=node)
        with self.assertAddsMessages(message, ignore_position=True):
            self.checker.visit_assert(node)

    def test_flags_multiline_string(self) -> None:
        """Equality against a multiline string is reported."""
        node = _extract_assert(
            """
def test_render(result):
    assert result == (  #@
        "line one\\n"
        "line two\\n"
        "line three\\n"
        "line four\\n"
    )
"""
        )
        message = testutils.MessageTest("prefer-snapshot-assertion", node=node)
        with self.assertAddsMessages(message, ignore_position=True):
            self.checker.visit_assert(node)

    def test_flags_dedented_string(self) -> None:
        """A textwrap.dedent-wrapped multiline string is reported."""
        node = _extract_assert(
            '''
import textwrap

def test_render(result):
    assert result == textwrap.dedent(  #@
        """
        one
        two
        three
        """
    )
'''
        )
        message = testutils.MessageTest("prefer-snapshot-assertion", node=node)
        with self.assertAddsMessages(message, ignore_position=True):
            self.checker.visit_assert(node)

    def test_ignores_small_literal(self) -> None:
        """A small inline literal is clearer inline than as a snapshot."""
        node = _extract_assert(
            """
def test_pair(result):
    assert result == {"a": 1, "b": 2}  #@
"""
        )
        with self.assertNoMessages():
            self.checker.visit_assert(node)

    def test_ignores_comparison_with_name(self) -> None:
        """Comparing with an expected fixture or parameter is fine."""
        node = _extract_assert(
            """
def test_match(result, expected):
    assert result == expected  #@
"""
        )
        with self.assertNoMessages():
            self.checker.visit_assert(node)

    def test_ignores_helpers_outside_tests(self) -> None:
        """Large literals outside test functions are not reported."""
        node = _extract_assert(
            """
def check_payload(result):
    assert result == {  #@
        "id": 1,
        "name": "alice",
        "roles": ["admin", "editor"],
        "active": True,
        "score": 12,
    }
"""
        )
        with self.assertNoMessages():
            self.checker.visit_assert(node)

    def test_flags_repeated_substring_probes(self) -> None:
        """Three substring asserts on one subject are reported once."""
        func = _extract_function(_SUBSTRING_TEST)
        first = func.body[0]
        message = testutils.MessageTest(
            "prefer-snapshot-substring", node=first, args=(3, "output")
        )
        with self.assertAddsMessages(message, ignore_position=True):
            self.checker.visit_functiondef(func)

    def test_ignores_few_substring_probes(self) -> None:
        """Two probes on one subject are below the threshold."""
        func = _extract_function(
            """
def test_report(output):  #@
    assert "header" in output
    assert "footer" in output
"""
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(func)

    def test_ignores_probes_on_different_subjects(self) -> None:
        """Probes spread across subjects are not one contract."""
        func = _extract_function(
            """
def test_report(out, err):  #@
    assert "header" in out
    assert "warning" in err
    assert "footer" in out
"""
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(func)

    def test_ignores_non_comparison_assert(self) -> None:
        """An assert without an equality comparison is not reported."""
        node = _extract_assert(
            """
def test_state(flag):
    assert flag, "flag must be set"  #@
"""
        )
        with self.assertNoMessages():
            self.checker.visit_assert(node)

    def test_ignores_probes_in_helper_function(self) -> None:
        """Substring probes in a non-test function are not reported."""
        func = _extract_function(
            """
def check_report(output):  #@
    assert "header" in output, "has header"
    assert "row" in output, "has row"
    assert "footer" in output, "has footer"
"""
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(func)

    def test_ignores_probes_in_nested_function(self) -> None:
        """Probes inside a nested helper belong to that helper's frame."""
        func = _extract_function(
            """
def test_outer(output):  #@
    def helper(inner):
        assert "a" in inner, "has a"
        assert "b" in inner, "has b"
        assert "c" in inner, "has c"

    helper(output)
"""
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(func)
