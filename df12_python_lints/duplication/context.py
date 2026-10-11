"""Explicit runtime context for the duplication commands.

The CLI builds one :class:`RunContext` and passes it to every operation. The
target checkout is never inferred from this package's location, the process
working directory is never changed, and relative paths resolve against the
selected repository.
"""

from __future__ import annotations

import dataclasses as dc
import pathlib
import typing as typ

from df12_python_lints._runtime import (
    DEFAULT_TIMEOUT_SECONDS,
    CommandResult,
    CommandRunner,
    resolve_repository,
    run_command,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

__all__ = ["CommandResult", "CommandRunner", "run_command"]

DEFAULT_BINARY_RELATIVE = pathlib.PurePosixPath(".tools/nose/nose")


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
    resolved = resolve_repository(repository)
    override = binary or environment.get("NOSE_BIN") or None
    return RunContext(
        repository=resolved,
        environment=dict(environment),
        binary_override=None if override is None else (resolved / override).resolve(),
        runner=options.runner,
        timeout_seconds=options.timeout_seconds,
    )
