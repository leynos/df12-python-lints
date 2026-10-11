"""Explicit runtime context for the Skylos commands.

As with the duplication command, the target checkout is chosen by
``--repository`` and never inferred from where this package is installed;
the process working directory is never changed.
"""

from __future__ import annotations

import dataclasses as dc
import typing as typ

from df12_python_lints._runtime import resolve_repository, run_command

from .backend import BackendProbe

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    from df12_python_lints._runtime import CommandRunner

DEFAULT_TIMEOUT_SECONDS = 600


@dc.dataclass(frozen=True, slots=True)
class SkylosContext:
    """Everything an operation needs to act on one target repository.

    Attributes
    ----------
    repository : pathlib.Path
        Resolved absolute path of the target checkout.
    environment : collections.abc.Mapping[str, str]
        Environment handed to the scan subprocess.
    probe : BackendProbe
        The runtime and backend facts; replaced in tests.
    runner : CommandRunner
        Subprocess boundary; replaced in tests.
    timeout_seconds : int
        Bound on the scan.
    """

    repository: pathlib.Path
    environment: cabc.Mapping[str, str]
    probe: BackendProbe
    runner: CommandRunner = run_command
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @property
    def pyproject(self) -> pathlib.Path:
        """The target repository's ``pyproject.toml``."""
        return self.repository / "pyproject.toml"


def build_context(
    *,
    repository: str | None,
    environment: cabc.Mapping[str, str],
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> SkylosContext:
    """Construct the run context at the CLI boundary.

    Raises
    ------
    ToolConfigError
        If the repository directory or its ``pyproject.toml`` is missing.
    """
    return SkylosContext(
        repository=resolve_repository(repository),
        environment=dict(environment),
        probe=BackendProbe.detect(),
        timeout_seconds=timeout_seconds,
    )
