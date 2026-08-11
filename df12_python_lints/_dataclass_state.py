"""Classify dataclass fields and explicit runtime slot declarations.

The dataclass-slots analysis uses these helpers to distinguish storage-backed
instance state from ``ClassVar`` and ``InitVar`` pseudo-fields, including state
inherited through local dataclass and manually slotted lineages.
"""

from __future__ import annotations

import itertools
import typing as typ

from astroid import exceptions, nodes, util

from ._dataclass_decorators import (
    expression_origin,
    find_dataclass_decorator,
    subscript_target,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_PSEUDO_FIELD_ORIGINS = frozenset({
    "dataclasses.InitVar",
    "dataclasses.KW_ONLY",
    "typing.ClassVar",
    "typing_extensions.ClassVar",
})


def _dataclass_field_name(statement: nodes.NodeNG) -> str | None:
    """Return one real dataclass field name declared by *statement*."""
    if not isinstance(statement, nodes.AnnAssign) or not isinstance(
        statement.target, nodes.AssignName
    ):
        return None
    origin = expression_origin(subscript_target(statement.annotation))
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


def _inferred_slot_value(value: nodes.NodeNG) -> nodes.NodeNG | None:
    """Return one unambiguous inferred value for a slots expression."""
    try:
        inferred = tuple(itertools.islice(value.infer(), 2))
    except exceptions.InferenceError:
        return None
    if len(inferred) != 1 or inferred[0] is util.Uninferable:
        return None
    if not isinstance(inferred[0], nodes.NodeNG):
        return None
    return inferred[0]


def _slot_name(value: nodes.NodeNG) -> str | None:
    """Return one valid, unambiguously inferred slot name."""
    inferred = _inferred_slot_value(value)
    if not isinstance(inferred, nodes.Const) or not isinstance(inferred.value, str):
        return None
    return inferred.value if inferred.value.isidentifier() else None


def _node_elements(values: cabc.Iterable[object]) -> tuple[nodes.NodeNG, ...] | None:
    """Return *values* when every slot element is an Astroid node."""
    elements = tuple(values)
    if not all(isinstance(element, nodes.NodeNG) for element in elements):
        return None
    return typ.cast("tuple[nodes.NodeNG, ...]", elements)


def _slot_elements(value: nodes.NodeNG) -> tuple[nodes.NodeNG, ...] | None:
    """Return the elements from one statically supported slot value."""
    if isinstance(value, nodes.Const):
        return (value,)
    if isinstance(value, nodes.Dict):
        elements = tuple(key for key, _ in value.items if key is not None)
        return _node_elements(elements) if len(elements) == len(value.items) else None
    if isinstance(value, (nodes.List, nodes.Set, nodes.Tuple)):
        return _node_elements(value.elts)
    return None


def _validated_slot_names(
    elements: tuple[nodes.NodeNG, ...],
) -> frozenset[str] | None:
    """Validate every element and return the complete set of slot names."""
    names: set[str] = set()
    for element in elements:
        if (name := _slot_name(element)) is None:
            return None
        names.add(name)
    return frozenset(names)


def _resolved_slot_names(value: nodes.NodeNG) -> frozenset[str] | None:
    """Resolve and validate one complete ``__slots__`` value."""
    inferred = _inferred_slot_value(value)
    if inferred is None or (elements := _slot_elements(inferred)) is None:
        return None
    return _validated_slot_names(elements)


def local_slot_names(node: nodes.ClassDef) -> frozenset[str] | None:
    """Return validated names from *node*'s sole direct slots assignment."""
    values = tuple(
        value
        for statement in node.body
        if (value := _slots_value(statement)) is not None
    )
    return _resolved_slot_names(values[0]) if len(values) == 1 else None


def has_local_slots(node: nodes.ClassDef) -> bool:
    """Return whether *node* has one valid, locally resolved slots value."""
    return local_slot_names(node) is not None


def _local_instance_state(node: nodes.ClassDef) -> cabc.Iterator[str]:
    """Yield instance state declared directly by one class."""
    if find_dataclass_decorator(node) is not None:
        yield from dataclass_field_names(node)
    if (slot_names := local_slot_names(node)) is not None:
        yield from slot_names


def declared_instance_state(
    node: nodes.ClassDef,
    cache: dict[nodes.ClassDef, frozenset[str]] | None = None,
) -> frozenset[str]:
    """Return visible dataclass fields and slots, caching each lineage prefix."""
    state_cache = {} if cache is None else cache
    if node in state_cache:
        return state_cache[node]
    state = set(_local_instance_state(node))
    for ancestor in node.ancestors(recurs=False):
        if isinstance(ancestor, nodes.ClassDef):
            state.update(declared_instance_state(ancestor, state_cache))
    state_cache[node] = frozenset(state)
    return state_cache[node]


def has_declared_instance_fields(node: nodes.ClassDef) -> bool:
    """Return whether *node* visibly declares real dataclass fields."""
    return bool(dataclass_field_names(node))
