"""Checker flagging re-exports created by assignment.

Binding an imported name (or an attribute of an imported module) to a new
module-level name hides the import relationship from readers, type
checkers, and refactoring tools. A ``from``-import with an alias states
the same intent as a real import binding.

Examples
--------
Flagged::

    import os.path

    join = os.path.join

Preferred::

    from os.path import join
"""

from __future__ import annotations

import typing as typ

from astroid import nodes
from pylint import checkers

from ._expressions import attribute_root

if typ.TYPE_CHECKING:
    from pylint.typing import MessageDefinitionTuple

_MSGS: typ.Final[dict[str, MessageDefinitionTuple]] = {
    "C9105": (
        "Re-export %r with a from-import rather than assignment",
        "reexport-by-assignment",
        (
            "Emitted when a module-level name is bound by assigning an "
            "imported name or an attribute reached through an imported "
            "module. Use 'from module import name [as alias]' or "
            "'import module as alias' so importers and type checkers see "
            "a real import binding."
        ),
    ),
}


def _is_imported(name_node: nodes.Name) -> bool:
    """Return whether *name_node* resolves to an import statement.

    Examples
    --------
    With ``import os`` in scope, a ``Name`` node for ``os`` reports
    ``True``; a name bound by a local ``def`` reports ``False``.
    """
    try:
        _, assignments = name_node.lookup(name_node.name)
    except AttributeError:  # pragma: no cover - defensive against odd nodes
        return False
    return any(
        isinstance(assignment, nodes.Import | nodes.ImportFrom)
        for assignment in assignments
    )


class ReexportAssignmentChecker(checkers.BaseChecker):
    """Report module-level aliases of imported names made by assignment.

    Examples
    --------
    Enable alongside the plugin and run pylint as usual::

        pylint --load-plugins=df12_python_lints my_module.py
    """

    name = "df12-reexport-assignment"
    msgs = _MSGS

    def visit_assign(self, node: nodes.Assign) -> None:
        """Check *node* for a module-level alias of an imported name.

        Examples
        --------
        Invoked by pylint's AST walker for every assignment statement.
        """
        if not isinstance(node.scope(), nodes.Module):
            return
        match node.targets:
            case [nodes.AssignName(name=target_name)]:
                pass
            case _:
                return
        root = attribute_root(node.value)
        if root is None or not _is_imported(root):
            return
        self.add_message("reexport-by-assignment", node=node, args=(target_name,))
