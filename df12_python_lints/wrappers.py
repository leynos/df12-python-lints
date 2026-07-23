"""Checker flagging trivial wrappers with no logic of their own.

A function whose whole body returns an attribute of one of its parameters,
or calls through such an attribute while passing its own parameters along
unchanged, adds a name and a call frame without adding behaviour. Access
the attribute or bound method directly at the call site, or expose it as a
property when the indirection is deliberate.

Examples
--------
Flagged::

    def get_name(user):
        return user.profile.name

    def send(self, message):
        return self._client.send(message)

Preferred::

    user.profile.name          # at the call site
    self._client.send(message)  # at the call site
"""

from __future__ import annotations

import typing as typ

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


def _is_passthrough_argument(
    argument: nodes.NodeNG, parameter_names: cabc.Container[str]
) -> bool:
    """Return whether *argument* forwards a parameter unchanged.

    Examples
    --------
    ``message`` and ``*args`` forward parameters; ``message.upper()`` and
    ``42`` do not.
    """
    match argument:
        case nodes.Starred(value=nodes.Name(name=name)) | nodes.Name(name=name):
            return name in parameter_names
        case _:
            return False


def _is_passthrough_call(
    call: nodes.Call, parameter_names: cabc.Container[str]
) -> bool:
    """Return whether *call* only forwards parameters unchanged.

    Examples
    --------
    ``self._client.send(message)`` forwards; ``self._client.send(message,
    retries=3)`` supplies new information and does not.
    """
    arguments_forward = all(
        _is_passthrough_argument(argument, parameter_names) for argument in call.args
    )
    keywords_forward = all(
        _is_passthrough_argument(keyword.value, parameter_names)
        for keyword in call.keywords
    )
    return arguments_forward and keywords_forward


def _proxy_root(
    statement: nodes.NodeNG, parameter_names: cabc.Container[str]
) -> nodes.Name | None:
    """Return the base name a pure forwarding *statement* proxies through.

    Eligible statements return an attribute chain, or return or evaluate
    a call on an attribute chain whose arguments all forward parameters
    unchanged.

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
            if not _is_passthrough_call(call, parameter_names):
                return None
            return attribute_root(call.func)
        case _:
            return None


def _forwarded_parameter(node: nodes.FunctionDef) -> str | None:
    """Return the parameter *node* merely forwards through, if any.

    Examples
    --------
    ``def get(user): return user.name`` returns ``"user"``; a function
    with any other body shape returns ``None``.
    """
    parameter_names = frozenset(node.argnames())
    match _body_without_docstring(node):
        case [statement]:
            root = _proxy_root(statement, parameter_names)
        case _:
            return None
    if root is None or root.name not in parameter_names:
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

    visit_asyncfunctiondef = visit_functiondef
