"""``df12-skylos`` operations with a scripted backend, and the command line."""

from __future__ import annotations

import io
import logging
import typing as typ

import pytest
from skylos_support import FakeRunner, context_for, make_repository, probe

from df12_python_lints import _log
from df12_python_lints._runtime import Streams
from df12_python_lints.skylos import cli, commands

if typ.TYPE_CHECKING:
    import pathlib

_FINDING = "pkg/core.py:5  SKY-U001  unused function: never_called\n"


def _run(
    tmp_path: pathlib.Path, runner: FakeRunner
) -> tuple[int, str, str, pathlib.Path]:
    """Run ``check`` with a scripted backend; return status, streams, repository."""
    repo = make_repository(tmp_path)
    out, err = io.StringIO(), io.StringIO()
    code = commands.run_check(context_for(repo, runner), Streams(out, err))
    return code, out.getvalue(), err.getvalue(), repo


class TestCheck:
    """Verdicts and exit statuses."""

    def test_clean_gate_exits_zero_naming_backend_and_interpreter(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A completed clean scan passes."""
        code, out, _, _ = _run(tmp_path, FakeRunner())
        assert code == 0, "expected: code == 0"
        assert "skylos gate passed (skylos 4.33.2 under Python 3.12+)" in out, (
            "expected: 'skylos gate passed (skylos 4.33.2 under Python 3.12+)' in out"
        )

    def test_blocking_findings_exit_one_with_native_output_and_a_hint(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The native report is shown untouched, then how to record an exception."""
        code, out, _, _ = _run(tmp_path, FakeRunner(stdout=_FINDING, status=1))
        assert code == 1, "expected: code == 1"
        assert _FINDING in out, "expected: _FINDING in out"
        assert "df12-skylos allow --symbol" in out, (
            "expected: 'df12-skylos allow --symbol' in out"
        )

    def test_failed_analysis_exits_two(self, tmp_path: pathlib.Path) -> None:
        """Native status 2 is never green."""
        code, _, err, _ = _run(
            tmp_path, FakeRunner(stdout="x:1  SKY-ANALYSIS-INCOMPLETE  e\n", status=2)
        )
        assert code == 2, "expected: code == 2"
        assert "incomplete analysis" in err, "expected: 'incomplete analysis' in err"

    def test_empty_root_warning_exits_two(self, tmp_path: pathlib.Path) -> None:
        """A zero exit that logged an empty root is a failed scan."""
        runner = FakeRunner(stderr="WARNING - No Python files found in pkg\n")
        code, _, err, _ = _run(tmp_path, runner)
        assert code == 2, "expected: code == 2"
        assert "no Python files" in err, "expected: 'no Python files' in err"

    def test_old_interpreter_never_starts_the_scan(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The runtime is verified before the backend is invoked."""
        runner = FakeRunner()
        repo = make_repository(tmp_path)
        context = context_for(repo, runner, backend_probe=probe(interpreter=(3, 11)))
        err = io.StringIO()
        assert commands.run_check(context, Streams(io.StringIO(), err)) == 2, (
            "expected: commands.run_check(context, Streams(io.StringIO(), err)) == 2"
        )
        assert "requires 3.12 or newer" in err.getvalue(), (
            "expected: 'requires 3.12 or newer' in err.getvalue()"
        )
        assert not runner.calls, "no analysis may run under an unsuitable interpreter"

    def test_invalid_configuration_never_reaches_the_backend(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A lax gate is rejected before any subprocess."""
        runner = FakeRunner()
        repo = make_repository(tmp_path, policy="[tool.skylos.gate]\nstrict = false\n")
        err = io.StringIO()
        code = commands.run_check(
            context_for(repo, runner), Streams(io.StringIO(), err)
        )
        assert code == 2, "expected: code == 2"
        assert "strict must be true" in err.getvalue(), (
            "expected: 'strict must be true' in err.getvalue()"
        )
        assert not runner.calls, "expected: not runner.calls"

    def test_warnings_do_not_change_the_exit_status(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Advisories go to stderr and the clean gate still passes."""
        policy = (
            "[tool.skylos.gate]\nstrict = true\n"
            '[tool.skylos.whitelist]\nnames = ["x"]\n'
            '[tool.df12_skylos]\nroots = ["pkg"]\npython = "3.12"\n'
        )
        repo = make_repository(tmp_path, policy=policy)
        out, err = io.StringIO(), io.StringIO()
        assert commands.run_check(context_for(repo), Streams(out, err)) == 0, (
            "expected: commands.run_check(context_for(repo), Streams(out, err)) == 0"
        )
        assert "warning:" in err.getvalue(), "expected: 'warning:' in err.getvalue()"


class TestValidateConfig:
    """``validate-config`` invokes nothing and edits nothing."""

    def test_valid_configuration_runs_no_subprocess_and_leaves_the_file_alone(
        self, tmp_path: pathlib.Path
    ) -> None:
        """No backend, no provisioning, no edit."""
        runner = FakeRunner()
        repo = make_repository(tmp_path)
        before = (repo / "pyproject.toml").read_bytes()
        out = io.StringIO()
        code = commands.run_validate_config(
            context_for(repo, runner, backend_probe=probe(installed=None)),
            Streams(out, io.StringIO()),
        )
        assert code == 0, "expected: code == 0"
        assert "configuration valid" in out.getvalue(), (
            "expected: 'configuration valid' in out.getvalue()"
        )
        assert not runner.calls, "expected: not runner.calls"
        assert (repo / "pyproject.toml").read_bytes() == before, (
            "expected: (repo / 'pyproject.toml').read_bytes() == before"
        )

    def test_invalid_configuration_exits_two_naming_the_key(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The diagnostic names the offending key."""
        repo = make_repository(tmp_path, policy="[tool.skylos.gate]\nstrict = true\n")
        err = io.StringIO()
        code = commands.run_validate_config(
            context_for(repo), Streams(io.StringIO(), err)
        )
        assert code == 2, "expected: code == 2"
        assert "tool.df12_skylos" in err.getvalue(), (
            "expected: 'tool.df12_skylos' in err.getvalue()"
        )


class TestCommandLine:
    """Argument handling through ``main``."""

    def test_version_reports_package_pin_and_interpreter(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--version`` prints the diagnostics the issue asks for."""
        assert cli.main(["--version"]) == 0, "expected: cli.main(['--version']) == 0"
        out = capsys.readouterr().out
        assert out.startswith("df12-skylos "), (
            "expected: out.startswith('df12-skylos ')"
        )
        assert "skylos pin 4.33.2" in out, "expected: 'skylos pin 4.33.2' in out"

    def test_no_subcommand_is_an_invocation_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A bare invocation prints usage and exits two."""
        assert cli.main([]) == 2, "expected: cli.main([]) == 2"
        assert "usage" in capsys.readouterr().err, (
            "expected: 'usage' in capsys.readouterr().err"
        )

    def test_help_lists_every_operation(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--help`` documents the three operations."""
        with pytest.raises(SystemExit) as raised:
            cli.main(["--help"])
        assert raised.value.code == 0, "expected: raised.value.code == 0"
        out = capsys.readouterr().out
        assert all(word in out for word in ("check", "validate-config", "allow")), (
            "expected: all(word in out for word in ('check', 'validate-config', 'all..."
        )

    def test_bad_repository_exits_two(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A missing repository is an invocation error."""
        assert (
            cli.main(["validate-config", "--repository", str(tmp_path / "nope")]) == 2
        ), "expected: cli.main(['validate-config', '--repository', str(tmp_path / '..."
        assert "configuration error" in capsys.readouterr().err, (
            "expected: 'configuration error' in capsys.readouterr().err"
        )

    def test_defaults_to_the_invocation_directory(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without --repository the current directory is the target."""
        repo = make_repository(tmp_path)
        monkeypatch.chdir(repo)
        assert cli.main(["validate-config"]) == 0, (
            "expected: cli.main(['validate-config']) == 0"
        )

    def test_allow_requires_symbol_and_reason(self, tmp_path: pathlib.Path) -> None:
        """Argparse rejects missing options with its usage status."""
        repo = make_repository(tmp_path)
        with pytest.raises(SystemExit) as raised:
            cli.main(["allow", "--repository", str(repo), "--symbol", "x"])
        assert raised.value.code == 2, "expected: raised.value.code == 2"


def test_a_manifest_that_is_not_utf8_exits_two(tmp_path: pathlib.Path) -> None:
    """Invalid UTF-8 in ``pyproject.toml`` is a configuration error."""
    repo = make_repository(tmp_path)
    (repo / "pyproject.toml").write_bytes(b"[project]\nname = '\xff\xfe'\n")
    err = io.StringIO()
    code = commands.run_validate_config(context_for(repo), Streams(io.StringIO(), err))
    assert code == 2, "expected: code == 2"
    assert "cannot read" in err.getvalue(), "expected: 'cannot read' in err.getvalue()"


def test_verbose_logs_the_operation_and_its_outcome(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One record per operation carries scope, outcome and elapsed time."""
    monkeypatch.setattr(_log.logger, "handlers", list(_log.logger.handlers))
    monkeypatch.setattr(_log.logger, "level", logging.NOTSET)
    caplog.set_level(logging.DEBUG, logger="df12_python_lints")
    repo = make_repository(tmp_path)
    assert cli.main(["--verbose", "validate-config", "--repository", str(repo)]) == 0, (
        "expected: cli.main(['--verbose', 'validate-config', '--repository', str(rep..."
    )
    messages = [record.getMessage() for record in caplog.records]
    operation = next(m for m in messages if m.startswith("operation=validate-config"))
    assert "outcome=ok" in operation, operation
    assert "elapsed_seconds=" in operation, operation
