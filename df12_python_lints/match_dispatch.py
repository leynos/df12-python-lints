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

import collections
import typing as typ

from astroid import nodes
from pylint import checkers

from ._chains import elif_chain_tests, is_elif_branch

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from pylint.typing import MessageDefinitionTuple

_TERMINAL_STATEMENTS = (nodes.Return, nodes.Raise, nodes.Continue, nodes.Break)

_MIN_DISPATCH_BRANCHES = 2


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
        func = call.func
        if not (isinstance(func, nodes.Name) and func.name == "isinstance"):
            continue
        if call.args:
            subjects.add(call.args[0].as_string())
    return frozenset(subjects)


def _repeated_subject(tests: cabc.Iterable[nodes.NodeNG]) -> str | None:
    """Return the subject dispatched on across *tests*, if any.

    A subject counts as dispatched on when at least two tests contain an
    ``isinstance`` call with it as the first argument. Ties break towards
    the most frequent, then lexically smallest, subject for determinism.

    Examples
    --------
    Tests for ``isinstance(v, dict)`` and ``isinstance(v, list)`` return
    ``"v"``; unrelated tests return ``None``.
    """
    counts: collections.Counter[str] = collections.Counter()
    for test in tests:
        counts.update(_isinstance_subjects(test))
    candidates = [s for s, n in counts.items() if n >= _MIN_DISPATCH_BRANCHES]
    if not candidates:
        return None
    return min(candidates, key=lambda subject: (-counts[subject], subject))


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
    if not isinstance(stmt, nodes.If) or stmt.orelse:
        return frozenset()
    if not stmt.body or not isinstance(stmt.body[-1], _TERMINAL_STATEMENTS):
        return frozenset()
    return _isinstance_subjects(stmt.test)


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
        subject = _repeated_subject(elif_chain_tests(node))
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
        common = _guard_subjects(node)
        if not common:
            return
        if _guard_subjects(node.previous_sibling()) & common:
            return
        run_length = 1
        current: nodes.NodeNG = node
        while shared := _guard_subjects(current.next_sibling()) & common:
            common = shared
            run_length += 1
            current = current.next_sibling()
        if run_length >= _MIN_DISPATCH_BRANCHES:
            subject = min(common)
            self.add_message(
                "prefer-structural-pattern-matching", node=node, args=(subject,)
            )
