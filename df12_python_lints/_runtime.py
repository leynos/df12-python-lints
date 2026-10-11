"""Subprocess boundary and repository resolution shared by the commands.

Both ``df12-duplication`` and ``df12-skylos`` run an external backend against a
selected checkout. They share the same rules: an argument vector without a
shell, an explicit working directory, a bounded run, and a repository that is
chosen by the caller rather than inferred from where this package lives.
"""

from __future__ import annotations

import collections.abc as cabc
import dataclasses as dc
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - runs one verified backend without a shell.
import typing as typ

from ._errors import ToolConfigError, ToolExecutionError

DEFAULT_TIMEOUT_SECONDS = 120


@dc.dataclass(frozen=True, slots=True)
class CommandResult:
    """The outcome of one subprocess: its status and decoded output."""

    returncode: int
    stdout: str
    stderr: str


type CommandRunner = cabc.Callable[
    [cabc.Sequence[str], pathlib.Path, cabc.Mapping[str, str], int], CommandResult
]


class Streams(typ.NamedTuple):
    """Where a command writes its report and its diagnostics."""

    out: typ.TextIO
    err: typ.TextIO


def run_command(
    command: cabc.Sequence[str],
    cwd: pathlib.Path,
    environment: cabc.Mapping[str, str],
    timeout: int,
) -> CommandResult:
    """Run one argument vector without a shell, bounded by ``timeout`` seconds.

    Raises
    ------
    ToolExecutionError
        If the program cannot start or exceeds the timeout.
    """
    try:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argument vector, no shell.
            list(command),
            cwd=cwd,
            env=dict(environment),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        msg = f"{command[0]} timed out after {timeout} seconds"
        raise ToolExecutionError(msg) from error
    except OSError as error:
        msg = f"cannot run {command[0]}: {error}"
        raise ToolExecutionError(msg) from error
    return CommandResult(result.returncode, result.stdout, result.stderr)


def resolve_repository(repository: str | None) -> pathlib.Path:
    """Resolve the target checkout chosen by ``--repository``.

    Parameters
    ----------
    repository : str | None
        The ``--repository`` value; the invocation directory when ``None``.

    Returns
    -------
    pathlib.Path
        The resolved absolute directory, which holds a ``pyproject.toml``.

    Raises
    ------
    ToolConfigError
        If the directory is inaccessible or has no ``pyproject.toml``.
    """
    root = pathlib.Path(repository) if repository else pathlib.Path.cwd()
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        msg = f"repository {root} is not accessible: {error}"
        raise ToolConfigError(msg) from error
    if not resolved.is_dir() or not (resolved / "pyproject.toml").is_file():
        msg = f"{resolved} is not a repository with a pyproject.toml"
        raise ToolConfigError(msg)
    return resolved
