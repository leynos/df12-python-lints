"""``df12-duplication allow`` records only keys that cover a reported family.

The vendored gate this command replaced ran the detector first and refused an
exception covering no reported family, so a misspelled key failed instead of
recording an entry that silences nothing. v0.4.0 of the command lacked that
check; these tests pin it.
"""

from __future__ import annotations

import typing as typ

from duplication_support import (
    Script,
    family,
    location,
    make_repository,
    report,
    write_fake_nose,
)

from df12_python_lints.duplication import cli

if typ.TYPE_CHECKING:
    import pathlib

    import pytest

_A = location("src/a.py", 1, 20, "parse")
_B = location("src/b.py", 1, 20, "parse")
_C = location("src/c.py", 1, 20, "parse")


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a repository whose detector reports one three-member family."""
    repo = make_repository(tmp_path / "repo")
    write_fake_nose(repo / "n", Script(stdout=report(family(_A, _B, _C))))
    return repo


def _allow(repo: pathlib.Path, binary: str, *members: str) -> int:
    """Run ``allow`` for ``members`` with the given detector binary."""
    argv = ["allow", "--repository", str(repo), "--binary", binary]
    for member in members:
        argv.extend(("--member", member))
    return cli.main([*argv, "--reason", "why"])


class TestAllowCoverage:
    """The detector gates the write."""

    def test_key_covering_no_reported_family_is_refused(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A misspelled key exits 2 with the old message and writes nothing."""
        repo = _repo(tmp_path)
        before = (repo / "pyproject.toml").read_bytes()
        code = _allow(repo, "n", "src/nonexistent.py")
        assert code == 2, "expected: a key matching no family to exit 2"
        assert "covers no reported family" in capsys.readouterr().err, (
            "expected: 'covers no reported family' in the error output"
        )
        assert (repo / "pyproject.toml").read_bytes() == before, (
            "expected: the manifest to stay untouched"
        )

    def test_key_set_covering_only_part_of_a_family_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Coverage is whole-family: two keys for a three-member family fail."""
        repo = _repo(tmp_path)
        before = (repo / "pyproject.toml").read_bytes()
        code = _allow(repo, "n", "src/a.py::parse", "src/b.py::parse")
        assert code == 2, "expected: partial coverage to exit 2"
        assert (repo / "pyproject.toml").read_bytes() == before, (
            "expected: the manifest to stay untouched"
        )

    def test_whole_family_is_recorded(self, tmp_path: pathlib.Path) -> None:
        """Keys covering every location are written."""
        repo = _repo(tmp_path)
        code = _allow(
            repo, "n", "src/a.py::parse", "src/b.py::parse", "src/c.py::parse"
        )
        assert code == 0, "expected: whole-family coverage to exit 0"
        assert "src/c.py::parse" in (repo / "pyproject.toml").read_text(
            encoding="utf-8"
        ), "expected: the entry to be written"

    def test_unusable_detector_stops_allow_before_writing(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A detector that cannot run is an error and records nothing."""
        repo = _repo(tmp_path)
        before = (repo / "pyproject.toml").read_bytes()
        code = _allow(repo, "missing-nose", "src/a.py::parse")
        assert code == 2, "expected: an unusable detector to exit 2"
        assert (repo / "pyproject.toml").read_bytes() == before, (
            "expected: the manifest to stay untouched"
        )
