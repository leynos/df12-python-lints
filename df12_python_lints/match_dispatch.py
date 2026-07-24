"""Checker flagging ``isinstance`` dispatch better served by ``match``.

The checker looks for two shapes of type dispatch on a single subject:

- an ``if``/``elif`` chain whose branch tests call ``isinstance`` on the
  same subject; and
- consecutive guard ``if`` statements (no ``else``, each body ending in a
  terminal statement) whose tests call ``isinstance`` on the same subject.

Both are clearer as a ``match`` statement with class patterns.

Examples
--------
Flagged::

    if isinstance(value, dict):
        handle_mapping(value)
    elif isinstance(value, list):
        handle_sequence(value)

Preferred::

    match value:
        case dict():
            handle_mapping(value)
        case list():
            handle_sequence(value)
"""

from __future__ import annotations

import typing as typ

from astroid import nodes
from pylint import checkers

from ._chains import (
    MIN_DISPATCH_BRANCHES,
    elif_chain_tests,
    is_elif_branch,
    narrowing_prefix,
    repeated_subject,
)

if typ.TYPE_CHECKING:
    from pylint.typing import MessageDefinitionTuple


def _isinstance_subjects(test: nodes.NodeNG) -> frozenset[str]:
    """Return rendered first arguments of ``isinstance`` calls in *test*.

    Walks the whole test expression so compound conditions such as
    ``isinstance(x, dict) and x`` still contribute their subject.

    Examples
    --------
    A test of ``isinstance(value, dict)`` yields ``frozenset({"value"})``.
    """
    subjects: set[str] = set()
    for call in test.nodes_of_class(nodes.Call):
        match call.func:
            case nodes.Name(name="isinstance") if call.args:
                subjects.add(call.args[0].as_string())
    return frozenset(subjects)


def _guard_subjects(stmt: nodes.NodeNG | None) -> frozenset[str]:
    """Return the ``isinstance`` subjects of *stmt* when it is a guard.

    A guard is an ``if`` without ``else`` whose body ends in a terminal
    statement (``return``, ``raise``, ``continue``, or ``break``), so
    consecutive guards behave as mutually exclusive dispatch branches.

    Examples
    --------
    ``if isinstance(x, dict): return 1`` yields ``frozenset({"x"})``; a
    guard without an ``isinstance`` test yields an empty set.
    """
    match stmt:
        case nodes.If(orelse=[], body=[*_, last]) as guard:
            match last:
                case nodes.Return() | nodes.Raise() | nodes.Continue() | nodes.Break():
                    return _isinstance_subjects(guard.test)
    return frozenset()


_MSGS: typ.Final[dict[str, MessageDefinitionTuple]] = {
    "R9101": (
        "Type dispatch on %r would be clearer as a match statement",
        "prefer-structural-pattern-matching",
        (
            "Emitted when consecutive branches select behaviour with "
            "isinstance() checks on one subject. A match statement with "
            "class patterns states the accepted shapes directly instead "
            "of decomposing them imperatively."
        ),
    ),
}


class MatchDispatchChecker(checkers.BaseChecker):
    """Report ``isinstance`` dispatch that should use ``match``/``case``.

    Attributes
    ----------
    name : str
        The checker identifier, ``df12-match-dispatch``.
    msgs : dict[str, MessageDefinitionTuple]
        The R9101 ``prefer-structural-pattern-matching`` message.

    Examples
    --------
    Enable alongside the plugin and run pylint as usual::

        pylint --load-plugins=df12_python_lints my_module.py
    """

    name = "df12-match-dispatch"
    msgs = _MSGS

    def visit_if(self, node: nodes.If) -> None:
        """Check *node* for dispatch chains rooted at it.

        Examples
        --------
        Invoked by pylint's AST walker for every ``if`` statement.
        """
        if is_elif_branch(node):
            return
        subject = repeated_subject(
            tuple(_isinstance_subjects(test) for test in elif_chain_tests(node))
        )
        if subject is not None:
            self.add_message(
                "prefer-structural-pattern-matching", node=node, args=(subject,)
            )
            return
        self._check_guard_run(node)

    def _check_guard_run(self, node: nodes.If) -> None:
        """Report a run of consecutive guard ``if`` statements at *node*.

        Only the first guard of a run reports, so a run of three guards
        yields a single message.

        Examples
        --------
        Two consecutive ``if isinstance(x, ...): return ...`` statements
        produce one message on the first of them.
        """
        if not _guard_subjects(node):
            return
        if _guard_subjects(node.previous_sibling()) & _guard_subjects(node):
            return
        subject_sets = [_guard_subjects(node)]
        current: nodes.NodeNG = node
        while subjects := _guard_subjects(current.next_sibling()):
            subject_sets.append(subjects)
            current = current.next_sibling()
        run_length, common = narrowing_prefix(tuple(subject_sets))
        if run_length >= MIN_DISPATCH_BRANCHES:
            self.add_message(
                "prefer-structural-pattern-matching",
                node=node,
                args=(min(common),),
            )
