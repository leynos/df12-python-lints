"""Require explicit slot layouts for closed standard-library dataclasses.

The plugin reports R9111 when a real :func:`dataclasses.dataclass` appears to
describe closed instance state but omits both ``slots=True`` and a manual
``__slots__`` layout.  Conservative analysis suppresses advice when generated
slots could be unsafe or ineffective.  Load the package plugin with Pylint::

    pylint --load-plugins=df12_python_lints my_package

Loading :mod:`df12_python_lints` registers this checker alongside the package's
other df12 house-policy checks.
"""

from __future__ import annotations

import typing as typ

from pylint import checkers

from ._dataclass_analysis import LayoutAnalyzer
from ._dataclass_decorators import find_dataclass_decorator

if typ.TYPE_CHECKING:
    from astroid import nodes
    from pylint.lint import PyLinter
    from pylint.typing import MessageDefinitionTuple

    override = typ.override
else:  # The project's pylint gate runs the plugin under PyPy 3.11.
    override = getattr(typ, "override", lambda method: method)

_MSGS: typ.Final[dict[str, MessageDefinitionTuple]] = {
    "R9111": (
        "Dataclass %r should declare slots=True",
        "prefer-slots-for-dataclass",
        (
            "Emitted when a standard-library dataclass appears to define closed "
            "instance state but neither requests generated slots nor declares an "
            "explicit __slots__ layout. Use dataclass(slots=True), adding "
            "weakref_slot=True when weak references are required. Intentional "
            "open-state or compatibility exceptions require an explained local "
            "suppression."
        ),
    ),
}


class DataclassSlotsChecker(checkers.BaseChecker):
    """Report closed standard-library dataclasses without slots.

    Attributes
    ----------
    name : str
        The checker identifier, ``df12-dataclass-slots``.
    msgs : dict[str, MessageDefinitionTuple]
        The R9111 ``prefer-slots-for-dataclass`` message.

    Examples
    --------
    Enable alongside the plugin and run Pylint as usual::

        pylint --load-plugins=df12_python_lints my_module.py
    """

    name = "df12-dataclass-slots"
    msgs = _MSGS

    @override
    # pylint: disable-next=useless-return  # Keep the terminal return explicit.
    def __init__(self, linter: PyLinter) -> None:
        """Initialize without retaining analysis across modules."""
        super().__init__(linter)
        self._analyzer: LayoutAnalyzer | None = None
        return  # ruff:ignore[useless-return]  # Keep the terminal return explicit.

    # pylint: disable-next=useless-return  # Keep the terminal return explicit.
    def visit_module(self, node: nodes.Module) -> None:
        """Prepare cached reverse-inheritance analysis for *node*."""
        self._analyzer = LayoutAnalyzer(node)
        return  # ruff:ignore[useless-return]  # Keep the terminal return explicit.

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Check *node* when it is a real standard-library dataclass."""
        decorator = find_dataclass_decorator(node)
        if decorator is None:
            return
        if self._analyzer is None or self._analyzer.module is not node.root():
            self._analyzer = LayoutAnalyzer(node.root())
        if self._analyzer.is_eligible(node):
            self.add_message(
                "prefer-slots-for-dataclass",
                node=decorator,
                args=(node.name,),
            )
        return
