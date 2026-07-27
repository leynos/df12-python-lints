"""Binding-aware decorator recognition for standard-library dataclasses."""

from __future__ import annotations

from astroid import bases, nodes


def _import_binding_origin(
    names: list[tuple[str, str | None]], bound_name: str
) -> str | None:
    """Return the module path an ``import`` binds to *bound_name*."""
    for original, alias in names:
        if (alias or original.split(".", maxsplit=1)[0]) == bound_name:
            return original if alias else original.split(".", maxsplit=1)[0]
    return None


def _assignment_origin(assignment: nodes.NodeNG, bound_name: str) -> str | None:
    """Return the import origin represented by one lexical binding."""
    match assignment:
        case nodes.Import(names=names):
            return _import_binding_origin(names, bound_name)
        case nodes.ImportFrom(modname=modname, names=names):
            for original, alias in names:
                if (alias or original) == bound_name:
                    return f"{modname}.{original}"
    return None


def imported_origin(name_node: nodes.Name) -> str | None:
    """Resolve the import origin of *name_node*'s active lexical binding."""
    _, assignments = name_node.lookup(name_node.name)
    origins = {
        origin
        for assignment in assignments
        if (origin := _assignment_origin(assignment, name_node.name)) is not None
    }
    return origins.pop() if len(origins) == 1 and len(assignments) == 1 else None


def expression_origin(node: nodes.NodeNG | bases.Proxy) -> str | None:
    """Resolve an imported dotted expression without executing linted code."""
    match node:
        case nodes.Name():
            return imported_origin(node)
        case nodes.Attribute(expr=expr, attrname=attrname):
            prefix = expression_origin(expr)
            return f"{prefix}.{attrname}" if prefix is not None else None
    return None


def decorator_target(decorator: nodes.NodeNG) -> nodes.NodeNG:
    """Return the callable expression underlying *decorator*."""
    return decorator.func if isinstance(decorator, nodes.Call) else decorator


def find_dataclass_decorator(node: nodes.ClassDef) -> nodes.NodeNG | None:
    """Return *node*'s real stdlib dataclass decorator, when present."""
    if node.decorators is None:
        return None
    for decorator in node.decorators.nodes:
        if expression_origin(decorator_target(decorator)) == "dataclasses.dataclass":
            return decorator
    return None


def has_literal_slots(decorator: nodes.NodeNG) -> bool:
    """Return whether *decorator* contains the lexical pair ``slots=True``."""
    if not isinstance(decorator, nodes.Call):
        return False
    return any(
        keyword.arg == "slots"
        and isinstance(keyword.value, nodes.Const)
        and keyword.value.value is True
        for keyword in decorator.keywords
    )
