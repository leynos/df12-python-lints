"""Install the built wheel and drive ``df12-skylos`` from a fresh environment.

The command runs from a directory that is neither this checkout nor the target
repository, with ``PYTHONPATH`` absent and an unrelated ``scripts`` package on
the working directory. The scan interpreter and the package interpreter are
the same, so each supported Python is exercised on its own.
"""

from __future__ import annotations

import typing as typ

import pytest
from skylos_support import make_repository
from wheel_support import PYTHONS, UV, install_environment, run

pytestmark = pytest.mark.skipif(UV is None, reason="needs uv to build and install")

if typ.TYPE_CHECKING:
    import pathlib
    import subprocess

_USED = "def f():\n    return 1\n\n\ndef main():\n    return f()\n"
_DEAD = _USED + "\n\ndef never_called():\n    return 2\n"


def _outside(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a working directory holding a decoy ``scripts`` package."""
    outside = tmp_path / "outside"
    (outside / "scripts").mkdir(parents=True)
    (outside / "scripts" / "__init__.py").write_text(
        "raise SystemExit(99)\n", encoding="utf-8"
    )
    return outside


@pytest.mark.parametrize("python", PYTHONS)
class TestInstalledWheel:
    """The console script from a fresh, non-editable installation."""

    def test_version_and_validation_from_outside_both_checkouts(
        self, tmp_path: pathlib.Path, wheel: pathlib.Path, python: str
    ) -> None:
        """Version diagnostics and configuration validation need no scan."""
        command = str(
            install_environment(tmp_path, wheel, python, extra="skylos") / "df12-skylos"
        )
        outside = _outside(tmp_path)
        repo = make_repository(tmp_path / "target", files={"pkg/core.py": _USED})
        version = run([command, "--version"], cwd=outside)
        assert "skylos pin 4.33.2" in version.stdout, version.stdout + version.stderr
        valid = run(
            [command, "validate-config", "--repository", str(repo)], cwd=outside
        )
        assert valid.returncode == 0, valid.stdout + valid.stderr

    def test_clean_blocked_and_excused_scans_through_the_installed_command(
        self, tmp_path: pathlib.Path, wheel: pathlib.Path, python: str
    ) -> None:
        """Clean, planted and excused scans behave through the installed command."""
        bin_dir = install_environment(tmp_path, wheel, python, extra="skylos")
        outside = _outside(tmp_path)
        repo = make_repository(tmp_path / "target", files={"pkg/core.py": _USED})

        def df12(*arguments: str) -> subprocess.CompletedProcess[str]:
            """Run ``df12-skylos`` against the target from the outside directory."""
            command = [str(bin_dir / "df12-skylos"), *arguments]
            return run([*command, "--repository", str(repo)], cwd=outside)

        clean = df12("check")
        assert clean.returncode == 0, clean.stdout + clean.stderr
        (repo / "pkg" / "core.py").write_text(_DEAD, encoding="utf-8")
        blocked = df12("check")
        assert blocked.returncode == 1, blocked.stdout + blocked.stderr
        assert "never_called" in blocked.stdout
        allowed = df12("allow", "--symbol", "never_called", "--reason", "why")
        assert allowed.returncode == 0, allowed.stdout + allowed.stderr
        excused = df12("check")
        assert excused.returncode == 0, excused.stdout + excused.stderr

    def test_existing_commands_and_validation_work_without_the_extra(
        self, tmp_path: pathlib.Path, wheel: pathlib.Path, python: str
    ) -> None:
        """Without Skylos the plugin, ambrleaks and validation still work."""
        bin_dir = install_environment(tmp_path, wheel, python, extra=None)
        outside = _outside(tmp_path)
        repo = make_repository(tmp_path / "target", files={"pkg/core.py": _USED})
        target = ["--repository", str(repo)]
        plugin = run(
            [
                str(bin_dir / "python"),
                "-c",
                "import df12_python_lints, sys; sys.exit('skylos' in sys.modules)",
            ],
            cwd=outside,
        )
        assert plugin.returncode == 0, "importing the plugin must not load Skylos"
        snapshots = tmp_path / "snaps" / "__snapshots__"
        snapshots.mkdir(parents=True)
        (snapshots / "test_x.ambr").write_text(
            "# serializer version: 1\n", encoding="utf-8"
        )
        scan = run([str(bin_dir / "ambrleaks"), str(snapshots.parent)], cwd=outside)
        assert scan.returncode == 0, scan.stdout + scan.stderr
        command = str(bin_dir / "df12-skylos")
        valid = run([command, "validate-config", *target], cwd=outside)
        assert valid.returncode == 0, "validation needs no backend"
        checked = run([command, "check", *target], cwd=outside)
        assert checked.returncode == 2, checked.stdout + checked.stderr
        assert "skylos is not installed" in checked.stderr
        assert "Traceback" not in checked.stderr

    def test_an_unsuitable_interpreter_is_refused(
        self, tmp_path: pathlib.Path, wheel: pathlib.Path, python: str
    ) -> None:
        """A repository needing a newer interpreter than the scan runs under fails."""
        bin_dir = install_environment(tmp_path, wheel, python, extra="skylos")
        policy = (
            "[tool.skylos.gate]\nstrict = true\n[tool.df12_skylos]\n"
            'roots = ["pkg"]\npython = "3.99"\n'
        )
        repo = make_repository(
            tmp_path / "target", policy=policy, files={"pkg/core.py": _USED}
        )
        result = run(
            [str(bin_dir / "df12-skylos"), "check", "--repository", str(repo)],
            cwd=_outside(tmp_path),
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "requires 3.99 or newer" in result.stderr
