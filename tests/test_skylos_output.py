"""Exact, reviewable output contracts for the stable ``df12-skylos`` messages.

Each case compares a command's full output and exit status with a golden file
under ``tests/data/skylos_output``. The backend and interpreter are scripted, so
no version or path varies. Regenerate deliberately with
``DF12_UPDATE_GOLDEN=1 pytest tests/test_skylos_output.py`` and review the diff.
"""

from __future__ import annotations

import io
import os
import pathlib
import typing as typ

import pytest
from skylos_support import FakeRunner, context_for, make_repository

from df12_python_lints._runtime import Streams
from df12_python_lints.skylos import commands

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_GOLDEN = pathlib.Path(__file__).parent / "data" / "skylos_output"
_FINDING = "pkg/core.py:5  SKY-U001  unused function: never_called\n"
_CASES: dict[str, cabc.Callable[[pathlib.Path], tuple[int, str, str]]] = {}


def _case(name: str) -> cabc.Callable[[cabc.Callable[..., tuple[int, str, str]]], None]:
    """Register a scenario under ``name``."""

    def register(function: cabc.Callable[..., tuple[int, str, str]]) -> None:
        """Add ``function`` to the scenario table."""
        _CASES[name] = function

    return register


def _run(
    repo: pathlib.Path, operation: str, runner: FakeRunner | None = None
) -> tuple[int, str, str]:
    """Run one operation and return its status and streams."""
    out, err = io.StringIO(), io.StringIO()
    context = context_for(repo, runner)
    code = getattr(commands, operation)(context, Streams(out, err))
    return code, out.getvalue(), err.getvalue()


@_case("validate_ok")
def _validate_ok(tmp_path: pathlib.Path) -> tuple[int, str, str]:
    """Validate a good configuration."""
    return _run(make_repository(tmp_path), "run_validate_config")


@_case("check_clean")
def _check_clean(tmp_path: pathlib.Path) -> tuple[int, str, str]:
    """Run a completed clean gate."""
    return _run(make_repository(tmp_path), "run_check", FakeRunner())


@_case("check_blocking")
def _check_blocking(tmp_path: pathlib.Path) -> tuple[int, str, str]:
    """Run a gate with blocking findings."""
    runner = FakeRunner(stdout=_FINDING, status=1)
    return _run(make_repository(tmp_path), "run_check", runner)


@_case("check_failed_analysis")
def _check_failed(tmp_path: pathlib.Path) -> tuple[int, str, str]:
    """Run a scan that ends with native status 2."""
    runner = FakeRunner(stdout="x.py:1  SKY-ANALYSIS-INCOMPLETE  e\n", status=2)
    return _run(make_repository(tmp_path), "run_check", runner)


@_case("check_empty_root")
def _check_empty_root(tmp_path: pathlib.Path) -> tuple[int, str, str]:
    """Run a scan that exits zero after logging an empty root."""
    runner = FakeRunner(stderr="WARNING - No Python files found in pkg\n")
    return _run(make_repository(tmp_path), "run_check", runner)


@_case("validate_lax_gate")
def _validate_lax(tmp_path: pathlib.Path) -> tuple[int, str, str]:
    """Validate a non-strict gate."""
    repo = make_repository(tmp_path, policy="[tool.skylos.gate]\nstrict = false\n")
    return _run(repo, "run_validate_config")


@pytest.mark.parametrize("name", sorted(_CASES))
def test_output_matches_the_golden_file(name: str, tmp_path: pathlib.Path) -> None:
    """Stdout, stderr and the exit status of each stable verdict are fixed."""
    code, out, err = _CASES[name](tmp_path)
    actual = f"exit: {code}\n--- stdout\n{out}--- stderr\n{err}"
    path = _GOLDEN / f"{name}.txt"
    if os.environ.get("DF12_UPDATE_GOLDEN"):
        path.write_text(actual, encoding="utf-8")
    assert actual == path.read_text(encoding="utf-8"), f"{name} output changed"
