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
        "df12-trivial-wrapper",
        "df12-reexport-assignment",
        "df12-suppression-comments",
    }
    missing = expected - names
    assert not missing, f"checkers failed to register: {sorted(missing)}"
