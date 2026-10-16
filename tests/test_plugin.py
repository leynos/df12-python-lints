"""Tests for the plugin registration entry point."""

from __future__ import annotations

import typing as typ

from pylint.lint import PyLinter

import df12_python_lints

if typ.TYPE_CHECKING:
    from pylint.checkers.base_checker import BaseChecker


def _plugin_checkers(linter: PyLinter) -> list[BaseChecker]:
    """Return the df12 plugin checkers registered on *linter*."""
    return [
        checker
        for checker in linter.get_checkers()
        if type(checker).__module__.startswith("df12_python_lints")
    ]


def test_register_adds_all_checkers() -> None:
    """Registering the plugin exposes all df12 checkers."""
    linter = PyLinter()
    df12_python_lints.register(linter)
    names = {checker.name for checker in linter.get_checkers()}
    expected = {
        "df12-match-dispatch",
        "df12-assert-message",
        "df12-constant-chain",
        "df12-dataclass-slots",
        "df12-trivial-wrapper",
        "df12-reexport-assignment",
        "df12-suppression-comments",
        "df12-snapshot-asserts",
        "df12-type-aliases",
        "df12-future-annotations",
    }
    missing = expected - names
    assert not missing, f"checkers failed to register: {sorted(missing)}"


def test_register_is_idempotent_for_exact_checker_types() -> None:
    """Repeated registration preserves each checker instance."""
    linter = PyLinter()
    df12_python_lints.register(linter)
    before = _plugin_checkers(linter)

    df12_python_lints.register(linter)
    after = _plugin_checkers(linter)

    assert len(before) == 10, "initial registration should create ten plugin checkers"
    assert len(after) == 10, "repeated registration should leave ten plugin checkers"
    for checker in after:
        assert sum(type(candidate) is type(checker) for candidate in after) == 1, (
            "each exact checker type should occur once after repeated registration"
        )
        previous = [
            candidate for candidate in before if type(candidate) is type(checker)
        ]
        assert len(previous) == 1, "each exact type should have one prior instance"
        assert previous[0] is checker, "repeated registration should preserve identity"


def test_forced_plugin_reload_preserves_checker_instances() -> None:
    """Cover workers' forced plugin reload on an already-populated linter.

    Pylint calls ``load_plugin_modules(..., force=True)`` in worker processes.
    """
    linter = PyLinter()
    linter.load_plugin_modules(["df12_python_lints"])
    before = _plugin_checkers(linter)

    linter.load_plugin_modules(linter._dynamic_plugins, force=True)
    after = _plugin_checkers(linter)

    assert len(before) == 10, "plugin loading should register ten checkers"
    assert len(after) == 10, "forced reload should not duplicate plugin checkers"
    for checker in before:
        current = [candidate for candidate in after if type(candidate) is type(checker)]
        assert len(current) == 1, "forced reload should retain one checker per type"
        assert current[0] is checker, "forced reload should preserve checker identity"


def test_register_preserves_a_manually_registered_checker() -> None:
    """Registration fills missing types without replacing existing checkers."""
    linter = PyLinter()
    manual_checker = df12_python_lints.AssertMessageChecker(linter)
    linter.register_checker(manual_checker)

    df12_python_lints.register(linter)
    checkers = _plugin_checkers(linter)

    assert len(checkers) == 10, "manual registration should still produce ten checkers"
    assert sum(checker is manual_checker for checker in checkers) == 1, (
        "registration should preserve the manually registered checker"
    )
    for checker in checkers:
        assert sum(type(candidate) is type(checker) for candidate in checkers) == 1, (
            "manual registration should not duplicate exact checker types"
        )


def test_independent_linters_receive_independent_checkers() -> None:
    """Each linter owns its own set of plugin checker instances."""
    first_linter = PyLinter()
    second_linter = PyLinter()
    df12_python_lints.register(first_linter)
    df12_python_lints.register(second_linter)
    first_checkers = _plugin_checkers(first_linter)
    second_checkers = _plugin_checkers(second_linter)

    assert len(first_checkers) == 10, "first linter should own ten plugin checkers"
    assert len(second_checkers) == 10, "second linter should own ten plugin checkers"
    for first_checker in first_checkers:
        assert all(
            first_checker is not second_checker for second_checker in second_checkers
        ), "independent linters should not share checker instances"
        assert first_checker.linter is first_linter, (
            "checker should reference first linter"
        )
    for second_checker in second_checkers:
        assert second_checker.linter is second_linter, (
            "checker should reference second linter"
        )


def test_message_ids_remain_unique_after_r9111_integration() -> None:
    """Dataclass slots owns R9111 and type statements move to R9112."""
    linter = PyLinter()
    df12_python_lints.register(linter)
    message_ids = [definition.msgid for definition in linter.msgs_store.messages]
    assert len(message_ids) == len(set(message_ids)), (
        f"duplicate message identifiers: {message_ids!r}"
    )
    by_symbol = {
        definition.symbol: definition.msgid
        for definition in linter.msgs_store.messages
        if definition.symbol in {"prefer-slots-for-dataclass", "prefer-type-statement"}
    }
    expected = {
        "prefer-slots-for-dataclass": "R9111",
        "prefer-type-statement": "R9112",
    }
    assert by_symbol == expected, f"unexpected message identifiers: {by_symbol!r}"
