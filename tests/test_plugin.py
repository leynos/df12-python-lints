"""Tests for the plugin registration entry point."""

from __future__ import annotations

from pylint.lint import PyLinter

import df12_python_lints


def test_register_adds_all_checkers() -> None:
    """Registering the plugin exposes all df12 checkers."""
    linter = PyLinter()
    df12_python_lints.register(linter)
    names = {checker.name for checker in linter.get_checkers()}
    assert "df12-match-dispatch" in names, "dispatch checker must register"
    assert "df12-assert-message" in names, "assert checker must register"
    assert "df12-constant-chain" in names, "constant chain checker must register"
