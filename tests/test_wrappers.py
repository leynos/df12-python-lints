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

    def test_ignores_reordered_arguments(self) -> None:
        """Reordering arguments adapts the call rather than forwarding."""
        node = _extract_function(
            """
            def swap(self, first, second):  #@
                return self._target.swap(second, first)
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_repeated_argument(self) -> None:
        """Passing one parameter twice adapts the call."""
        node = _extract_function(
            """
            def pair(self, value):  #@
                return self._target.pair(value, value)
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_omitted_parameter(self) -> None:
        """Dropping a parameter filters the call, which is behaviour."""
        node = _extract_function(
            """
            def send(self, message, priority):  #@
                return self._client.send(message)
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


def _alias_message(
    node: astroid.nodes.FunctionDef, target: str
) -> testutils.MessageTest:
    """Build the expected message for an alias report on *node*."""
    return testutils.MessageTest(
        "trivial-alias-wrapper", node=node, args=(node.name, target)
    )


class TestTrivialAliasWrapper(testutils.CheckerTestCase):
    """Exercise detection of bare-name argument-forwarding wrappers."""

    CHECKER_CLASS = TrivialWrapperChecker

    def test_flags_forwarding_to_module_function(self) -> None:
        """Forwarding every argument to a module function is reported."""
        node = _extract_function(
            """
            def bar(value):
                return value * 2

            def foo(qux):  #@
                return bar(qux)
            """
        )
        with self.assertAddsMessages(_alias_message(node, "bar"), ignore_position=True):
            self.checker.visit_functiondef(node)

    def test_flags_forwarding_to_imported_function(self) -> None:
        """Forwarding to a from-imported function is reported."""
        node = _extract_function(
            """
            from json import dumps

            def serialize(payload):  #@
                return dumps(payload)
            """
        )
        with self.assertAddsMessages(
            _alias_message(node, "dumps"), ignore_position=True
        ):
            self.checker.visit_functiondef(node)

    def test_ignores_call_through_parameter(self) -> None:
        """A combinator calling through a parameter is higher-order code."""
        node = _extract_function(
            """
            def apply(handler, value):  #@
                return handler(value)
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_class_constructor_call(self) -> None:
        """A factory calling a class constructor keeps a deliberate name."""
        node = _extract_function(
            """
            class Config:
                pass

            def make_config(source):  #@
                return Config(source)
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_imported_class_constructor(self) -> None:
        """An imported constructor is a factory, matching the local rule."""
        node = _extract_function(
            """
            from collections import OrderedDict

            def make_mapping(items):  #@
                return OrderedDict(items)
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_builtin_call(self) -> None:
        """Wrapping a builtin is a named conversion, not an alias."""
        node = _extract_function(
            """
            def stringify(value):  #@
                return str(value)
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_transformed_arguments(self) -> None:
        """Transforming an argument before forwarding adds behaviour."""
        node = _extract_function(
            """
            def bar(value):
                return value * 2

            def foo(qux):  #@
                return bar(qux.strip())
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_supplied_extra_argument(self) -> None:
        """Supplying a constant argument specializes the call."""
        node = _extract_function(
            """
            def bar(value, retries):
                return (value, retries)

            def foo(qux):  #@
                return bar(qux, 3)
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)

    def test_ignores_call_on_computed_receiver(self) -> None:
        """A call through a computed expression has no forwarding root."""
        node = _extract_function(
            """
            def combine(self, x):  #@
                return (self.a + self.b).send(x)
            """
        )
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)
