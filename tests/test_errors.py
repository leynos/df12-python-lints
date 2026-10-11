"""Error labelling: configuration problems versus backend failures."""

from __future__ import annotations

import io
import typing as typ

import pytest
from skylos_support import FakeRunner, context_for, make_repository, probe

from df12_python_lints._errors import (
    ToolConfigError,
    ToolExecutionError,
    ToolPlatformError,
    describe,
)
from df12_python_lints._runtime import Streams
from df12_python_lints.skylos import commands

if typ.TYPE_CHECKING:
    import pathlib

    from df12_python_lints.skylos.backend import BackendProbe


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ToolConfigError("bad key"), "configuration error: bad key"),
        (ToolExecutionError("no binary"), "error: no binary"),
        (ToolPlatformError("no flock"), "error: no flock"),
    ],
)
def test_describe_labels_each_error_class(
    error: ToolConfigError, expected: str
) -> None:
    """Execution and platform errors are plain; the base class is configuration."""
    assert describe(error) == expected


class TestCommandLevelLabels:
    """Commands print the label that matches the failure."""

    def _stderr(self, code_and_err: tuple[int, str]) -> str:
        code, err = code_and_err
        assert code == 2, err
        return err

    def _check(
        self, repo: pathlib.Path, runner: FakeRunner, backend_probe: BackendProbe
    ) -> tuple[int, str]:
        err = io.StringIO()
        context = context_for(repo, runner, backend_probe=backend_probe)
        code = commands.run_check(context, Streams(io.StringIO(), err))
        return code, err.getvalue()

    def test_a_missing_backend_is_a_plain_error(self, tmp_path: pathlib.Path) -> None:
        """A backend that is not installed starts with ``error:``."""
        repo = make_repository(tmp_path)
        err = self._stderr(self._check(repo, FakeRunner(), probe(installed=None)))
        assert err.startswith("error: "), err

    def test_a_timeout_is_a_plain_error(self, tmp_path: pathlib.Path) -> None:
        """A scan timeout starts with ``error:``."""
        repo = make_repository(tmp_path)

        def timeout(*_args: object) -> typ.NoReturn:
            """Simulate a scan that exceeds its bound."""
            msg = "python timed out after 1 seconds"
            raise ToolExecutionError(msg)

        context = context_for(repo)
        context = type(context)(
            repository=context.repository,
            environment={},
            probe=context.probe,
            runner=timeout,
        )
        err = io.StringIO()
        assert commands.run_check(context, Streams(io.StringIO(), err)) == 2
        assert err.getvalue().startswith("error: "), err.getvalue()

    def test_invalid_configuration_is_labelled_as_configuration(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A lax gate starts with ``configuration error:``."""
        repo = make_repository(tmp_path, policy="[tool.skylos.gate]\nstrict = false\n")
        err = self._stderr(self._check(repo, FakeRunner(), probe()))
        assert err.startswith("configuration error: "), err
