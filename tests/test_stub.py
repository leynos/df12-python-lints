"""Tests for the generated package stub."""

from __future__ import annotations

import df12_python_lints


def test_hello_returns_stub_greeting() -> None:
    """The generated package exposes a working greeting."""
    assert df12_python_lints.hello() == "hello from Python"
