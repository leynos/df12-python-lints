"""Tests for the plugin registration entry point."""

from __future__ import annotations

from pylint.lint import PyLinter

import df12_python_lints


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


def test_message_ids_remain_unique_after_r9111_integration() -> None:
    """Dataclass slots owns R9111 and type statements move to R9112."""
    linter = PyLinter()
    df12_python_lints.register(linter)
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
