"""Checker requiring a failure message on every ``assert`` statement.

A bare ``assert`` that fails reports only the falsy expression. Attaching a
message makes the violated expectation explicit, which matters most when a
property-based test shrinks to a minimal counterexample and the reader must
work out which invariant broke.

Examples
--------
Flagged::

    assert _is_pinned_action(ref, path)

Preferred::

    assert _is_pinned_action(ref, path), "exact path pin must match"
"""

from __future__ import annotations

import typing as typ

from pylint import checkers

if typ.TYPE_CHECKING:
    from astroid import nodes
    from pylint.typing import MessageDefinitionTuple


_MSGS: typ.Final[dict[str, MessageDefinitionTuple]] = {
    "C9102": (
        "Assert statement lacks a failure message",
        "assert-missing-message",
        (
            "Emitted when an assert statement has no second operand. Use "
            'assert expression, "message" so a failure names the violated '
            "expectation instead of echoing the expression alone."
        ),
    ),
}


class AssertMessageChecker(checkers.BaseChecker):
    """Report ``assert`` statements that lack a failure message.

    Examples
    --------
    Enable alongside the plugin and run pylint as usual::

        pylint --load-plugins=df12_python_lints tests/
    """

    name = "df12-assert-message"
    msgs = _MSGS

    def visit_assert(self, node: nodes.Assert) -> None:
        """Report *node* when it carries no failure message.

        Examples
        --------
        Invoked by pylint's AST walker for every ``assert`` statement.
        """
        if node.fail is None:
            self.add_message("assert-missing-message", node=node)
