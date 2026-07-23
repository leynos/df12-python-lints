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


def is_imported_name(name_node: nodes.Name) -> bool:
    """Return whether *name_node* is bound by an import statement.

    The name is resolved with astroid's scope-aware lookup, and the
    result is ``True`` when any surviving binding is an ``import`` or
    ``from`` import. No defensive exception handling guards the lookup:
    ``nodes.Name`` inherits ``LookupMixIn``, so the method is always
    present and cannot raise :class:`AttributeError` for a missing
    attribute.

    Scope and reuse
    ---------------
    Shared by the re-export and trivial-wrapper checkers to classify a
    name binding as an import. It is a binding classifier, not a general
    inference helper: it reports only whether a binding *is* an import,
    leaving what the import resolves to (for example, a function versus a
    class) to callers.

    Examples
    --------
    With ``import os`` in scope, a ``Name`` node for ``os`` reports
    ``True``; a name bound by a local ``def`` reports ``False``.
    """
    _, assignments = name_node.lookup(name_node.name)
    return any(
        isinstance(assignment, nodes.Import | nodes.ImportFrom)
        for assignment in assignments
    )
