"""Install the built wheel into fresh environments and drive the console script.

Each case builds a non-editable wheel, creates a clean virtual environment for
one interpreter, installs the wheel (with or without the ``duplication``
extra) and runs ``df12-duplication`` from a directory that is neither this
checkout nor the target checkout, with ``PYTHONPATH`` absent and an
unrelated ``scripts`` package on the working directory.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - drives uv and the installed console script.
import typing as typ

import pytest
from duplication_support import Script, make_repository, report, write_fake_nose

_UV = shutil.which("uv")
_ROOT = pathlib.Path(__file__).resolve().parent.parent
pytestmark = [
    pytest.mark.skipif(_UV is None, reason="needs uv to build and install"),
    # Each test builds, creates a venv and installs; a cold cache exceeds the
    # suite-wide 30 s limit, so match the subprocess bounds instead.
    pytest.mark.timeout(900),
]
_PYTHONS = ["3.12", "3.14"]

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def _clean_env() -> dict[str, str]:
    """Environment with no ``PYTHONPATH`` and no activated virtualenv."""
    env = {
        k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "VIRTUAL_ENV"}
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run(
    args: list[str], *, cwd: pathlib.Path, timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    """Run one command in a clean environment and capture its output."""
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argument vectors built by this module.
        args,
        cwd=cwd,
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """Build the wheel once for the module."""
    out = tmp_path_factory.mktemp("wheel")
    assert _UV is not None
    built = _run([_UV, "build", "--wheel", "--out-dir", str(out), str(_ROOT)], cwd=out)
    assert built.returncode == 0, built.stderr
    return next(out.glob("df12_python_lints-*.whl"))


def _environment(
    root: pathlib.Path, wheel: pathlib.Path, python: str, *, extra: bool
) -> pathlib.Path:
    """Create a fresh venv for ``python`` and install the wheel; return its bin."""
    assert _UV is not None
    venv = root / f"venv-{python}-{'extra' if extra else 'bare'}"
    made = _run([_UV, "venv", "--python", python, str(venv)], cwd=root)
    if made.returncode != 0:
        pytest.skip(f"Python {python} is not available: {made.stderr.strip()[:200]}")
    spec = f"{wheel}[duplication]" if extra else str(wheel)
    installed = _run(
        [_UV, "pip", "install", "--python", str(venv / "bin" / "python"), spec],
        cwd=root,
    )
    assert installed.returncode == 0, installed.stderr
    return venv / "bin"


@pytest.mark.parametrize("python", _PYTHONS)
class TestInstalledWheel:
    """The console script from a fresh, non-editable installation."""

    def test_check_and_allow_run_from_outside_both_checkouts(
        self, tmp_path: pathlib.Path, wheel: pathlib.Path, python: str
    ) -> None:
        """check, allow and --version work with a decoy ``scripts`` package present."""
        bin_dir = _environment(tmp_path, wheel, python, extra=True)
        outside = tmp_path / "outside"
        (outside / "scripts").mkdir(parents=True)
        (outside / "scripts" / "__init__.py").write_text(
            "raise SystemExit(99)\n", encoding="utf-8"
        )
        repo = make_repository(tmp_path / "target")
        write_fake_nose(repo / "n", Script(stdout=report()))
        command = str(bin_dir / "df12-duplication")
        checked = _run(
            [command, "check", "--repository", str(repo), "--binary", "n"], cwd=outside
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        allowed = _run(
            [
                command,
                "allow",
                "--repository",
                str(repo),
                "--member",
                "src/a.py",
                "--reason",
                "why",
            ],
            cwd=outside,
        )
        assert allowed.returncode == 0, allowed.stdout + allowed.stderr
        assert "duplication_gate" in (repo / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        version = _run([command, "--version"], cwd=outside)
        assert version.stdout.startswith("df12-duplication "), version.stdout

    def test_existing_commands_work_without_the_extra(
        self, tmp_path: pathlib.Path, wheel: pathlib.Path, python: str
    ) -> None:
        """Pylint plugin and ambrleaks need none of the duplication dependencies."""
        bin_dir = _environment(tmp_path, wheel, python, extra=False)
        snap = tmp_path / "snaps"
        (snap / "__snapshots__").mkdir(parents=True)
        (snap / "__snapshots__" / "test_x.ambr").write_text(
            "# serializer version: 1\n", encoding="utf-8"
        )
        scan = _run([str(bin_dir / "ambrleaks"), str(snap)], cwd=tmp_path)
        assert scan.returncode == 0, scan.stdout + scan.stderr
        plugin = _run(
            [
                str(bin_dir / "python"),
                "-c",
                "import df12_python_lints, sys; sys.exit('tomlkit' in sys.modules)",
            ],
            cwd=tmp_path,
        )
        assert plugin.returncode == 0, "importing the plugin must not load tomlkit"
        help_ = _run([str(bin_dir / "df12-duplication"), "--help"], cwd=tmp_path)
        assert help_.returncode == 0, help_.stderr


def test_wheel_bundles_the_release_manifest(wheel: pathlib.Path) -> None:
    """The digest table ships inside the distribution."""
    import zipfile

    with zipfile.ZipFile(wheel) as archive:
        names: cabc.Collection[str] = archive.namelist()
    assert "df12_python_lints/duplication/releases.json" in names
