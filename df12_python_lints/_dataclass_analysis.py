"""Decide when generated dataclass slots are safe and meaningful.

The :class:`~df12_python_lints.dataclass_slots.DataclassSlotsChecker` delegates
state, extension-boundary, decorator-order, class-cell, and inherited-layout
analysis to this module.  Its conservative result avoids suggesting slots when
Astroid cannot prove that a closed layout will remain valid.
"""

from __future__ import annotations

import contextlib
import typing as typ

from astroid import bases, exceptions, nodes

from ._dataclass_decorators import (
    decorator_target,
    expression_origin,
    find_dataclass_decorator,
    has_literal_slots,
    subscript_target,
)
from ._dataclass_inference import (
    VARIABLE_LENGTH_BUILTIN_QNAMES,
    Layout,
    inferred_class,
)
from ._dataclass_state import (
    declared_instance_state,
    has_declared_instance_fields,
    has_local_slots,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_MIN_MULTIPLE_BASES = 2


def _direct_nodes(root: nodes.NodeNG) -> cabc.Iterator[nodes.NodeNG]:
    """Yield descendants without entering nested executable scopes."""
    for child in root.get_children():
        if isinstance(
            child,
            (nodes.ClassDef, nodes.FunctionDef, nodes.AsyncFunctionDef, nodes.Lambda),
        ):
            continue
        yield child
        yield from _direct_nodes(child)


def _direct_methods(node: nodes.ClassDef) -> cabc.Iterator[nodes.FunctionDef]:
    """Yield direct instance methods declared by *node*."""
    for statement in node.body:
        if not isinstance(statement, (nodes.FunctionDef, nodes.AsyncFunctionDef)):
            continue
        if statement.type == "method" and statement.argnames():
            yield statement


def _decorated_with(method: nodes.FunctionDef, origin: str) -> bool:
    """Return whether *method* has a decorator imported from *origin*."""
    return method.decorators is not None and any(
        expression_origin(decorator_target(decorator)) == origin
        for decorator in method.decorators.nodes
    )


def _is_unshadowed_builtin(node: nodes.Name, name: str) -> bool:
    """Return whether *node* is the unshadowed builtin called *name*."""
    if node.name != name:
        return False
    _, assignments = node.lookup(name)
    if len(assignments) != 1:
        return False
    assignment = assignments[0]
    return isinstance(assignment, (nodes.ClassDef, nodes.FunctionDef)) and (
        assignment.qname() == f"builtins.{name}"
    )


def _is_instance_name(node: nodes.NodeNG, parameter: str) -> bool:
    """Return whether *node* is the current method's instance parameter."""
    return isinstance(node, nodes.Name) and node.name == parameter


def _call_requires_dictionary(call: nodes.Call, parameter: str) -> bool:
    """Return whether *call* demonstrates dynamic instance state."""
    match call:
        case nodes.Call(func=nodes.Name() as function, args=[first, *_]) if (
            _is_instance_name(first, parameter)
        ):
            return any(
                _is_unshadowed_builtin(function, name)
                for name in ("vars", "setattr", "delattr")
            )
    return False


def _object_setattr_is_open(
    call: nodes.Call, parameter: str, declared_state: frozenset[str]
) -> bool:
    """Return whether an ``object.__setattr__`` call names undeclared state."""
    match call:
        case nodes.Call(
            func=nodes.Attribute(
                expr=nodes.Name() as object_name,
                attrname="__setattr__",
            ),
            args=[instance, name_node, *_],
        ) if _is_unshadowed_builtin(object_name, "object") and _is_instance_name(
            instance, parameter
        ):
            pass
        case _:
            return False
    return not (
        isinstance(name_node, nodes.Const)
        and isinstance(name_node.value, str)
        and name_node.value in declared_state
    )


def _is_instance_dictionary(node: nodes.NodeNG, parameter: str) -> bool:
    """Return whether *node* reads the instance dictionary."""
    return (
        isinstance(node, nodes.Attribute)
        and node.attrname == "__dict__"
        and _is_instance_name(node.expr, parameter)
    )


def _attribute_mutation_is_open(
    node: nodes.NodeNG, parameter: str, declared_state: frozenset[str]
) -> bool:
    """Return whether *node* mutates an undeclared instance attribute."""
    if not isinstance(node, (nodes.AssignAttr, nodes.DelAttr)):
        return False
    return _is_instance_name(node.expr, parameter) and (
        node.attrname not in declared_state
    )


def _node_requires_open_state(
    node: nodes.NodeNG, parameter: str, declared_state: frozenset[str]
) -> bool:
    """Return whether one method descendant demonstrates open instance state."""
    if _is_instance_dictionary(node, parameter):
        return True
    if not isinstance(node, nodes.Call):
        return _attribute_mutation_is_open(node, parameter, declared_state)
    return any((
        _call_requires_dictionary(node, parameter),
        _object_setattr_is_open(node, parameter, declared_state),
    ))


def _method_requires_open_state(
    method: nodes.FunctionDef, declared_state: frozenset[str]
) -> bool:
    """Return whether one direct method visibly depends on open state."""
    parameter = method.argnames()[0]
    if _decorated_with(method, "functools.cached_property"):
        return True
    return any(
        _node_requires_open_state(child, parameter, declared_state)
        for child in _direct_nodes(method)
    )


def _is_zero_argument_super(node: nodes.NodeNG) -> bool:
    """Return whether *node* calls the unshadowed ``super`` without arguments."""
    match node:
        case nodes.Call(
            func=nodes.Name() as function,
            args=[],
            keywords=[],
        ):
            return _is_unshadowed_builtin(function, "super")
    return False


def _uses_class_cell(method: nodes.FunctionDef) -> bool:
    """Return whether *method*'s subtree uses a replacement-class hazard."""
    for child in method.nodes_of_class((nodes.Name, nodes.Call)):
        if isinstance(child, nodes.Name) and child.name == "__class__":
            return True
        if _is_zero_argument_super(child):
            return True
    return False


def _has_extension_base(node: nodes.ClassDef) -> bool:
    """Return whether *node* directly names a known extension boundary."""
    return any(
        expression_origin(subscript_target(base))
        in {"abc.ABC", "typing.Protocol", "typing_extensions.Protocol"}
        for base in node.bases
    )


def _has_class_header_boundary(node: nodes.ClassDef) -> bool:
    """Return whether explicit header configuration affects class creation."""
    if node.keywords:
        return True
    try:
        return node.declared_metaclass() is not None
    except exceptions.InferenceError:
        return True


def _methods_have_class_hazard(methods: tuple[nodes.FunctionDef, ...]) -> bool:
    """Return whether a direct method makes replacement-class slots unsafe."""
    return any(
        _decorated_with(method, "abc.abstractmethod") or _uses_class_cell(method)
        for method in methods
    )


def _methods_require_open_state(
    methods: tuple[nodes.FunctionDef, ...], node: nodes.ClassDef
) -> bool:
    """Return whether direct methods demonstrate deliberately open state."""
    declared_state = declared_instance_state(node)
    return any(
        _method_requires_open_state(method, declared_state) for method in methods
    )


def _has_unsafe_inner_decorator(node: nodes.ClassDef, decorator: nodes.NodeNG) -> bool:
    """Return whether an inner decorator may retain the original class."""
    if node.decorators is None:
        return True
    decorator_index = node.decorators.nodes.index(decorator)
    return any(
        expression_origin(decorator_target(inner)) != "typing.final"
        for inner in node.decorators.nodes[decorator_index + 1 :]
    )


def has_local_slots_hazard(node: nodes.ClassDef, decorator: nodes.NodeNG) -> bool:
    """Return whether local class evidence makes generated slots unsafe."""
    methods = tuple(_direct_methods(node))
    checks = (
        lambda: _has_class_header_boundary(node),
        lambda: _has_extension_base(node),
        lambda: "__init_subclass__" in node.locals,
        lambda: _methods_have_class_hazard(methods),
        lambda: _methods_require_open_state(methods, node),
    )
    if any(check() for check in checks):
        return True
    return _has_unsafe_inner_decorator(node, decorator)


def _local_dataclass_base(
    base: nodes.NodeNG | bases.Proxy, module: nodes.Module
) -> nodes.ClassDef | None:
    """Return a local dataclass named by *base*, when inference is unambiguous."""
    inferred = inferred_class(base)
    if inferred is None or inferred.root() is not module:
        return None
    return inferred if find_dataclass_decorator(inferred) is not None else None


def _multiple_inheritance_dataclass_bases(
    child: nodes.ClassDef,
    module: nodes.Module,
    base_layout: cabc.Callable[[nodes.NodeNG | bases.Proxy], Layout],
) -> tuple[nodes.ClassDef, ...]:
    """Return local dataclass bases in a conflicting slot-layout shape."""
    if len(child.bases) < _MIN_MULTIPLE_BASES:
        return ()
    layouts = tuple(base_layout(base) for base in child.bases)
    if layouts.count(Layout.SLOTTED) <= 1:
        return ()
    return tuple(
        inferred
        for base, layout in zip(child.bases, layouts, strict=True)
        if layout is Layout.SLOTTED
        and (inferred := _local_dataclass_base(base, module)) is not None
    )


class LayoutAnalyzer:
    """Cache conservative layout and reverse-inheritance decisions per module."""

    def __init__(self, module: nodes.Module) -> None:
        """Build reverse-inheritance facts for *module* in two phases.

        ``_find_multiple_bases`` first evaluates provisional eligibility while
        ``_multiple_bases`` is empty.  Clearing that provisional cache is
        required before final evaluation incorporates the discovered conflicts.
        """
        self.module = module
        self._eligibility: dict[nodes.ClassDef, bool] = {}
        self._layouts: dict[nodes.ClassDef, Layout] = {}
        self._visiting: set[nodes.ClassDef] = set()
        self._multiple_bases: frozenset[nodes.ClassDef] = frozenset()
        self._multiple_bases = self._find_multiple_bases()
        self._eligibility.clear()
        self._layouts.clear()

    def _find_multiple_bases(self) -> frozenset[nodes.ClassDef]:
        """Find local dataclass bases used in direct multiple inheritance."""
        unsafe: set[nodes.ClassDef] = set()
        for child in self.module.nodes_of_class(nodes.ClassDef):
            unsafe.update(
                _multiple_inheritance_dataclass_bases(
                    child, self.module, self._base_layout
                )
            )
        return frozenset(unsafe)

    @staticmethod
    def _field_layout(node: nodes.ClassDef) -> Layout:
        """Return the layout contribution from *node*'s declared fields."""
        return Layout.SLOTTED if has_declared_instance_fields(node) else Layout.NEUTRAL

    def _inherited_layout(self, node: nodes.ClassDef) -> Layout:
        """Combine the provable layout inherited from *node*'s direct bases."""
        layouts = tuple(self._base_layout(base) for base in node.bases)
        if Layout.UNSAFE in layouts or layouts.count(Layout.SLOTTED) > 1:
            return Layout.UNSAFE
        return Layout.SLOTTED if Layout.SLOTTED in layouts else Layout.NEUTRAL

    def _local_layout(self, node: nodes.ClassDef) -> Layout:
        """Classify a base declared in the linted module."""
        inherited_layout = self._inherited_layout(node)
        if inherited_layout is Layout.UNSAFE:
            return Layout.UNSAFE
        if has_local_slots(node):
            own_layout = self._external_layout(node)
            return max(inherited_layout, own_layout)
        decorator = find_dataclass_decorator(node)
        if decorator is None:
            return Layout.UNSAFE
        if has_literal_slots(decorator) or self.is_eligible(node):
            own_layout = self._field_layout(node)
        else:
            return Layout.UNSAFE
        return max(inherited_layout, own_layout)

    @contextlib.contextmanager
    def _visiting_node(self, node: nodes.ClassDef) -> cabc.Iterator[None]:
        """Mark *node* as visiting for the duration of recursive analysis."""
        self._visiting.add(node)
        try:
            yield
        finally:
            self._visiting.remove(node)

    @staticmethod
    def _external_layout(node: nodes.ClassDef) -> Layout:
        """Classify an inferred base outside the linted module."""
        try:
            slots = node.slots()
        except exceptions.InferenceError:
            return Layout.UNSAFE
        if slots is None:
            return Layout.UNSAFE
        return Layout.SLOTTED if slots else Layout.NEUTRAL

    def _base_layout(self, base: nodes.NodeNG | bases.Proxy) -> Layout:
        """Classify one explicit base lineage."""
        inferred = inferred_class(base)
        if inferred is None:
            return Layout.UNSAFE
        if inferred.qname() == "builtins.object":
            return Layout.NEUTRAL
        if inferred.qname() in VARIABLE_LENGTH_BUILTIN_QNAMES:
            return Layout.UNSAFE
        if inferred.root() is self.module:
            if inferred not in self._layouts:
                self._layouts[inferred] = self._local_layout(inferred)
            return self._layouts[inferred]
        return self._external_layout(inferred)

    def is_eligible(self, node: nodes.ClassDef) -> bool:
        """Return whether *node* may safely receive generated slots."""
        if node in self._eligibility:
            return self._eligibility[node]
        if node in self._visiting:
            return False
        with self._visiting_node(node):
            decorator = find_dataclass_decorator(node)
            result = (
                decorator is not None
                and not has_literal_slots(decorator)
                and not has_local_slots(node)
                and node not in self._multiple_bases
                and not has_local_slots_hazard(node, decorator)
                and self._inherited_layout(node) is not Layout.UNSAFE
            )
        self._eligibility[node] = result
        return result
