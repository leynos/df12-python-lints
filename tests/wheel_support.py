"""Build, install and drive the wheel for the installed-command tests.

Each helper uses a clean environment: no ``PYTHONPATH`` and no activated
virtual environment, so nothing leaks in from the checkout under test.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - drives uv and the installed console scripts.

import pytest

UV = shutil.which("uv")
ROOT = pathlib.Path(__file__).resolve().parent.parent
PYTHONS = ["3.12", "3.14"]


def clean_env() -> dict[str, str]:
    """Return an environment with no ``PYTHONPATH`` and no virtualenv."""
    env = {
        k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "VIRTUAL_ENV"}
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run(
    args: list[str], *, cwd: pathlib.Path, timeout: int = 900
) -> subprocess.CompletedProcess[str]:
    """Run one command in a clean environment and capture its output."""
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argument vectors built by the tests.
        args,
        cwd=cwd,
        env=clean_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def build_wheel(out: pathlib.Path) -> pathlib.Path:
    """Build the non-editable wheel into ``out`` and return its path."""
    if UV is None:
        pytest.skip("needs uv to build the wheel")
    built = run([UV, "build", "--wheel", "--out-dir", str(out), str(ROOT)], cwd=out)
    if built.returncode != 0:
        pytest.fail(f"wheel build failed: {built.stderr}")
    return next(out.glob("df12_python_lints-*.whl"))


def install_environment(
    root: pathlib.Path, wheel: pathlib.Path, python: str, *, extra: str | None
) -> pathlib.Path:
    """Create a fresh venv for ``python``, install the wheel, return its ``bin``.

    Parameters
    ----------
    root : pathlib.Path
        Directory that receives the virtual environment.
    wheel : pathlib.Path
        The built wheel.
    python : str
        Interpreter request, for example ``"3.12"``.
    extra : str | None
        Optional extra to install with the wheel.
    """
    if UV is None:
        pytest.skip("needs uv to install the wheel")
    venv = root / f"venv-{python}-{extra or 'bare'}"
    made = run([UV, "venv", "--python", python, str(venv)], cwd=root)
    if made.returncode != 0:
        pytest.skip(f"Python {python} is not available: {made.stderr.strip()[:200]}")
    spec = f"{wheel}[{extra}]" if extra else str(wheel)
    installed = run(
        [UV, "pip", "install", "--python", str(venv / "bin" / "python"), spec],
        cwd=root,
    )
    if installed.returncode != 0:
        pytest.fail(f"wheel installation failed: {installed.stderr}")
    return venv / "bin"
