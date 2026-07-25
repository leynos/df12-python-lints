"""Checker flagging assertions better expressed as syrupy snapshots.

Two shapes of test assertion indicate that a snapshot would carry the
contract more clearly:

- equality against a large inline literal — a big dict, list, set, or
  tuple, or a multiline or very long string (including one wrapped in
  ``textwrap.dedent``); and
- repeated substring probes — several ``assert "..." in output``
  statements against the same subject in one test.

Both are clearer as ``assert value == snapshot`` with syrupy, which
stores the expected output beside the test and updates it under review
with ``pytest --snapshot-update``.

Examples
--------
Flagged::

    def test_report(report):
        assert report.lines() == ["header", "row 1", "row 2", "row 3",
                                  "row 4", "row 5", "row 6", "footer"]

Preferred::

    def test_report(report, snapshot):
        assert report.lines() == snapshot
"""

from __future__ import annotations

import typing as typ

from astroid import nodes
from pylint import checkers

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from pylint.typing import MessageDefinitionTuple

_MIN_LITERAL_LEAVES = 8
_MIN_STRING_NEWLINES = 3
_MIN_STRING_LENGTH = 200
_MIN_SUBSTRING_PROBES = 3

_MSGS: typ.Final[dict[str, MessageDefinitionTuple]] = {
    "R9108": (
        "Assertion against a large inline literal; consider a syrupy snapshot",
        "prefer-snapshot-assertion",
        (
            "Emitted when a test asserts equality against a large inline "
            "collection or a multiline string. A syrupy snapshot "
            "(assert value == snapshot) stores the expected output "
            "beside the test and updates under review with "
            "pytest --snapshot-update."
        ),
    ),
    "R9109": (
        "%d substring assertions probe %r; consider a syrupy snapshot",
        "prefer-snapshot-substring",
        (
            "Emitted when one test repeatedly asserts that string "
            "fragments occur in the same subject. A syrupy snapshot of "
            "the whole output captures the contract in one reviewable "
            "assertion."
        ),
    ),
}


def _leaf_count(literal: nodes.NodeNG) -> int:
    """Count the constant and name leaves inside *literal*.

    Counting AST leaves rather than source characters keeps the measure
    independent of formatting.

    Examples
    --------
    ``{"a": 1, "b": [2, 3]}`` has five leaves.
    """
    return sum(1 for _ in literal.nodes_of_class((nodes.Const, nodes.Name)))


def _is_large_string(value: object) -> bool:
    """Return whether *value* is a multiline or very long string.

    Examples
    --------
    A four-line expected report qualifies; ``"short"`` does not.
    """
    if not isinstance(value, str):
        return False
    return value.count("\n") >= _MIN_STRING_NEWLINES or len(value) >= _MIN_STRING_LENGTH


def _is_snapshot_worthy(operand: nodes.NodeNG) -> bool:
    """Return whether *operand* is a literal that suits a snapshot.

    Examples
    --------
    A dict literal with ten entries qualifies; a plain name such as an
    ``expected`` fixture never does.
    """
    match operand:
        case nodes.Dict() | nodes.List() | nodes.Set() | nodes.Tuple():
            return _leaf_count(operand) >= _MIN_LITERAL_LEAVES
        case nodes.Const(value=value):
            return _is_large_string(value)
        case nodes.Call(
            func=nodes.Attribute(attrname="dedent") | nodes.Name(name="dedent"),
            args=[argument],
        ):
            return _is_snapshot_worthy(argument)
        case _:
            return False


def _in_test_function(node: nodes.NodeNG) -> bool:
    """Return whether *node* sits inside a ``test_``-named function.

    Examples
    --------
    An assert in ``test_render`` qualifies; one in a helper does not.
    """
    frame = node.frame()
    return isinstance(frame, nodes.FunctionDef) and frame.name.startswith("test_")


def _substring_probe_target(statement: nodes.Assert) -> str | None:
    """Return the probed subject when *statement* is a substring assert.

    Examples
    --------
    ``assert "header" in output`` returns ``"output"``; other assert
    shapes return ``None``.
    """
    match statement.test:
        case nodes.Compare(
            left=nodes.Const(value=str()),
            ops=[("in", nodes.Name() | nodes.Attribute() as target)],
        ):
            return target.as_string()
        case _:
            return None


def _direct_substring_probes(
    function: nodes.FunctionDef,
) -> cabc.Iterator[tuple[str, nodes.Assert]]:
    """Yield ``(target, statement)`` for each direct substring probe.

    A probe is an ``assert "fragment" in subject`` statement whose frame
    is *function* itself, so probes belonging to a nested helper are
    excluded. The target is the probed subject's source text.

    Examples
    --------
    A ``test_`` body with ``assert "header" in output`` yields
    ``("output", <Assert>)``; a probe inside a nested ``def`` is skipped.
    """
    for statement in function.nodes_of_class(nodes.Assert):
        if statement.frame() is not function:
            continue
        target = _substring_probe_target(statement)
        if target is None:
            continue
        yield target, statement


class SnapshotAssertionChecker(checkers.BaseChecker):
    """Report assertions in tests that should be syrupy snapshots.

    Examples
    --------
    Enable alongside the plugin and run pylint as usual::

        pylint --load-plugins=df12_python_lints tests/
    """

    name = "df12-snapshot-asserts"
    msgs = _MSGS

    def visit_assert(self, node: nodes.Assert) -> None:
        """Check *node* for equality against a snapshot-worthy literal.

        Examples
        --------
        Invoked by pylint's AST walker for every ``assert`` statement.
        """
        if not _in_test_function(node):
            return
        match node.test:
            case nodes.Compare(left=left, ops=[("==", right)]):
                operands = (left, right)
            case _:
                return
        if any(_is_snapshot_worthy(operand) for operand in operands):
            self.add_message("prefer-snapshot-assertion", node=node)

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check *node* for repeated substring probes on one subject.

        Examples
        --------
        Invoked by pylint's AST walker for every function definition.
        """
        if not node.name.startswith("test_"):
            return
        first_probe: dict[str, nodes.Assert] = {}
        counts: dict[str, int] = {}
        for target, statement in _direct_substring_probes(node):
            first_probe.setdefault(target, statement)
            counts[target] = counts.get(target, 0) + 1
        for target, count in counts.items():
            if count >= _MIN_SUBSTRING_PROBES:
                self.add_message(
                    "prefer-snapshot-substring",
                    node=first_probe[target],
                    args=(count, target),
                )

    visit_asyncfunctiondef = visit_functiondef
