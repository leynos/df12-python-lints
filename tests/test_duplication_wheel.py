"""Install the built wheel into fresh environments and drive the console script.

Each case builds a non-editable wheel, creates a clean virtual environment for
one interpreter, installs the wheel (with or without the ``duplication``
extra) and runs ``df12-duplication`` from a directory that is neither this
checkout nor the target checkout, with ``PYTHONPATH`` absent and an
unrelated ``scripts`` package on the working directory.
"""

from __future__ import annotations

import typing as typ

import pytest
from duplication_support import Script, make_repository, report, write_fake_nose
from wheel_support import PYTHONS, UV, install_environment, run

pytestmark = pytest.mark.skipif(UV is None, reason="needs uv to build and install")

if typ.TYPE_CHECKING:
    import pathlib


@pytest.mark.parametrize("python", PYTHONS)
class TestInstalledWheel:
    """The console script from a fresh, non-editable installation."""

    def test_check_and_allow_run_from_outside_both_checkouts(
        self, tmp_path: pathlib.Path, wheel: pathlib.Path, python: str
    ) -> None:
        """check, allow and --version work with a decoy ``scripts`` package present."""
        bin_dir = install_environment(tmp_path, wheel, python, extra="duplication")
        outside = tmp_path / "outside"
        (outside / "scripts").mkdir(parents=True)
        (outside / "scripts" / "__init__.py").write_text(
            "raise SystemExit(99)\n", encoding="utf-8"
        )
        repo = make_repository(tmp_path / "target")
        write_fake_nose(repo / "n", Script(stdout=report()))
        command = str(bin_dir / "df12-duplication")
        checked = run(
            [command, "check", "--repository", str(repo), "--binary", "n"], cwd=outside
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        allowed = run(
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
        version = run([command, "--version"], cwd=outside)
        assert version.stdout.startswith("df12-duplication "), version.stdout

    def test_existing_commands_work_without_the_extra(
        self, tmp_path: pathlib.Path, wheel: pathlib.Path, python: str
    ) -> None:
        """Pylint plugin and ambrleaks need none of the duplication dependencies."""
        bin_dir = install_environment(tmp_path, wheel, python, extra=None)
        snap = tmp_path / "snaps"
        (snap / "__snapshots__").mkdir(parents=True)
        (snap / "__snapshots__" / "test_x.ambr").write_text(
            "# serializer version: 1\n", encoding="utf-8"
        )
        scan = run([str(bin_dir / "ambrleaks"), str(snap)], cwd=tmp_path)
        assert scan.returncode == 0, scan.stdout + scan.stderr
        plugin = run(
            [
                str(bin_dir / "python"),
                "-c",
                "import df12_python_lints, sys; sys.exit('tomlkit' in sys.modules)",
            ],
            cwd=tmp_path,
        )
        assert plugin.returncode == 0, "importing the plugin must not load tomlkit"
        help_ = run([str(bin_dir / "df12-duplication"), "--help"], cwd=tmp_path)
        assert help_.returncode == 0, help_.stderr


def test_wheel_bundles_the_release_manifest(wheel: pathlib.Path) -> None:
    """The digest table ships inside the distribution."""
    import zipfile

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert "df12_python_lints/duplication/releases.json" in names
