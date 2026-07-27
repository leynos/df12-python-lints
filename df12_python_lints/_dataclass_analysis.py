"""Conservative Astroid analysis for the dataclass-slots checker."""

from __future__ import annotations

import enum
import typing as typ

from astroid import bases, exceptions, nodes, util

from ._dataclass_decorators import (
    decorator_target,
    expression_origin,
    find_dataclass_decorator,
    has_literal_slots,
    has_local_slots,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_VARIABLE_LENGTH_BUILTINS = frozenset({
    "builtins.bytearray",
    "builtins.bytes",
    "builtins.dict",
    "builtins.list",
    "builtins.set",
    "builtins.str",
    "builtins.tuple",
})
_MIN_MULTIPLE_BASES = 2


class Layout(enum.Enum):
    """Describe the instance layout contributed by one base lineage."""

    NEUTRAL = enum.auto()
    SLOTTED = enum.auto()
    UNSAFE = enum.auto()


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
        _attribute_mutation_is_open(node, parameter, declared_state),
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
    """Return whether *method* directly uses a replacement-class hazard."""
    for child in _direct_nodes(method):
        if isinstance(child, nodes.Name) and child.name == "__class__":
            return True
        if _is_zero_argument_super(child):
            return True
    return False


def _declared_state(node: nodes.ClassDef) -> frozenset[str]:
    """Return names visibly declared across *node*'s local base lineage."""
    declared = set(node.locals)
    for ancestor in node.ancestors(recurs=True):
        if isinstance(ancestor, nodes.ClassDef):
            declared.update(ancestor.locals)
    return frozenset(declared)


def _has_extension_base(node: nodes.ClassDef) -> bool:
    """Return whether *node* directly names a known extension boundary."""
    return any(
        expression_origin(base) in {"abc.ABC", "typing.Protocol"} for base in node.bases
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
    declared_state = _declared_state(node)
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


def has_local_hold_tongue_evidence(
    node: nodes.ClassDef, decorator: nodes.NodeNG
) -> bool:
    """Return whether local class evidence makes generated slots unsafe."""
    methods = tuple(_direct_methods(node))
    if any((
        _has_class_header_boundary(node),
        _has_extension_base(node),
        "__init_subclass__" in node.locals,
        _methods_have_class_hazard(methods),
        _methods_require_open_state(methods, node),
    )):
        return True
    return _has_unsafe_inner_decorator(node, decorator)


def _inferred_class(base: nodes.NodeNG | bases.Proxy) -> nodes.ClassDef | None:
    """Infer one unambiguous class for *base*, or return ``None``."""
    try:
        inferred = list(base.infer())
    except exceptions.InferenceError:
        return None
    if len(inferred) != 1 or inferred[0] is util.Uninferable:
        return None
    candidate = inferred[0]
    if isinstance(candidate, bases.Instance):
        candidate = candidate._proxied
    return candidate if isinstance(candidate, nodes.ClassDef) else None


def _has_declared_instance_fields(node: nodes.ClassDef) -> bool:
    """Return whether *node* visibly declares dataclass instance fields."""
    return any(
        isinstance(statement, (nodes.AnnAssign, nodes.Assign))
        for statement in node.body
    )


def _local_dataclass_base(
    base: nodes.NodeNG | bases.Proxy, module: nodes.Module
) -> nodes.ClassDef | None:
    """Return a local dataclass named by *base*, when inference is unambiguous."""
    inferred = _inferred_class(base)
    if inferred is None or inferred.root() is not module:
        return None
    return inferred if find_dataclass_decorator(inferred) is not None else None


def _multiple_inheritance_dataclass_bases(
    child: nodes.ClassDef, module: nodes.Module
) -> tuple[nodes.ClassDef, ...]:
    """Return local dataclass bases in one direct multiple-inheritance shape."""
    if len(child.bases) < _MIN_MULTIPLE_BASES:
        return ()
    return tuple(
        inferred
        for base in child.bases
        if (inferred := _local_dataclass_base(base, module)) is not None
    )


class LayoutAnalyzer:
    """Cache conservative layout and reverse-inheritance decisions per module."""

    def __init__(self, module: nodes.Module) -> None:
        """Build reverse-inheritance facts for *module*."""
        self.module = module
        self._eligibility: dict[nodes.ClassDef, bool] = {}
        self._visiting: set[nodes.ClassDef] = set()
        self._multiple_bases = self._find_multiple_bases()

    def _find_multiple_bases(self) -> frozenset[nodes.ClassDef]:
        """Find local dataclass bases used in direct multiple inheritance."""
        unsafe: set[nodes.ClassDef] = set()
        for child in self.module.nodes_of_class(nodes.ClassDef):
            unsafe.update(_multiple_inheritance_dataclass_bases(child, self.module))
        return frozenset(unsafe)

    @staticmethod
    def _field_layout(node: nodes.ClassDef) -> Layout:
        """Return the layout contribution from *node*'s declared fields."""
        return Layout.SLOTTED if _has_declared_instance_fields(node) else Layout.NEUTRAL

    def _local_layout(self, node: nodes.ClassDef) -> Layout:
        """Classify a base declared in the linted module."""
        if has_local_slots(node):
            return self._external_layout(node)
        decorator = find_dataclass_decorator(node)
        if decorator is None:
            return Layout.UNSAFE
        if has_literal_slots(decorator):
            return self._field_layout(node)
        return self._field_layout(node) if self.is_eligible(node) else Layout.UNSAFE

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
        inferred = _inferred_class(base)
        if inferred is None:
            return Layout.UNSAFE
        if inferred.qname() == "builtins.object":
            return Layout.NEUTRAL
        if inferred.qname() in _VARIABLE_LENGTH_BUILTINS:
            return Layout.UNSAFE
        if inferred.root() is self.module:
            return self._local_layout(inferred)
        return self._external_layout(inferred)

    def _bases_are_safe(self, node: nodes.ClassDef) -> bool:
        """Return whether *node*'s inherited layout is provably slot-only."""
        layouts = tuple(self._base_layout(base) for base in node.bases)
        return Layout.UNSAFE not in layouts and layouts.count(Layout.SLOTTED) <= 1

    def is_eligible(self, node: nodes.ClassDef) -> bool:
        """Return whether *node* may safely receive generated slots."""
        if node in self._eligibility:
            return self._eligibility[node]
        if node in self._visiting:
            return False
        self._visiting.add(node)
        decorator = find_dataclass_decorator(node)
        result = (
            decorator is not None
            and not has_literal_slots(decorator)
            and not has_local_slots(node)
            and node not in self._multiple_bases
            and not has_local_hold_tongue_evidence(node, decorator)
            and self._bases_are_safe(node)
        )
        self._visiting.remove(node)
        self._eligibility[node] = result
        return result
