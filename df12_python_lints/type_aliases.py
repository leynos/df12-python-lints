"""Checker flagging type aliases that predate the ``type`` statement.

On a Python 3.12+ baseline, PEP 695 gives type aliases their own
statement. Aliases created by plain assignment (``Clock =
cabc.Callable[[], dt.datetime]``) or by a ``TypeAlias`` annotation are
indistinguishable from ordinary values to readers and eagerly evaluated
at import time; the ``type`` statement declares the intent explicitly
and defers evaluation of the aliased expression.

Detection is deliberately conservative: only module-level bindings are
considered, and a plain assignment counts as an alias only when its
value subscripts a construct from ``typing``, ``typing_extensions``, or
``collections.abc`` (resolved through the module's import bindings), or
an unshadowed builtin generic such as ``dict``. Unannotated PEP 604
unions (``X = int | str``) are left alone because ``a | b`` on
arbitrary values is not reliably a type expression.

Examples
--------
Flagged::

    import collections.abc as cabc

    Clock = cabc.Callable[[], dt.datetime]

Preferred::

    type Clock = cabc.Callable[[], dt.datetime]
"""

from __future__ import annotations

import typing as typ

from astroid import nodes
from pylint import checkers

if typ.TYPE_CHECKING:
    from pylint.typing import MessageDefinitionTuple

_MSGS: typ.Final[dict[str, MessageDefinitionTuple]] = {
    "R9111": (
        "Declare type alias %r with a 'type' statement",
        "prefer-type-statement",
        (
            "Emitted when a module-level type alias is created by a plain "
            "assignment of a subscripted typing construct or by a "
            "'TypeAlias' annotation on a Python 3.12+ baseline. Use the "
            "PEP 695 'type' statement, which names the intent and defers "
            "evaluation of the aliased expression."
        ),
    ),
}

_MIN_TYPE_STATEMENT_VERSION: typ.Final = (3, 12)

# Modules whose subscripted attributes are type expressions rather than
# runtime values; an assignment of one to a module-level name is an alias.
_TYPING_MODULES: typ.Final = frozenset({
    "typing",
    "typing_extensions",
    "collections.abc",
})

# Builtin generics that read as type expressions when subscripted.
_BUILTIN_GENERICS: typ.Final = frozenset({
    "dict",
    "frozenset",
    "list",
    "set",
    "tuple",
    "type",
})


def _dotted_parts(node: nodes.NodeNG) -> tuple[nodes.Name, list[str]] | None:
    """Split a pure attribute chain into its base ``Name`` and attributes.

    Returns ``None`` for anything other than ``name`` or
    ``name.attr[.deeper]`` chains, mirroring
    :func:`._expressions.attribute_root` but preserving the attribute
    path so the chain's import origin can be reconstructed.

    Examples
    --------
    ``cabc.Callable`` yields the ``Name`` for ``cabc`` and
    ``["Callable"]``; ``get()`` yields ``None``.
    """
    attrs: list[str] = []
    current = node
    while isinstance(current, nodes.Attribute):
        attrs.append(current.attrname)
        current = current.expr
    if not isinstance(current, nodes.Name):
        return None
    attrs.reverse()
    return current, attrs


def _assignment_import_origin(
    assignment: nodes.NodeNG,
    bound_name: str,
) -> str | None:
    """Return the import origin *assignment* binds to *bound_name*.

    Classifies a single binding drawn from a name's lookup chain: an
    ``import`` or ``from`` import that binds *bound_name* yields its
    dotted origin, and any other assignment yields ``None``. An unaliased
    dotted ``import a.b.c`` binds only its top-level name and resolves to
    that top-level name.

    Examples
    --------
    For ``import collections.abc as cabc`` and ``bound_name="cabc"`` the
    result is ``"collections.abc"``; ``from typing import Callable`` with
    ``bound_name="Callable"`` yields ``"typing.Callable"``; a non-import
    binding yields ``None``.
    """
    match assignment:
        case nodes.Import(names=names):
            for modname, alias in names:
                if (alias or modname.partition(".")[0]) == bound_name:
                    return modname if alias else modname.partition(".")[0]
        case nodes.ImportFrom(modname=modname, names=names):
            for original, alias in names:
                if (alias or original) == bound_name:
                    return f"{modname}.{original}"
    return None


def _imported_origin(name_node: nodes.Name) -> str | None:
    """Resolve the dotted module path *name_node* was imported as.

    Scans *name_node*'s lookup assignments in order and returns the first
    import origin classified by :func:`_assignment_import_origin`, or
    ``None`` when no binding is an import. ``import collections.abc as
    cabc`` maps ``cabc`` to ``collections.abc``; ``from typing import
    Callable as C`` maps ``C`` to ``typing.Callable``. Names not bound by
    an import resolve to ``None``.

    Examples
    --------
    With ``import typing as typ`` in scope, the ``Name`` for ``typ``
    resolves to ``"typing"``.
    """
    _, assignments = name_node.lookup(name_node.name)
    for assignment in assignments:
        origin = _assignment_import_origin(assignment, name_node.name)
        if origin is not None:
            return origin
    return None


def _is_unshadowed_builtin_generic(name_node: nodes.Name) -> bool:
    """Return whether *name_node* is a builtin generic such as ``dict``.

    The name must resolve to the builtins scope; a module-level
    rebinding of ``dict`` shadows the builtin and disqualifies it.

    Examples
    --------
    A bare ``dict`` in a module that never rebinds it reports ``True``.
    """
    if name_node.name not in _BUILTIN_GENERICS:
        return False
    scope, _ = name_node.lookup(name_node.name)
    return isinstance(scope, nodes.Module) and scope.name == "builtins"


def _subscript_names_type(value: nodes.NodeNG) -> bool:
    """Return whether *value* subscripts a recognized typing construct.

    Examples
    --------
    ``cabc.Callable[[], int]`` (with ``import collections.abc as cabc``)
    and ``dict[str, int]`` report ``True``; ``matrix[0]`` reports
    ``False``.
    """
    if not isinstance(value, nodes.Subscript):
        return False
    parts = _dotted_parts(value.value)
    if parts is None:
        return False
    base, attrs = parts
    origin = _imported_origin(base)
    if origin is None:
        return not attrs and _is_unshadowed_builtin_generic(base)
    dotted = ".".join([origin, *attrs])
    module = dotted.rpartition(".")[0]
    return module in _TYPING_MODULES


def _is_type_alias_annotation(annotation: nodes.NodeNG) -> bool:
    """Return whether *annotation* resolves to ``typing.TypeAlias``.

    Examples
    --------
    ``TypeAlias`` imported from ``typing`` and ``typ.TypeAlias`` under
    ``import typing as typ`` both report ``True``.
    """
    parts = _dotted_parts(annotation)
    if parts is None:
        return False
    base, attrs = parts
    origin = _imported_origin(base)
    if origin is None:
        return False
    dotted = ".".join([origin, *attrs])
    return dotted in {f"{module}.TypeAlias" for module in _TYPING_MODULES}


class TypeAliasChecker(checkers.BaseChecker):
    """Report module-level type aliases that should be ``type`` statements.

    The check is inert until the configured ``py-version`` reaches 3.12,
    the first release with PEP 695 ``type`` statements.

    Examples
    --------
    Enable alongside the plugin and run pylint as usual::

        pylint --load-plugins=df12_python_lints --py-version=3.14 my_module.py
    """

    name = "df12-type-aliases"
    msgs = _MSGS

    def _type_statement_available(self) -> bool:
        """Return whether the configured baseline has the ``type`` statement."""
        return tuple(self.linter.config.py_version) >= _MIN_TYPE_STATEMENT_VERSION

    def visit_assign(self, node: nodes.Assign) -> None:
        """Check *node* for a module-level alias built by plain assignment.

        Examples
        --------
        Invoked by pylint's AST walker for every assignment statement.
        """
        if not self._type_statement_available():
            return
        if not isinstance(node.scope(), nodes.Module):
            return
        match node.targets:
            case [nodes.AssignName(name=target_name)]:
                pass
            case _:
                return
        if _subscript_names_type(node.value):
            self.add_message("prefer-type-statement", node=node, args=(target_name,))

    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        """Check *node* for a ``TypeAlias``-annotated alias.

        Examples
        --------
        Invoked by pylint's AST walker for every annotated assignment.
        """
        if not self._type_statement_available():
            return
        if not isinstance(node.scope(), nodes.Module):
            return
        if node.value is None or not isinstance(node.target, nodes.AssignName):
            return
        if _is_type_alias_annotation(node.annotation):
            self.add_message(
                "prefer-type-statement", node=node, args=(node.target.name,)
            )
