"""Shared fixtures for the test suite."""

from __future__ import annotations

import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib


@pytest.fixture
def write_snapshot() -> cabc.Callable[[pathlib.Path, str], pathlib.Path]:
    """Return a factory writing snapshot content and yielding its path."""

    def _write(directory: pathlib.Path, content: str) -> pathlib.Path:
        """Write *content* as a snapshot file and return its path."""
        snapshot_dir = directory / "__snapshots__"
        snapshot_dir.mkdir()
        path = snapshot_dir / "test_demo.ambr"
        path.write_text(content, encoding="utf-8")
        return path

    return _write
