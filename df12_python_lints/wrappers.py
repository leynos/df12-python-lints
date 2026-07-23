"""Checker flagging trivial wrappers with no logic of their own.

Two shapes of forwarding add a name and a call frame without adding
behaviour:

- returning an attribute of a parameter, or calling through such an
  attribute with the function's own parameters passed along unchanged
  (``trivial-attribute-wrapper``); and
- forwarding every argument unchanged to another module-level or
  imported function (``trivial-alias-wrapper``).

Access the attribute, bound method, or target function directly at the
call site — or alias it with an import — unless the indirection is
deliberate.

Examples
--------
Flagged::

    def get_name(user):
        return user.profile.name

    def send(self, message):
        return self._client.send(message)

    def foo(qux):
        return bar(qux)

Preferred::

    user.profile.name           # at the call site
    self._client.send(message)  # at the call site
    from mymodule import bar as foo
"""

from __future__ import annotations

import typing as typ

import astroid
from astroid import nodes
from pylint import checkers

from ._expressions import attribute_root

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from pylint.typing import MessageDefinitionTuple

_MSGS: typ.Final[dict[str, MessageDefinitionTuple]] = {
    "R9104": (
        "Function %r only forwards attribute access or a proxied call",
        "trivial-attribute-wrapper",
        (
            "Emitted when a function body does nothing but return an "
            "attribute of one of its parameters, or call through such an "
            "attribute with its own parameters passed along unchanged. "
            "Access the attribute or bound method directly at the call "
            "site, or expose it as a property when the indirection is "
            "required."
        ),
    ),
    "R9110": (
        "Function %r only forwards its arguments to %r",
        "trivial-alias-wrapper",
        (
            "Emitted when a function body does nothing but call another "
            "module-level or imported function with its own parameters "
            "passed along unchanged. Call the target directly, or alias "
            "it with 'from module import target as name' when a "
            "different name is wanted."
        ),
    ),
}


def _body_without_docstring(node: nodes.FunctionDef) -> list[nodes.NodeNG]:
    """Return the statements of *node* excluding a leading docstring.

    Examples
    --------
    A function holding a docstring and a ``return`` yields a single-item
    list containing the ``return`` statement.
    """
    match list(node.body):
        case [nodes.Expr(value=nodes.Const()), *rest]:
            return rest
        case body:
            return body


def _forwarded_name(argument: nodes.NodeNG) -> str | None:
    """Return the name *argument* forwards unchanged, if it is one.

    Examples
    --------
    ``message`` and ``*args`` forward names; ``message.upper()`` and
    ``42`` do not.
    """
    match argument:
        case nodes.Starred(value=nodes.Name(name=name)) | nodes.Name(name=name):
            return name
        case _:
            return None


def _is_passthrough_call(call: nodes.Call, expected: cabc.Sequence[str]) -> bool:
    """Return whether *call* forwards exactly *expected*, in order.

    Every expected parameter must be forwarded exactly once, and the
    positional arguments must keep the wrapper's declaration order.
    Reordering, repeating, or omitting a parameter adapts the call,
    which is behaviour rather than trivial forwarding.

    Examples
    --------
    With parameters ``(a, b)``, ``target(a, b)`` and ``target(a, b=b)``
    forward; ``target(b, a)``, ``target(a, a)``, and ``target(a)`` do
    not.
    """
    positional: list[str] = []
    for argument in call.args:
        name = _forwarded_name(argument)
        if name is None:
            return False
        positional.append(name)
    keyword_names: list[str] = []
    for keyword in call.keywords:
        name = _forwarded_name(keyword.value)
        if name is None:
            return False
        keyword_names.append(name)
    if sorted([*positional, *keyword_names]) != sorted(expected):
        return False
    forwarded_positionally = set(positional)
    return positional == [
        parameter for parameter in expected if parameter in forwarded_positionally
    ]


def _proxy_root(
    statement: nodes.NodeNG, parameters: cabc.Sequence[str]
) -> nodes.Name | None:
    """Return the base name a pure forwarding *statement* proxies through.

    Eligible statements return an attribute chain, or return or evaluate
    a call on an attribute chain that forwards every remaining parameter
    unchanged and in declaration order.

    Examples
    --------
    ``return user.profile.name`` returns the ``Name`` node for ``user``;
    ``return transform(user.name)`` returns ``None``.
    """
    match statement:
        case nodes.Return(value=nodes.Attribute() as value):
            return attribute_root(value)
        case (
            nodes.Return(value=nodes.Call() as call)
            | nodes.Expr(value=nodes.Call() as call)
        ):
            if not isinstance(call.func, nodes.Attribute):
                return None
            root = attribute_root(call.func)
            if root is None:
                return None
            expected = [name for name in parameters if name != root.name]
            if not _is_passthrough_call(call, expected):
                return None
            return root
        case _:
            return None


def _aliased_call(statement: nodes.NodeNG) -> nodes.Call | None:
    """Return the bare-name call *statement* forwards to, if any.

    Examples
    --------
    ``return bar(qux)`` returns the call node; ``return obj.bar(qux)``
    returns ``None`` because the target is an attribute chain.
    """
    match statement:
        case (
            nodes.Return(value=nodes.Call(func=nodes.Name()) as call)
            | nodes.Expr(value=nodes.Call(func=nodes.Name()) as call)
        ):
            return call
        case _:
            return None


def _import_infers_function(name_node: nodes.Name) -> bool:
    """Return whether an imported *name_node* infers to a function.

    Imported classes must not count: a factory wrapping a constructor
    keeps a deliberate name, matching the local ``ClassDef`` exemption.

    Examples
    --------
    ``dumps`` from ``json`` infers to a function; ``OrderedDict`` from
    ``collections`` infers to a class and reports ``False``.
    """
    try:
        inferred = next(name_node.infer())
    except (astroid.InferenceError, StopIteration):
        return False
    return isinstance(inferred, nodes.FunctionDef)


def _resolves_to_function(name_node: nodes.Name) -> bool:
    """Return whether *name_node* names a module function or one imported.

    Parameters, local bindings, classes, and builtins do not qualify:
    calling through a parameter is higher-order code, and wrapping a
    class or builtin is a factory with a deliberate name. Imported
    bindings only qualify when inference confirms a function.

    Examples
    --------
    With ``def bar(...)`` at module level, a ``Name`` node for ``bar``
    reports ``True``; a ``Name`` node for ``str`` reports ``False``.
    """
    _, assignments = name_node.lookup(name_node.name)
    for assignment in assignments:
        match assignment:
            case nodes.FunctionDef() if isinstance(assignment.parent, nodes.Module):
                return True
            case nodes.Import() | nodes.ImportFrom():
                return _import_infers_function(name_node)
            case _:
                continue
    return False


def _alias_target(node: nodes.FunctionDef) -> str | None:
    """Return the function *node* merely re-invokes, if any.

    Examples
    --------
    ``def foo(qux): return bar(qux)`` returns ``"bar"`` when ``bar`` is
    a module-level function; ``def apply(f, x): return f(x)`` returns
    ``None``.
    """
    parameters = tuple(node.argnames())
    match _body_without_docstring(node):
        case [statement]:
            call = _aliased_call(statement)
        case _:
            return None
    if call is None or not isinstance(call.func, nodes.Name):
        return None
    if call.func.name in parameters:
        return None
    if not _is_passthrough_call(call, parameters):
        return None
    if not _resolves_to_function(call.func):
        return None
    return call.func.name


def _forwarded_parameter(node: nodes.FunctionDef) -> str | None:
    """Return the parameter *node* merely forwards through, if any.

    Examples
    --------
    ``def get(user): return user.name`` returns ``"user"``; a function
    with any other body shape returns ``None``.
    """
    parameters = tuple(node.argnames())
    match _body_without_docstring(node):
        case [statement]:
            root = _proxy_root(statement, parameters)
        case _:
            return None
    if root is None or root.name not in parameters:
        return None
    return root.name


class TrivialWrapperChecker(checkers.BaseChecker):
    """Report functions with no logic beyond forwarding.

    Decorated functions are exempt: decorators such as ``property`` or
    ``functools.cache`` make the forwarding deliberate.

    Examples
    --------
    Enable alongside the plugin and run pylint as usual::

        pylint --load-plugins=df12_python_lints my_module.py
    """

    name = "df12-trivial-wrapper"
    msgs = _MSGS

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check *node* for a body that only forwards.

        Examples
        --------
        Invoked by pylint's AST walker for every function definition.
        """
        if node.decorators is not None:
            return
        if _forwarded_parameter(node) is not None:
            self.add_message("trivial-attribute-wrapper", node=node, args=(node.name,))
            return
        target = _alias_target(node)
        if target is not None:
            self.add_message(
                "trivial-alias-wrapper", node=node, args=(node.name, target)
            )

    visit_asyncfunctiondef = visit_functiondef
