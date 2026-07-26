"""Shared fixtures for the test suite.

The ambrleaks scanner and CLI tests all need syrupy-style ``.ambr``
snapshot files laid out as the scanner expects: a ``__snapshots__``
directory beside the tests containing the snapshot file. The
``write_snapshot`` fixture provides that layout as a small test API, so
individual tests only describe snapshot *content* and never repeat the
directory plumbing. Request the fixture by name and call the returned
factory with a base directory (usually ``tmp_path``) and the snapshot
text.
"""

from __future__ import annotations

import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib


@pytest.fixture
def write_snapshot() -> cabc.Callable[[pathlib.Path, str], pathlib.Path]:
    r"""Return a factory that writes a snapshot file into a directory.

    The factory creates a ``__snapshots__`` subdirectory beneath the
    given base directory (which must not already contain one) and
    writes the supplied content to a fixed ``test_demo.ambr`` file
    inside it, mirroring syrupy's on-disk layout.

    Returns
    -------
    collections.abc.Callable[[pathlib.Path, str], pathlib.Path]
        A callable taking the base directory and the snapshot text,
        returning the path of the written ``.ambr`` file.

    Examples
    --------
    Seed a snapshot and scan it::

        def test_scan(tmp_path, write_snapshot):
            path = write_snapshot(tmp_path, "# name: test_x\n  'v'\n# ---\n")
            findings = scan_file(path, DEFAULT_RULES, base_dir=tmp_path)
    """

    def _write(directory: pathlib.Path, content: str) -> pathlib.Path:
        """Write *content* as a snapshot file and return its path.

        Parameters
        ----------
        directory : pathlib.Path
            Base directory to receive the ``__snapshots__`` subdirectory.
        content : str
            Snapshot text to write, normally in syrupy's Amber format.

        Returns
        -------
        pathlib.Path
            Path of the written ``__snapshots__/test_demo.ambr`` file.
        """
        snapshot_dir = directory / "__snapshots__"
        snapshot_dir.mkdir()
        path = snapshot_dir / "test_demo.ambr"
        path.write_text(content, encoding="utf-8")
        return path

    return _write
