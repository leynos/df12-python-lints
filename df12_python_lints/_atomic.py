"""Atomic file replacement shared by manifest edits and tool installation."""

from __future__ import annotations

import contextlib
import os
import pathlib
import tempfile
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@contextlib.contextmanager
def _open_directory(directory: pathlib.Path) -> cabc.Iterator[int]:
    """Open a directory descriptor for a scoped ``fsync``.

    Yields
    ------
    int
        The open directory descriptor, closed when the block exits.
    """
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def atomic_replace(
    path: pathlib.Path,
    content: bytes,
    *,
    mode: int | None = None,
) -> None:
    """Replace ``path`` with ``content`` through a synced temporary sibling.

    The temporary file lives in the destination directory so the final
    ``replace`` is a same-filesystem rename. A failure at any step removes
    the temporary file and leaves the original untouched.

    Parameters
    ----------
    path : pathlib.Path
        Destination whose parent directory must exist.
    content : bytes
        Complete replacement contents.
    mode : int | None
        Permission bits for the new file. ``None`` keeps the mode of an
        existing destination and otherwise the temporary file's default.

    Examples
    --------
    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as directory:
    ...     target = pathlib.Path(directory, "a.txt")
    ...     atomic_replace(target, b"hello")
    ...     target.read_bytes()
    b'hello'
    """
    if mode is None and path.exists():
        mode = path.stat().st_mode & 0o7777
    with tempfile.NamedTemporaryFile(
        delete=False, dir=path.parent, prefix=f".{path.name}."
    ) as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = pathlib.Path(stream.name)
    try:
        if mode is not None:
            temporary.chmod(mode)
        temporary.replace(path)
        with _open_directory(path.parent) as descriptor:
            os.fsync(descriptor)
    finally:
        temporary.unlink(missing_ok=True)
