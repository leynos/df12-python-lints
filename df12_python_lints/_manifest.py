"""Comment-preserving ``pyproject.toml`` edits under one shared lock protocol.

``df12-duplication allow`` and ``df12-skylos allow`` both rewrite a
consumer's manifest. They share this single read-modify-write transaction so
concurrent runs of either command cannot lose each other's changes.

Protocol
--------
* The target is resolved to its real path first, so a symlinked manifest is
  edited in place (the link survives) and every spelling of one file takes
  the same lock.
* An advisory ``flock`` is taken on a sidecar ``.<name>.df12.lock`` beside the
  real file. The lock file is never unlinked or replaced, so its identity is
  stable while the manifest itself is atomically replaced.
* The lock is held across read, validation, edit and replacement. An edit
  that raises, or reports no change, writes nothing.
* The lock coordinates participating df12 commands only; it does not stop an
  arbitrary editor.

Platform boundary: advisory locking uses ``fcntl`` (Linux and macOS).
Elsewhere the transaction refuses to run rather than edit without a lock.
"""

from __future__ import annotations

import contextlib
import typing as typ

from ._atomic import atomic_replace
from ._errors import ToolConfigError, ToolExecutionError, ToolPlatformError

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    import tomlkit

_EXTRA_HINT = (
    "install the optional dependency with `pip install df12-python-lints[{extra}]`"
)


def lock_path_for(target: pathlib.Path) -> pathlib.Path:
    """Return the sidecar lock path for a resolved manifest.

    Examples
    --------
    >>> lock_path_for(pathlib.Path("/repo/pyproject.toml"))
    PosixPath('/repo/.pyproject.toml.df12.lock')
    """
    return target.with_name(f".{target.name}.df12.lock")


@contextlib.contextmanager
def manifest_lock(target: pathlib.Path) -> cabc.Iterator[None]:
    """Hold the exclusive advisory lock for one resolved manifest.

    Parameters
    ----------
    target : pathlib.Path
        The manifest's real path (see :func:`resolve_manifest`).

    Raises
    ------
    ToolPlatformError
        If the platform has no ``fcntl`` advisory locks.
    """
    try:
        import fcntl
    except ImportError as error:
        msg = "editing a manifest needs POSIX advisory locks (Linux or macOS)"
        raise ToolPlatformError(msg) from error
    lock_path = lock_path_for(target)
    try:
        lock = lock_path.open("a+", encoding="utf-8")
    except OSError as error:
        msg = f"cannot open the manifest lock {lock_path}: {error}"
        raise ToolExecutionError(msg) from error
    with lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        except OSError as error:
            msg = f"cannot lock {lock_path}: {error}"
            raise ToolExecutionError(msg) from error
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def resolve_manifest(path: pathlib.Path) -> pathlib.Path:
    """Return the real path of an existing manifest.

    Raises
    ------
    ToolConfigError
        If the manifest does not exist or is not a regular file.
    """
    try:
        target = path.resolve(strict=True)
    except OSError as error:
        msg = f"cannot read {path}: {error}"
        raise ToolConfigError(msg) from error
    if not target.is_file():
        msg = f"{path} is not a regular file"
        raise ToolConfigError(msg)
    return target


def _load_tomlkit(extra: str) -> typ.Any:  # ruff: ignore[any-type] - optional dependency loaded lazily.
    """Import ``tomlkit`` or fail with the actionable install hint for ``extra``."""
    try:
        import tomlkit
    except ImportError as error:
        hint = _EXTRA_HINT.format(extra=extra)
        msg = f"tomlkit is required to edit pyproject.toml: {hint}"
        raise ToolExecutionError(msg) from error
    return tomlkit


def edit_manifest(
    path: pathlib.Path,
    edit: cabc.Callable[[tomlkit.TOMLDocument], bool],
    *,
    extra: str,
) -> bool:
    """Run one locked read-modify-write transaction on a manifest.

    Parameters
    ----------
    path : pathlib.Path
        The manifest to edit; symlinks are followed.
    edit : collections.abc.Callable[[tomlkit.TOMLDocument], bool]
        Mutates the parsed document and returns whether anything changed.
        It may raise :class:`ToolConfigError` to reject the request; nothing
        is written in that case.
    extra : str
        Name of the optional extra that provides ``tomlkit``, used in the
        install hint when it is missing.

    Returns
    -------
    bool
        ``True`` if the file was rewritten.

    Raises
    ------
    ToolConfigError
        If the manifest cannot be read or parsed, or ``edit`` rejects it.
    ToolExecutionError
        If ``tomlkit`` is not installed or the replacement fails.
    """
    tomlkit_module = _load_tomlkit(extra)
    target = resolve_manifest(path)
    with manifest_lock(target):
        try:
            document = tomlkit_module.parse(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as error:
            msg = f"cannot read {path}: {error}"
            raise ToolConfigError(msg) from error
        except tomlkit_module.exceptions.ParseError as error:
            msg = f"cannot parse {path}: {error}"
            raise ToolConfigError(msg) from error
        if not edit(document):
            return False
        try:
            atomic_replace(target, tomlkit_module.dumps(document).encode("utf-8"))
        except OSError as error:
            msg = f"cannot write {path}: {error}"
            raise ToolExecutionError(msg) from error
    return True
