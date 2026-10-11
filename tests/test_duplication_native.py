"""Bounded integration tests against the real pinned nose binary.

These run only where a ``nose 0.20.0`` binary is available: set ``NOSE_BIN``
or install one with ``df12-duplication install`` (CI does). Each scenario is
a small disposable repository, so the whole module stays within seconds.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - runs the pinned binary to probe its version.
import typing as typ

import pytest
from duplication_support import PINNED, nose_table

from df12_python_lints.duplication import cli

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_CLONE = """\
def {name}(items):
    result = []
    for item in items:
        if item is None:
            continue
        value = str(item).strip().lower()
        if value:
            result.append(value)
    total = 0
    for entry in result:
        total += len(entry)
    return result, total
"""
_OTHER = """\
def {name}(mapping):
    keys = sorted(mapping)
    out = {{}}
    for key in keys:
        value = mapping[key]
        if isinstance(value, dict):
            out[key] = {name}(value)
        elif value is not None:
            out[key] = repr(value)
    return out, len(out)
"""


def _find_binary() -> pathlib.Path | None:
    """Locate a nose binary reporting the pinned version, else ``None``."""
    candidates = [
        os.environ.get("NOSE_BIN"),
        str(pathlib.Path(".tools/nose/nose").resolve()),
        shutil.which("nose"),
    ]
    for candidate in filter(None, candidates):
        try:
            result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argument vector.
                [candidate, "--version"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except OSError:
            continue
        if result.stdout.strip() == f"nose {PINNED}":
            return pathlib.Path(candidate).resolve()
    return None


_BINARY = _find_binary()
pytestmark = pytest.mark.skipif(_BINARY is None, reason=f"needs a nose {PINNED} binary")


def _table(roots: str = '["src"]', extra: str = "") -> str:
    """Render the ``[tool.nose]`` table for a disposable repository."""
    return '[project]\nname = "demo"\nversion = "0"\n\n' + nose_table(
        roots=roots,
        mode="syntax,semantic,near",
        extra=f'surface = "all"\ntop = 30\n{extra}',
    )


def _repo(
    tmp_path: pathlib.Path,
    files: cabc.Mapping[str, str],
    *,
    roots: str = '["src"]',
    extra: str = "",
) -> pathlib.Path:
    """Create a repository containing ``files`` and a ``[tool.nose]`` table."""
    repo = tmp_path / "repo"
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (repo / "pyproject.toml").write_text(_table(roots, extra), encoding="utf-8")
    return repo


def _check(repo: pathlib.Path) -> int:
    """Run ``check`` against ``repo`` with the real binary."""
    assert _BINARY is not None
    return cli.main(["check", "--repository", str(repo), "--binary", str(_BINARY)])


def _clones(count: int) -> dict[str, str]:
    """Return ``count`` structurally identical modules under ``src``."""
    return {f"src/m{i}.py": _CLONE.format(name=f"parse{i}") for i in range(count)}


class TestVerdicts:
    """Clean, planted-clone, allowed and grown-family scenarios."""

    def test_clean_repository_passes(self, tmp_path: pathlib.Path) -> None:
        """Dissimilar code is a clean scan."""
        files = {
            "src/a.py": _CLONE.format(name="a"),
            "src/b.py": _OTHER.format(name="b"),
        }
        assert _check(_repo(tmp_path, files)) == 0

    def test_planted_clone_blocks(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Two copies of one function block the gate."""
        assert _check(_repo(tmp_path, _clones(2))) == 1
        assert "src/m0.py" in capsys.readouterr().out

    def test_allowed_pair_passes_and_a_third_copy_blocks(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The exception covers the family it names and no more."""
        allow = (
            "\n[[tool.duplication_gate.allow]]\n"
            'members = ["src/m0.py::parse0", "src/m1.py::parse1"]\n'
            'reason = "deliberately parallel"\n'
        )
        repo = _repo(tmp_path / "pair", _clones(2), extra=allow)
        assert _check(repo) == 0, "the named pair is allowed"
        grown = _repo(tmp_path / "trio", _clones(3), extra=allow)
        assert _check(grown) == 1, "a third copy must block"

    def test_cross_root_families_are_found_in_one_query(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A clone split across two roots is still one family."""
        files = {
            "one/a.py": _CLONE.format(name="a"),
            "two/b.py": _CLONE.format(name="b"),
        }
        assert _check(_repo(tmp_path, files, roots='["one", "two"]')) == 1


class TestEmptyAndMissingScans:
    """A source-free or unreachable scan can never pass."""

    def test_missing_root_is_an_error(self, tmp_path: pathlib.Path) -> None:
        """A configured root that does not exist fails fast."""
        assert _check(_repo(tmp_path, {"src/a.py": "x = 1\n"}, roots='["nope"]')) == 2

    def test_root_without_supported_source_is_an_error(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Nose exits 0 with a warning; the gate must still refuse."""
        repo = _repo(tmp_path, {"src/readme.txt": "text\n"})
        assert _check(repo) == 2

    def test_fully_excluded_root_is_an_error(self, tmp_path: pathlib.Path) -> None:
        """Excluding every file leaves an empty effective scan."""
        repo = _repo(tmp_path, _clones(2), extra='exclude = ["*.py"]\n')
        assert _check(repo) == 2

    def test_wrong_pinned_version_is_an_error(self, tmp_path: pathlib.Path) -> None:
        """The binary must report exactly the pinned version."""
        repo = _repo(tmp_path, _clones(2))
        text = (
            (repo / "pyproject.toml")
            .read_text(encoding="utf-8")
            .replace(PINNED, "0.19.0")
        )
        (repo / "pyproject.toml").write_text(text, encoding="utf-8")
        assert _check(repo) == 2


class TestNativeConfigurationCannotSuppress:
    """Ambient nose files must not become a second suppression policy."""

    def test_ambient_nose_toml_and_ignore_file_do_not_hide_a_clone(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A raised threshold and a blanket ignore in the checkout are ignored."""
        repo = _repo(tmp_path, _clones(2))
        (repo / "nose.toml").write_text("[query]\nmin-size = 5000\n", encoding="utf-8")
        (repo / ".nose.toml").write_text("[query]\nmin-size = 5000\n", encoding="utf-8")
        (repo / "nose.ignore.json").write_text(
            '{"ignores":[{"paths":["src/**"],"reason":"accepted-risk"}]}',
            encoding="utf-8",
        )
        assert _check(repo) == 1, "the gate must still see the planted clone"

    def test_a_malformed_ambient_config_cannot_break_the_gate(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An invalid ambient file is not read at all."""
        repo = _repo(tmp_path, _clones(2))
        (repo / "nose.toml").write_text("this is [not toml", encoding="utf-8")
        assert _check(repo) == 1


class TestReportBudget:
    """Capped and unlimited reports."""

    def _two_families(self) -> dict[str, str]:
        """Return files forming two distinct duplication families."""
        files = {f"src/a{i}.py": _CLONE.format(name=f"a{i}") for i in range(2)}
        files.update({f"src/b{i}.py": _OTHER.format(name=f"b{i}") for i in range(2)})
        return files

    def test_capped_report_is_flagged_saturated(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``top = 1`` hides one family and the command says so."""
        repo = _repo(tmp_path, self._two_families())
        text = (
            (repo / "pyproject.toml")
            .read_text(encoding="utf-8")
            .replace("top = 30", "top = 1")
        )
        (repo / "pyproject.toml").write_text(text, encoding="utf-8")
        assert _check(repo) == 1
        assert "returned 1 of 2 families" in capsys.readouterr().err

    def test_top_zero_reports_every_family(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``top = 0`` is the detector's unlimited budget."""
        repo = _repo(tmp_path, self._two_families())
        text = (
            (repo / "pyproject.toml")
            .read_text(encoding="utf-8")
            .replace("top = 30", "top = 0")
        )
        (repo / "pyproject.toml").write_text(text, encoding="utf-8")
        assert _check(repo) == 1
        out = capsys.readouterr()
        assert "saturated" not in out.err, "an unlimited report is never saturated"
        assert out.out.count("(") >= 2, "both families are listed"


def test_real_binary_lets_the_unmatched_diagnostic_fire(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An entry for code that is not duplicated is reported as unmatched."""
    files = {"src/a.py": _CLONE.format(name="a"), "src/b.py": _OTHER.format(name="b")}
    allow = (
        '\n[[tool.duplication_gate.allow]]\nunit = "src/gone.py"\nreason = "was here"\n'
    )
    assert _check(_repo(tmp_path, files, extra=allow)) == 0
    assert "unmatched in this scan" in capsys.readouterr().err
