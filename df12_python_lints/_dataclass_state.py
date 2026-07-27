"""Classify statically visible dataclass fields and explicit slot state."""

from __future__ import annotations

import typing as typ

from astroid import nodes

from ._dataclass_decorators import expression_origin, find_dataclass_decorator

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_PSEUDO_FIELD_ORIGINS = frozenset({
    "dataclasses.InitVar",
    "dataclasses.KW_ONLY",
    "typing.ClassVar",
})


def _annotation_target(annotation: nodes.NodeNG) -> nodes.NodeNG:
    """Return the imported type expression wrapped by an annotation."""
    return annotation.value if isinstance(annotation, nodes.Subscript) else annotation


def _dataclass_field_name(statement: nodes.NodeNG) -> str | None:
    """Return one real dataclass field name declared by *statement*."""
    if not isinstance(statement, nodes.AnnAssign) or not isinstance(
        statement.target, nodes.AssignName
    ):
        return None
    origin = expression_origin(_annotation_target(statement.annotation))
    return None if origin in _PSEUDO_FIELD_ORIGINS else statement.target.name


def dataclass_field_names(node: nodes.ClassDef) -> frozenset[str]:
    """Return real dataclass fields declared directly by *node*."""
    return frozenset(
        field_name
        for statement in node.body
        if (field_name := _dataclass_field_name(statement)) is not None
    )


def _slots_value(statement: nodes.NodeNG) -> nodes.NodeNG | None:
    """Return the runtime value from a direct ``__slots__`` assignment."""
    match statement:
        case nodes.Assign(targets=[nodes.AssignName(name="__slots__")], value=value):
            return value
        case nodes.AnnAssign(
            target=nodes.AssignName(name="__slots__"), value=value
        ) if value is not None:
            return value
    return None


def has_local_slots(node: nodes.ClassDef) -> bool:
    """Return whether *node* assigns a runtime ``__slots__`` value."""
    return any(_slots_value(statement) is not None for statement in node.body)


def _literal_slot_names(value: nodes.NodeNG) -> cabc.Iterator[str]:
    """Yield statically visible names from one explicit slot value."""
    if isinstance(value, nodes.Const) and isinstance(value.value, str):
        yield value.value
        return
    if isinstance(value, (nodes.List, nodes.Set, nodes.Tuple)):
        for element in value.elts:
            if isinstance(element, nodes.Const) and isinstance(element.value, str):
                yield element.value


def _local_slot_names(node: nodes.ClassDef) -> cabc.Iterator[str]:
    """Yield literal slot names assigned directly by *node*."""
    for statement in node.body:
        if (value := _slots_value(statement)) is not None:
            yield from _literal_slot_names(value)


def _local_instance_state(node: nodes.ClassDef) -> cabc.Iterator[str]:
    """Yield instance state declared directly by one class."""
    if find_dataclass_decorator(node) is not None:
        yield from dataclass_field_names(node)
    yield from _local_slot_names(node)


def declared_instance_state(node: nodes.ClassDef) -> frozenset[str]:
    """Return visible dataclass fields and explicit slots across the lineage."""
    classes = (
        node,
        *(
            ancestor
            for ancestor in node.ancestors(recurs=True)
            if isinstance(ancestor, nodes.ClassDef)
        ),
    )
    return frozenset(
        name for class_node in classes for name in _local_instance_state(class_node)
    )


def has_declared_instance_fields(node: nodes.ClassDef) -> bool:
    """Return whether *node* visibly declares real dataclass fields."""
    return bool(dataclass_field_names(node))
