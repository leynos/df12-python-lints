"""Tests for the trivial wrapper checker."""

from __future__ import annotations

import typing as typ

import astroid
from pylint import testutils

from df12_python_lints.wrappers import TrivialWrapperChecker


def _extract_function(code: str) -> astroid.nodes.FunctionDef:
    """Extract the ``#@``-marked function definition from *code*."""
    return typ.cast("astroid.nodes.FunctionDef", astroid.extract_node(code))


def _wrapper_message(
    node: astroid.nodes.FunctionDef,
) -> testutils.MessageTest:
    """Build the expected message for a wrapper report on *node*."""
    return testutils.MessageTest(
        "trivial-attribute-wrapper", node=node, args=(node.name,)
    )


class TestTrivialWrapperChecker(testutils.CheckerTestCase):
    """Exercise detection of attribute and call forwarding wrappers."""

    CHECKER_CLASS = TrivialWrapperChecker

    def test_flags_attribute_forwarding(self) -> None:
        """A body returning a parameter attribute chain is reported."""
        node = _extract_function(
            """
            def get_name(user):  #@
                return user.profile.name
            """
        )
        with self.assertAddsMessages(_wrapper_message(node), ignore_position=True):
            self.checker.visit_functiondef(node)

    def test_flags_attribute_forwarding_with_docstring(self) -> None:
        """A docstring does not disguise a trivial wrapper."""
        node = _extract_function(
            '''
            def get_name(user):  #@
                """Return the user name."""
                return user.name
            '''
        )
        with self.assertAddsMessages(_wrapper_message(node), ignore_position=True):
            self.checker.visit_functiondef(node)

    def test_flags_proxied_call(self) -> None:
        """A call through a parameter attribute forwarding parameters."""
        node = _extract_function(
            """
            def send(self, message):  #@
                return self._client.send(message)
            """
        )
        with self.assertAddsMessages(_wrapper_message(node), ignore_position=True):
            self.checker.visit_functiondef(node)

    def test_flags_proxied_call_without_return(self) -> None:
        """A statement-only proxied call is still a trivial wrapper."""
        node = _extract_function(
            """
            def close(self):  #@
                self._connection.close()
            """
        )
        with self.assertAddsMessages(_wrapper_message(node), ignore_position=True):
            self.checker.visit_functiondef(node)

    def test_flags_starred_passthrough_call(self) -> None:
        """Starred and keyword pass-through arguments still forward."""
        node = _extract_function(
            """
            def call(self, *args, **kwargs):  #@
                return self._delegate.call(*args, **kwargs)
            """
        )
        with self.assertAddsMessages(_wrapper_message(node), ignore_position=True):
            self.checker.visit_functiondef(node)

    def test_ignores_decorated_function(self) -> None:
        """A decorator marks the forwarding as deliberate."""
        node = _extract_function(
            """
            @property
            def name(self):  #@
                return self._name
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_call_with_new_arguments(self) -> None:
        """Supplying a constant argument adds behaviour."""
        node = _extract_function(
            """
            def send(self, message):  #@
                return self._client.send(message, retries=3)
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_transformed_argument(self) -> None:
        """Transforming an argument before forwarding adds behaviour."""
        node = _extract_function(
            """
            def send(self, message):  #@
                return self._client.send(message.strip())
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_multi_statement_body(self) -> None:
        """More than one statement means the function does real work."""
        node = _extract_function(
            """
            def get_name(user):  #@
                name = user.name
                return name
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_attribute_of_non_parameter(self) -> None:
        """Attribute access on a global is not parameter forwarding."""
        node = _extract_function(
            """
            def get_default():  #@
                return settings.default
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_identity_return(self) -> None:
        """Returning a parameter unchanged involves no attribute access."""
        node = _extract_function(
            """
            def identity(value):  #@
                return value
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)
