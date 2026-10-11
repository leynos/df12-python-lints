"""Explicit runtime context for the duplication commands.

The CLI builds one :class:`RunContext` and passes it to every operation. The
target checkout is never inferred from this package's location, the process
working directory is never changed, and relative paths resolve against the
selected repository.
"""

from __future__ import annotations

import collections.abc as cabc
import dataclasses as dc
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - runs one verified, repository-selected binary without a shell.

from df12_python_lints._errors import ToolConfigError, ToolExecutionError

DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_BINARY_RELATIVE = pathlib.PurePosixPath(".tools/nose/nose")


@dc.dataclass(frozen=True, slots=True)
class CommandResult:
    """The outcome of one subprocess: its status and decoded output."""

    returncode: int
    stdout: str
    stderr: str


type CommandRunner = cabc.Callable[
    [cabc.Sequence[str], pathlib.Path, cabc.Mapping[str, str], int], CommandResult
]


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


@dc.dataclass(frozen=True, slots=True)
class RunContext:
    """Everything an operation needs to act on one target repository.

    Attributes
    ----------
    repository : pathlib.Path
        Resolved absolute path of the target checkout.
    environment : collections.abc.Mapping[str, str]
        Environment handed to subprocesses and used for ``PATH`` lookup.
    binary_override : pathlib.Path | None
        Explicit detector binary, already resolved against ``repository``.
    runner : CommandRunner
        Subprocess boundary; replaced in tests.
    timeout_seconds : int
        Bound on each detector invocation.
    """

    repository: pathlib.Path
    environment: cabc.Mapping[str, str]
    binary_override: pathlib.Path | None = None
    runner: CommandRunner = run_command
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @property
    def pyproject(self) -> pathlib.Path:
        """The target repository's ``pyproject.toml``."""
        return self.repository / "pyproject.toml"

    @property
    def default_binary(self) -> pathlib.Path:
        """The repository-local install location, ``.tools/nose/nose``."""
        return self.repository.joinpath(*DEFAULT_BINARY_RELATIVE.parts)


@dc.dataclass(frozen=True, slots=True)
class ContextOptions:
    """Tunables for :func:`build_context` that rarely change.

    Attributes
    ----------
    timeout_seconds : int
        Bound on each detector invocation.
    runner : CommandRunner
        Subprocess boundary; replaced in tests.
    """

    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    runner: CommandRunner = run_command


def build_context(
    *,
    repository: str | None,
    binary: str | None,
    environment: cabc.Mapping[str, str],
    options: ContextOptions = ContextOptions(),  # ruff: ignore[function-call-in-default-argument] - frozen, shared default.
) -> RunContext:
    """Construct the run context at the CLI boundary.

    Parameters
    ----------
    repository : str | None
        ``--repository`` value; the invocation directory when ``None``.
    binary : str | None
        ``--binary`` value, else ``NOSE_BIN`` from ``environment``; relative
        paths resolve against the repository, not the invocation directory.
    environment : collections.abc.Mapping[str, str]
        Process environment, copied into the context.
    options : ContextOptions
        Timeout and subprocess boundary.

    Raises
    ------
    ToolConfigError
        If the repository directory or its ``pyproject.toml`` is missing.
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
    override = binary or environment.get("NOSE_BIN") or None
    return RunContext(
        repository=resolved,
        environment=dict(environment),
        binary_override=None if override is None else (resolved / override).resolve(),
        runner=options.runner,
        timeout_seconds=options.timeout_seconds,
    )
