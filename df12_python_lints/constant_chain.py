"""Checker flagging constant-comparison chains better served by ``match``.

The checker looks for ``if``/``elif`` chains where every branch test
compares one subject with constants, enumeration members, or literals —
either by equality or by membership in a literal collection. Such chains
are clearer as a ``match`` statement over an enumeration of the accepted
values.

Examples
--------
Flagged::

    if colour == Colour.RED:
        stop()
    elif colour in {Colour.AMBER, Colour.GREEN}:
        go()

Preferred::

    match colour:
        case Colour.RED:
            stop()
        case Colour.AMBER | Colour.GREEN:
            go()
"""

from __future__ import annotations

import typing as typ

from astroid import nodes
from pylint import checkers

from ._chains import elif_chain_tests, is_elif_branch

if typ.TYPE_CHECKING:
    from astroid import bases
    from pylint.typing import MessageDefinitionTuple

_MIN_CHAIN_TESTS = 2

_MSGS: typ.Final[dict[str, MessageDefinitionTuple]] = {
    "R9103": (
        "Constant comparisons on %r would be clearer as a match statement",
        "prefer-match-over-constant-chain",
        (
            "Emitted when every branch of an if/elif chain compares one "
            "subject with constants, enumeration members, or literals by "
            "equality or membership. A match statement over an enumeration "
            "of the accepted values states the dispatch directly."
        ),
    ),
}


def _is_constant_like(node: nodes.NodeNG | bases.Proxy) -> bool:
    """Return whether *node* denotes a constant, enum member, or literal.

    Accepts literal constants, attribute references shaped like
    enumeration members (an upper-case attribute or an attribute of a
    capitalized name), and upper-case module-level constant names.

    Examples
    --------
    ``"reset"``, ``-1``, ``Colour.RED``, and ``MAX_RETRIES`` all
    qualify; ``config.mode`` and ``other`` do not.
    """
    match node:
        case nodes.Const():
            return True
        case nodes.UnaryOp(operand=nodes.Const()):
            return True
        case nodes.Attribute(attrname=attrname, expr=expr):
            if attrname.isupper():
                return True
            return isinstance(expr, nodes.Name) and expr.name[:1].isupper()
        case nodes.Name(name=name):
            return name.isupper()
        case _:
            return False


def _is_constant_container(node: nodes.NodeNG) -> bool:
    """Return whether *node* is a literal collection of constants.

    Examples
    --------
    ``{"a", "b"}`` and ``(Colour.RED, Colour.AMBER)`` qualify; a name
    bound to a collection elsewhere does not.
    """
    match node:
        case nodes.Set(elts=elts) | nodes.Tuple(elts=elts) | nodes.List(elts=elts):
            return all(_is_constant_like(element) for element in elts)
        case _:
            return False


def _equality_subject(left: nodes.NodeNG, right: nodes.NodeNG) -> str | None:
    """Return the non-constant side of an equality with a constant.

    Examples
    --------
    ``state == "idle"`` and ``"idle" == state`` both return ``"state"``;
    ``state == other`` returns ``None``.
    """
    left_constant = _is_constant_like(left)
    right_constant = _is_constant_like(right)
    if left_constant == right_constant:
        return None
    return left.as_string() if right_constant else right.as_string()


def _comparison_subject(test: nodes.NodeNG) -> str | None:
    """Return the subject when *test* only compares it with constants.

    Eligible tests are an equality against a constant, a membership test
    against a literal collection of constants, or an ``or`` combination
    of such comparisons on a single subject.

    Examples
    --------
    ``state == "idle" or state in {"stopping", "stopped"}`` returns
    ``"state"``; ``state == compute()`` returns ``None``.
    """
    match test:
        case nodes.BoolOp(op="or", values=values):
            subjects = {_comparison_subject(value) for value in values}
            if len(subjects) == 1 and None not in subjects:
                return subjects.pop()
            return None
        case nodes.Compare(left=left, ops=[(operator, right)]):
            if operator == "==":
                return _equality_subject(left, right)
            if operator == "in" and _is_constant_container(right):
                return left.as_string()
            return None
        case _:
            return None


class ConstantChainChecker(checkers.BaseChecker):
    """Report constant-comparison chains that should use ``match``/``case``.

    Examples
    --------
    Enable alongside the plugin and run pylint as usual::

        pylint --load-plugins=df12_python_lints my_module.py
    """

    name = "df12-constant-chain"
    msgs = _MSGS

    def visit_if(self, node: nodes.If) -> None:
        """Check the chain rooted at *node* for constant-only dispatch.

        Examples
        --------
        Invoked by pylint's AST walker for every ``if`` statement.
        """
        if is_elif_branch(node):
            return
        tests = elif_chain_tests(node)
        if len(tests) < _MIN_CHAIN_TESTS:
            return
        subjects = {_comparison_subject(test) for test in tests}
        if len(subjects) == 1 and None not in subjects:
            self.add_message(
                "prefer-match-over-constant-chain",
                node=node,
                args=(subjects.pop(),),
            )
