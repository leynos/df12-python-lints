"""Shared helpers for classifying simple expressions.

Several checkers in this package need to know whether an expression is a
pure attribute chain — ``name``, ``name.attr``, ``name.attr.deeper`` — with
no calls or subscripts along the way.

Examples
--------
Find the base name of a chain::

    root = attribute_root(node)
"""

from __future__ import annotations

from astroid import nodes


def attribute_root(node: nodes.NodeNG) -> nodes.Name | None:
    """Return the base ``Name`` of a pure attribute chain, if any.

    Calls, subscripts, or any other operation along the chain disqualify
    it.

    Examples
    --------
    ``os.path.join`` returns the ``Name`` node for ``os``;
    ``get_config().value`` returns ``None``.
    """
    current = node
    while isinstance(current, nodes.Attribute):
        current = current.expr
    return current if isinstance(current, nodes.Name) else None
