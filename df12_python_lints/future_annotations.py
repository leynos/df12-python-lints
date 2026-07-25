"""Checker flagging ``from __future__ import annotations`` on 3.14+.

PEP 749 makes deferred evaluation of annotations the default behaviour
from Python 3.14, so the future import no longer buys anything — and it
is not a harmless no-op either: it forces the older stringified
semantics instead of 3.14's lazily evaluated annotation objects, which
runtime annotation consumers can observe.

The check is inert until the configured ``py-version`` reaches 3.14, so
projects that still support older interpreters keep the import without
noise.

Examples
--------
Flagged (with ``--py-version=3.14`` or a 3.14+ interpreter)::

    from __future__ import annotations

Preferred: no future import; 3.14 defers annotation evaluation natively.
"""

from __future__ import annotations

import typing as typ

from pylint import checkers

if typ.TYPE_CHECKING:
    from astroid import nodes
    from pylint.typing import MessageDefinitionTuple

_MSGS: typ.Final[dict[str, MessageDefinitionTuple]] = {
    "C9112": (
        "Remove 'from __future__ import annotations' on a 3.14+ baseline",
        "redundant-future-annotations",
        (
            "Emitted when a module imports 'annotations' from __future__ "
            "while the configured py-version is 3.14 or newer. Deferred "
            "evaluation is the default there, and the future import "
            "forces the older stringified semantics instead of lazily "
            "evaluated annotation objects."
        ),
    ),
}

_DEFERRED_BY_DEFAULT_VERSION: typ.Final = (3, 14)


class FutureAnnotationsChecker(checkers.BaseChecker):
    """Report ``from __future__ import annotations`` on modern baselines.

    Examples
    --------
    Enable alongside the plugin and run pylint as usual::

        pylint --load-plugins=df12_python_lints --py-version=3.14 my_module.py
    """

    name = "df12-future-annotations"
    msgs = _MSGS

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Check *node* for a redundant annotations future import.

        Examples
        --------
        Invoked by pylint's AST walker for every ``from`` import.
        """
        if tuple(self.linter.config.py_version) < _DEFERRED_BY_DEFAULT_VERSION:
            return
        if node.modname != "__future__":
            return
        if any(name == "annotations" for name, _alias in node.names):
            self.add_message("redundant-future-annotations", node=node)
