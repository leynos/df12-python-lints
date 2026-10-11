"""``df12-duplication`` end to end through ``main`` with a scripted detector."""

from __future__ import annotations

import sys
import tomllib
import typing as typ

import pytest
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

_A = location("src/a.py", 1, 20, "parse")
_B = location("src/b.py", 1, 20, "parse")
_C = location("src/c.py", 1, 20, "parse")


class TestCheck:
    """The gate's verdicts and exit statuses."""

    def test_clean_scan_passes(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No families: exit 0 with the pinned detector version in the message."""
        code = _check(tmp_path, report())
        out = capsys.readouterr().out
        assert code == 0, out
        assert "duplication gate passed (nose 0.20.0)" in out

    def test_blocking_family_exits_one_with_actionable_report(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A planted clone blocks and shows how to record an exception."""
        code = _check(tmp_path, report(family(_A, _B)))
        out = capsys.readouterr().out
        assert code == 1, out
        assert (
            "src/a.py:1-20 parse ~ src/b.py:1-20 parse (copy-paste, value 22.1)" in out
        )
        assert "df12-duplication allow --member" in out

    def test_allowed_pair_passes_and_third_copy_blocks(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An exception for a pair excuses it, and a third copy blocks again."""
        extra = (
            "[[tool.duplication_gate.allow]]\n"
            'members = ["src/a.py::parse", "src/b.py::parse"]\n'
            'reason = "independent entry points"\n'
        )
        assert _check(tmp_path / "one", report(family(_A, _B)), extra=extra) == 0
        assert "1 allowed by reasoned exceptions" in capsys.readouterr().out
        assert _check(tmp_path / "two", report(family(_A, _B, _C)), extra=extra) == 1
        assert "src/c.py" in capsys.readouterr().out, "the grown family blocks"

    def test_unmatched_entry_is_explained_without_claiming_the_duplication_is_gone(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The diagnostic names ranking and budget, and never says it is gone."""
        extra = '[[tool.duplication_gate.allow]]\nunit = "src/z.py"\nreason = "old"\n'
        assert _check(tmp_path, report(), extra=extra) == 0
        err = capsys.readouterr().err
        assert "unmatched in this scan" in err
        assert "ranking" in err
        assert "duplication is gone" not in err
        assert "not removed automatically" in err

    def test_budget_saturation_is_reported(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A capped report says how many families went unenforced."""
        assert _check(tmp_path, report(family(_A, _B), total=40)) == 1
        err = capsys.readouterr().err
        assert "returned 1 of 40 families" in err
        assert "tool.nose.top" in err

    @pytest.mark.parametrize(
        ("kwargs", "fragment"),
        [
            ({"stdout": "not json"}, "not valid JSON"),
            ({"status": 3, "stderr": "bad"}, "status 3"),
            ({"version": "nose 9.9.9"}, "pins 'nose 0.20.0'"),
            (
                {"stderr": "warning: no supported source files found under: src"},
                "no supported source",
            ),
            ({"stdout": '{"schema_version": 9}'}, "summary"),
        ],
    )
    def test_failed_analysis_exits_two_without_a_traceback(
        self,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture[str],
        kwargs: dict[str, typ.Any],
        fragment: str,
    ) -> None:
        """Each failure class is exit 2 with a one-line diagnostic."""
        repo = make_repository(tmp_path / "repo")
        kwargs.setdefault("stdout", report())
        write_fake_nose(repo / "n", Script(**kwargs))
        code = cli.main(["check", "--repository", str(repo), "--binary", "n"])
        err = capsys.readouterr().err
        assert code == 2, err
        assert fragment in err
        assert "Traceback" not in err

    def test_missing_repository_and_pyproject_exit_two(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A bad --repository is an invocation error."""
        assert cli.main(["check", "--repository", str(tmp_path / "nope")]) == 2
        assert cli.main(["check", "--repository", str(tmp_path)]) == 2
        assert "pyproject.toml" in capsys.readouterr().err

    def test_defaults_to_the_invocation_directory(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without --repository the current directory is the target."""
        repo = make_repository(tmp_path / "repo")
        write_fake_nose(repo / "n", Script(stdout=report()))
        monkeypatch.chdir(repo)
        assert cli.main(["check", "--binary", "n"]) == 0

    def test_does_not_import_an_unrelated_scripts_package_or_change_cwd(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A generic ``scripts`` package on the path is never consulted."""
        decoy = tmp_path / "decoy"
        (decoy / "scripts").mkdir(parents=True)
        (decoy / "scripts" / "__init__.py").write_text(
            "raise SystemExit(99)\n", encoding="utf-8"
        )
        monkeypatch.syspath_prepend(str(decoy))
        repo = make_repository(tmp_path / "repo")
        write_fake_nose(repo / "n", Script(stdout=report()))
        before = str(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert cli.main(["check", "--repository", str(repo), "--binary", "n"]) == 0
        assert str(__import__("pathlib").Path.cwd()) == before, "cwd must not change"
        assert "scripts" not in sys.modules, "the decoy package must not be imported"


def _check(tmp_path: pathlib.Path, stdout: str, *, extra: str = "") -> int:
    """Run ``check`` against a repository whose detector prints ``stdout``."""
    repo = make_repository(tmp_path / "repo", extra=extra)
    write_fake_nose(repo / "n", Script(stdout=stdout))
    return cli.main(["check", "--repository", str(repo), "--binary", "n"])


class TestAllow:
    """Authoring through the command line."""

    def _repo(self, tmp_path: pathlib.Path) -> pathlib.Path:
        """Create a disposable repository."""
        return make_repository(tmp_path / "repo")

    def test_repeated_member_records_one_whole_family_entry(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """One or many members work without Make-variable splitting."""
        repo = self._repo(tmp_path)
        code = cli.main([
            "allow",
            "--repository",
            str(repo),
            "--member",
            "src/a.py::parse",
            "--member",
            "src/b.py::parse",
            "--member",
            "src/c.py::parse",
            "--reason",
            "Independently versioned.",
        ])
        assert code == 0, capsys.readouterr()
        entry = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))[
            "tool"
        ]["duplication_gate"]["allow"][0]
        assert entry["members"] == [
            "src/a.py::parse",
            "src/b.py::parse",
            "src/c.py::parse",
        ]

    def test_first_and_second_aliases_still_work(self, tmp_path: pathlib.Path) -> None:
        """The legacy --first/--second spelling maps onto members."""
        repo = self._repo(tmp_path)
        code = cli.main([
            "allow",
            "--repository",
            str(repo),
            "--first",
            "src/a.py",
            "--second",
            "src/b.py",
            "--reason",
            "legacy spelling",
        ])
        assert code == 0
        data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
        assert data["tool"]["duplication_gate"]["allow"][0]["members"] == [
            "src/a.py",
            "src/b.py",
        ]

    def test_arguments_with_spaces_unicode_and_shell_text_are_preserved(
        self, tmp_path: pathlib.Path
    ) -> None:
        """No shell is involved, so nothing is split or evaluated."""
        repo = self._repo(tmp_path)
        reason = "$(echo hi) `id` 'q' \"d\" ünï  trailing "
        assert (
            cli.main([
                "allow",
                "--repository",
                str(repo),
                "--member",
                "src/my file.py::f g",
                "--reason",
                reason,
            ])
            == 0
        )
        entry = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))[
            "tool"
        ]["duplication_gate"]["allow"][0]
        assert entry == {"unit": "src/my file.py::f g", "reason": reason}

    @pytest.mark.parametrize(
        "args",
        [
            ["--member", "a.py", "--reason", "  "],
            ["--reason", "r"],
            ["--member", "../x", "--reason", "r"],
            ["--member", "a.py::", "--reason", "r"],
        ],
    )
    def test_invalid_requests_exit_two_and_do_not_mutate(
        self,
        tmp_path: pathlib.Path,
        args: list[str],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Invalid input is rejected before the manifest is touched."""
        repo = self._repo(tmp_path)
        before = (repo / "pyproject.toml").read_bytes()
        assert cli.main(["allow", "--repository", str(repo), *args]) == 2
        assert (repo / "pyproject.toml").read_bytes() == before
        assert "configuration error" in capsys.readouterr().err

    def test_reason_is_required_by_the_parser(self, tmp_path: pathlib.Path) -> None:
        """Argparse rejects a missing --reason with its usage exit status."""
        with pytest.raises(SystemExit) as raised:
            cli.main([
                "allow",
                "--repository",
                str(self._repo(tmp_path)),
                "--member",
                "a.py",
            ])
        assert raised.value.code == 2


class TestEntryPoint:
    """Help, version and optional-dependency handling."""

    def test_version_prints_the_package_version(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--version`` reports the installed distribution."""
        assert cli.main(["--version"]) == 0
        assert capsys.readouterr().out.startswith("df12-duplication ")

    def test_no_subcommand_is_an_invocation_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A bare invocation prints usage and exits two."""
        assert cli.main([]) == 2
        assert "usage" in capsys.readouterr().err

    def test_help_lists_every_operation(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--help`` documents check, allow and install."""
        with pytest.raises(SystemExit) as raised:
            cli.main(["--help"])
        assert raised.value.code == 0
        out = capsys.readouterr().out
        assert all(word in out for word in ("check", "allow", "install"))
