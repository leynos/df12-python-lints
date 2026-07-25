"""Tests for the trivial wrapper checker."""

from __future__ import annotations

import typing as typ

import astroid
from pylint import testutils

from df12_python_lints.wrappers import TrivialWrapperChecker, _forwarded_names


def _extract_function(code: str) -> astroid.nodes.FunctionDef:
    """Extract the ``#@``-marked function definition from *code*."""
    return typ.cast("astroid.nodes.FunctionDef", astroid.extract_node(code))


def _extract_call(code: str) -> astroid.nodes.Call:
    """Extract the ``#@``-marked call expression from *code*."""
    return typ.cast("astroid.nodes.Call", astroid.extract_node(code))


def _wrapper_message(
    node: astroid.nodes.FunctionDef,
) -> testutils.MessageTest:
    """Build the expected message for a wrapper report on *node*."""
    return testutils.MessageTest(
        "trivial-attribute-wrapper", node=node, args=(node.name,)
    )


def _alias_message(
    node: astroid.nodes.FunctionDef, target: str
) -> testutils.MessageTest:
    """Build the expected message for an alias report on *node*."""
    return testutils.MessageTest(
        "trivial-alias-wrapper", node=node, args=(node.name, target)
    )


class _TrivialWrapperCheckerTestCase(testutils.CheckerTestCase):
    """Shared fixture and assertion helpers for the wrapper checkers."""

    CHECKER_CLASS = TrivialWrapperChecker

    def _assert_attribute_wrapper_reported(self, code: str) -> None:
        """Assert the marked function in *code* draws trivial-attribute-wrapper."""
        node = _extract_function(code)
        with self.assertAddsMessages(_wrapper_message(node), ignore_position=True):
            self.checker.visit_functiondef(node)

    def _assert_alias_wrapper_reported(self, code: str, target: str) -> None:
        """Assert the marked function draws trivial-alias-wrapper for *target*."""
        node = _extract_function(code)
        with self.assertAddsMessages(
            _alias_message(node, target), ignore_position=True
        ):
            self.checker.visit_functiondef(node)

    def _assert_no_wrapper_diagnostic(self, code: str) -> None:
        """Assert the marked function in *code* draws no diagnostics."""
        node = _extract_function(code)
        with self.assertNoMessages():
            self.checker.visit_functiondef(node)


class TestTrivialWrapperChecker(_TrivialWrapperCheckerTestCase):
    """Exercise detection of attribute and call forwarding wrappers."""

    def test_flags_attribute_forwarding(self) -> None:
        """A body returning a parameter attribute chain is reported."""
        self._assert_attribute_wrapper_reported(
            """
            def get_name(user):  #@
                return user.profile.name
            """
        )

    def test_flags_attribute_forwarding_with_docstring(self) -> None:
        """A docstring does not disguise a trivial wrapper."""
        self._assert_attribute_wrapper_reported(
            '''
            def get_name(user):  #@
                """Return the user name."""
                return user.name
            '''
        )

    def test_flags_proxied_call(self) -> None:
        """A call through a parameter attribute forwarding parameters."""
        self._assert_attribute_wrapper_reported(
            """
            def send(self, message):  #@
                return self._client.send(message)
            """
        )

    def test_flags_proxied_call_without_return(self) -> None:
        """A statement-only proxied call is still a trivial wrapper."""
        self._assert_attribute_wrapper_reported(
            """
            def close(self):  #@
                self._connection.close()
            """
        )

    def test_flags_starred_passthrough_call(self) -> None:
        """Starred and keyword pass-through arguments still forward."""
        self._assert_attribute_wrapper_reported(
            """
            def call(self, *args, **kwargs):  #@
                return self._delegate.call(*args, **kwargs)
            """
        )

    def test_ignores_decorated_function(self) -> None:
        """A decorator marks the forwarding as deliberate."""
        self._assert_no_wrapper_diagnostic(
            """
            @property
            def name(self):  #@
                return self._name
            """
        )

    def test_ignores_call_with_new_arguments(self) -> None:
        """Supplying a constant argument adds behaviour."""
        self._assert_no_wrapper_diagnostic(
            """
            def send(self, message):  #@
                return self._client.send(message, retries=3)
            """
        )

    def test_ignores_transformed_argument(self) -> None:
        """Transforming an argument before forwarding adds behaviour."""
        self._assert_no_wrapper_diagnostic(
            """
            def send(self, message):  #@
                return self._client.send(message.strip())
            """
        )

    def test_ignores_reordered_arguments(self) -> None:
        """Reordering arguments adapts the call rather than forwarding."""
        self._assert_no_wrapper_diagnostic(
            """
            def swap(self, first, second):  #@
                return self._target.swap(second, first)
            """
        )

    def test_ignores_repeated_argument(self) -> None:
        """Passing one parameter twice adapts the call."""
        self._assert_no_wrapper_diagnostic(
            """
            def pair(self, value):  #@
                return self._target.pair(value, value)
            """
        )

    def test_ignores_omitted_parameter(self) -> None:
        """Dropping a parameter filters the call, which is behaviour."""
        self._assert_no_wrapper_diagnostic(
            """
            def send(self, message, priority):  #@
                return self._client.send(message)
            """
        )

    def test_ignores_multi_statement_body(self) -> None:
        """More than one statement means the function does real work."""
        self._assert_no_wrapper_diagnostic(
            """
            def get_name(user):  #@
                name = user.name
                return name
            """
        )

    def test_ignores_attribute_of_non_parameter(self) -> None:
        """Attribute access on a global is not parameter forwarding."""
        self._assert_no_wrapper_diagnostic(
            """
            def get_default():  #@
                return settings.default
            """
        )

    def test_ignores_identity_return(self) -> None:
        """Returning a parameter unchanged involves no attribute access."""
        self._assert_no_wrapper_diagnostic(
            """
            def identity(value):  #@
                return value
            """
        )


class TestTrivialAliasWrapper(_TrivialWrapperCheckerTestCase):
    """Exercise detection of bare-name argument-forwarding wrappers."""

    def test_flags_forwarding_to_module_function(self) -> None:
        """Forwarding every argument to a module function is reported."""
        self._assert_alias_wrapper_reported(
            """
            def bar(value):
                return value * 2

            def foo(qux):  #@
                return bar(qux)
            """,
            "bar",
        )

    def test_flags_forwarding_to_imported_function(self) -> None:
        """Forwarding to a from-imported function is reported."""
        self._assert_alias_wrapper_reported(
            """
            from json import dumps

            def serialize(payload):  #@
                return dumps(payload)
            """,
            "dumps",
        )

    def test_ignores_call_through_parameter(self) -> None:
        """A combinator calling through a parameter is higher-order code."""
        self._assert_no_wrapper_diagnostic(
            """
            def apply(handler, value):  #@
                return handler(value)
            """
        )

    def test_ignores_class_constructor_call(self) -> None:
        """A factory calling a class constructor keeps a deliberate name."""
        self._assert_no_wrapper_diagnostic(
            """
            class Config:
                pass

            def make_config(source):  #@
                return Config(source)
            """
        )

    def test_ignores_imported_class_constructor(self) -> None:
        """An imported constructor is a factory, matching the local rule."""
        self._assert_no_wrapper_diagnostic(
            """
            from collections import OrderedDict

            def make_mapping(items):  #@
                return OrderedDict(items)
            """
        )

    def test_ignores_builtin_call(self) -> None:
        """Wrapping a builtin is a named conversion, not an alias."""
        self._assert_no_wrapper_diagnostic(
            """
            def stringify(value):  #@
                return str(value)
            """
        )

    def test_ignores_transformed_arguments(self) -> None:
        """Transforming an argument before forwarding adds behaviour."""
        self._assert_no_wrapper_diagnostic(
            """
            def bar(value):
                return value * 2

            def foo(qux):  #@
                return bar(qux.strip())
            """
        )

    def test_ignores_supplied_extra_argument(self) -> None:
        """Supplying a constant argument specializes the call."""
        self._assert_no_wrapper_diagnostic(
            """
            def bar(value, retries):
                return (value, retries)

            def foo(qux):  #@
                return bar(qux, 3)
            """
        )

    def test_ignores_call_on_computed_receiver(self) -> None:
        """A call through a computed expression has no forwarding root."""
        self._assert_no_wrapper_diagnostic(
            """
            def combine(self, x):  #@
                return (self.a + self.b).send(x)
            """
        )


class TestForwardedNames:
    """Exercise the extracted argument-forwarding helper directly."""

    def test_keeps_order_and_multiplicity(self) -> None:
        """Bare and starred names are returned in order, duplicates kept."""
        call = _extract_call("target(a, *b, a)  #@")
        assert _forwarded_names(call.args) == ("a", "b", "a")

    def test_returns_none_for_a_transformed_argument(self) -> None:
        """One transformed operand rejects the whole argument list."""
        call = _extract_call("target(a, b.strip())  #@")
        assert _forwarded_names(call.args) is None

    def test_returns_none_for_a_constant_argument(self) -> None:
        """One constant operand rejects the whole argument list."""
        call = _extract_call("target(a, 3)  #@")
        assert _forwarded_names(call.args) is None

    def test_forwards_keyword_value_names(self) -> None:
        """Keyword value operands forward their names when unchanged."""
        call = _extract_call("target(x=a, y=b)  #@")
        names = _forwarded_names(keyword.value for keyword in call.keywords)
        assert names == ("a", "b")

    def test_empty_arguments_yield_empty_tuple(self) -> None:
        """No operands forward no names, distinct from a rejection."""
        call = _extract_call("target()  #@")
        assert _forwarded_names(call.args) == ()
