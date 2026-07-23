"""Shared helpers for walking ``if``/``elif`` chains.

The dispatch-oriented checkers in this package all reason about a head
``if`` statement and the tests along its ``elif`` chain. These helpers keep
that traversal logic in one place.

Examples
--------
Collect the branch tests of a chain rooted at ``node``::

    tests = elif_chain_tests(node)
"""

from __future__ import annotations

from astroid import nodes


def elif_chain_tests(node: nodes.If) -> list[nodes.NodeNG]:
    """Collect the test expressions of *node* and its ``elif`` chain.

    Examples
    --------
    For ``if a: ... elif b: ... else: ...`` the result holds the test
    nodes for ``a`` and ``b`` in source order.
    """
    tests = [node.test]
    current = node
    while len(current.orelse) == 1 and isinstance(current.orelse[0], nodes.If):
        current = current.orelse[0]
        tests.append(current.test)
    return tests


def is_elif_branch(node: nodes.If) -> bool:
    """Return whether *node* is the ``elif`` arm of an enclosing ``if``.

    Examples
    --------
    The ``elif`` in ``if a: ... elif b: ...`` reports ``True``; the head
    ``if`` reports ``False``.
    """
    parent = node.parent
    return isinstance(parent, nodes.If) and node in parent.orelse
