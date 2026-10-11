"""Saturation, encoding, observability and environmental-failure CLI behaviour."""

from __future__ import annotations

import logging
import tempfile
import typing as typ

import pytest
from duplication_support import (
    Script,
    check_scenario,
    family,
    location,
    make_repository,
    report,
    write_fake_nose,
)

from df12_python_lints import _log
from df12_python_lints.duplication import cli

if typ.TYPE_CHECKING:
    import pathlib

_A = location("src/a.py", 1, 20, "parse")
_B = location("src/b.py", 1, 20, "parse")
_C = location("src/c.py", 1, 20, "parse")


class TestSaturation:
    """A capped report that hides families can never pass."""

    def test_saturated_report_with_everything_allowed_fails_closed(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Episodic's case: every returned family is allowed, 40 exist."""
        extra = (
            "[[tool.duplication_gate.allow]]\n"
            'members = ["src/a.py::parse", "src/b.py::parse"]\nreason = "r"\n'
        )
        assert (
            check_scenario(tmp_path, report(family(_A, _B), total=40), extra=extra) == 2
        )
        assert "cannot prove a clean scan" in capsys.readouterr().err

    def test_unsaturated_report_with_everything_allowed_still_passes(
        self, tmp_path: pathlib.Path
    ) -> None:
        """When every family was returned, allowed families pass."""
        extra = (
            "[[tool.duplication_gate.allow]]\n"
            'members = ["src/a.py::parse", "src/b.py::parse"]\nreason = "r"\n'
        )
        assert check_scenario(tmp_path, report(family(_A, _B)), extra=extra) == 0


class TestObservability:
    """Operations and subprocesses are logged on request, and silent otherwise."""

    def test_verbose_logs_the_operation_and_the_subprocess(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """One record per operation carries scope, outcome and elapsed time."""
        monkeypatch.setattr(_log.logger, "handlers", list(_log.logger.handlers))
        monkeypatch.setattr(_log.logger, "level", logging.NOTSET)
        caplog.set_level(logging.DEBUG, logger="df12_python_lints")
        repo = make_repository(tmp_path / "repo")
        write_fake_nose(repo / "n", Script(stdout=report(family(_A, _B))))
        cli.main(["--verbose", "check", "--repository", str(repo), "--binary", "n"])
        messages = [record.getMessage() for record in caplog.records]
        operation = next(m for m in messages if m.startswith("operation=check"))
        assert f"repository={repo.resolve()}" in operation
        assert "outcome=blocking" in operation
        assert "elapsed_seconds=" in operation
        assert any(m.startswith("subprocess program=") for m in messages)

    def test_default_runs_attach_no_handler(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without ``--verbose`` the command adds no handler and stays quiet."""
        monkeypatch.setattr(_log.logger, "handlers", [logging.NullHandler()])
        repo = make_repository(tmp_path / "repo")
        write_fake_nose(repo / "n", Script(stdout=report()))
        cli.main(["check", "--repository", str(repo), "--binary", "n"])
        kinds = [type(handler) for handler in _log.logger.handlers]
        assert kinds == [logging.NullHandler]


class TestEncoding:
    """Detector output is UTF-8 whatever the process locale says."""

    def test_non_ascii_paths_still_match_exceptions_under_the_c_locale(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A report path such as ``é.py`` is decoded as UTF-8 and matches."""
        monkeypatch.setenv("LC_ALL", "C")
        monkeypatch.setenv("LANG", "C")
        extra = (
            "[[tool.duplication_gate.allow]]\n"
            'members = ["src/é.py", "src/ü.py"]\nreason = "unicode names"\n'
        )
        found = family(location("src/é.py"), location("src/ü.py"))
        assert check_scenario(tmp_path, report(found), extra=extra) == 0

    def test_undecodable_detector_output_exits_two(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bytes that are not UTF-8 are a failed analysis, not status one."""
        repo = make_repository(tmp_path / "repo")
        script = repo / "n"
        script.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "--version" ]; then echo "nose 0.20.0"; exit 0; fi\n'
            "printf '\\377\\376'\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        code = cli.main(["check", "--repository", str(repo), "--binary", "n"])
        assert code == 2
        assert "not valid UTF-8" in capsys.readouterr().err


class TestEnvironmentalFailures:
    """Expected environmental failures are exit two, never a traceback."""

    @pytest.mark.parametrize("command", [["check"], ["install"]])
    def test_a_manifest_that_is_not_utf8_exits_two(
        self,
        tmp_path: pathlib.Path,
        command: list[str],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Invalid UTF-8 in ``pyproject.toml`` is a configuration error."""
        repo = make_repository(tmp_path / "repo")
        (repo / "pyproject.toml").write_bytes(b"[project]\nname = '\xff\xfe'\n")
        assert cli.main([*command, "--repository", str(repo), "--binary", "n"]) == 2
        err = capsys.readouterr().err
        assert "cannot read" in err or "cannot load" in err
        assert "Traceback" not in err

    def test_scratch_directory_failure_exits_two(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """If the scratch files cannot be created the gate fails closed."""
        repo = make_repository(tmp_path / "repo")
        write_fake_nose(repo / "n", Script(stdout=report()))

        def refuse(*_args: object, **_kwargs: object) -> None:
            """Simulate a full or read-only temporary directory."""
            msg = "no space left"
            raise OSError(msg)

        monkeypatch.setattr(tempfile, "TemporaryDirectory", refuse)
        assert cli.main(["check", "--repository", str(repo), "--binary", "n"]) == 2
        assert "cannot prepare the scratch files" in capsys.readouterr().err

    def test_a_failure_is_logged_with_its_category(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The operation record names the failure category and the detector."""
        monkeypatch.setattr(_log.logger, "handlers", list(_log.logger.handlers))
        monkeypatch.setattr(_log.logger, "level", logging.NOTSET)
        caplog.set_level(logging.DEBUG, logger="df12_python_lints")
        repo = make_repository(tmp_path / "repo")
        write_fake_nose(repo / "n", Script(stdout=report(), version="nose 9.9.9"))
        cli.main(["check", "--repository", str(repo), "--binary", "n"])
        messages = [record.getMessage() for record in caplog.records]
        assert any("failure category=ToolExecutionError" in m for m in messages)
        write_fake_nose(repo / "n", Script(stdout=report(family(_A, _B))))
        cli.main(["check", "--repository", str(repo), "--binary", "n"])
        messages = [record.getMessage() for record in caplog.records]
        assert any("detector=nose-0.20.0" in m and "blocking=1" in m for m in messages)
