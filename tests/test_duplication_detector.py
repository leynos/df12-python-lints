"""The detector adapter: command construction, containment and failure handling."""

from __future__ import annotations

import pathlib
import typing as typ

import pytest
from duplication_support import (
    PINNED,
    FakeRunner,
    family,
    location,
    make_repository,
    nose_table,
    report,
)

from df12_python_lints._errors import ToolConfigError, ToolExecutionError
from df12_python_lints.duplication import context as context_module
from df12_python_lints.duplication.detector import resolve_binary, run_detector
from df12_python_lints.duplication.settings import load_settings

if typ.TYPE_CHECKING:
    from df12_python_lints.duplication.schema import DetectorReport
    from df12_python_lints.duplication.settings import NoseSettings


def _prepared(
    tmp_path: pathlib.Path,
    runner: FakeRunner,
    *,
    binary: str = "bin/nose",
    env: dict[str, str] | None = None,
) -> tuple[context_module.RunContext, NoseSettings]:
    """Build a context with an existing fake binary and the loaded settings."""
    repo = make_repository(tmp_path / "repo")
    (repo / "bin").mkdir()
    (repo / binary).write_text("#!/bin/sh\n", encoding="utf-8")
    context = context_module.build_context(
        repository=str(repo),
        binary=binary,
        environment=env or {},
        options=context_module.ContextOptions(runner=runner),
    )
    return context, load_settings(context.pyproject)


class TestCommandConstruction:
    """One argument vector, no shell, explicit working directory."""

    def test_all_roots_go_to_one_query_in_the_repository(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Cross-root families need one detector query with every root."""
        runner = FakeRunner(query_stdout=report())
        repo = make_repository(
            tmp_path / "r",
            nose_table=nose_table(
                roots='["src", "src"]',
                extra='exclude = ["t/**", "x y"]\ntop = 0\nsurface = "default"\n',
            ),
        )
        context = context_module.build_context(
            repository=str(repo),
            binary="n",
            environment={},
            options=context_module.ContextOptions(runner=runner),
        )
        (repo / "n").write_text("", encoding="utf-8")
        run_detector(load_settings(context.pyproject), context)
        argv = runner.query_argv
        assert argv[1:5] == ["query", "--root", "src", "--root"], argv
        assert argv.count("query") == 1, "exactly one query"
        assert "all" not in argv, "surface default must not widen"
        assert "top=0" in argv, "the unlimited budget term is passed"
        assert argv[argv.index("--min-size") + 1] == "24"
        assert [argv[i + 1] for i, a in enumerate(argv) if a == "--exclude"] == [
            "t/**",
            "x y",
        ], "exclusions with spaces stay one argument"
        assert {cwd for _, cwd in runner.calls} == {context.repository}, "explicit cwd"

    def test_surface_all_and_top_budget_terms(self, tmp_path: pathlib.Path) -> None:
        """``all`` and ``top=N`` terms are emitted as query terms."""
        runner = FakeRunner(query_stdout=report())
        context, settings = _prepared(tmp_path, runner)
        run_detector(settings, context)
        argv = runner.query_argv
        assert "all" in argv, argv
        assert "top=30" in argv, argv

    def test_ambient_native_configuration_is_neutralized(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Empty --config and --ignore-file stop ambient files taking effect."""
        runner = FakeRunner(query_stdout=report())
        context, settings = _prepared(tmp_path, runner)
        run_detector(settings, context)
        assert sorted(runner.neutral_files) == [
            ("--config", ""),
            ("--ignore-file", '{"ignores": []}\n'),
        ]
        argv = runner.query_argv
        scratch = pathlib.Path(argv[argv.index("--config") + 1])
        assert not scratch.exists(), "scratch files are removed after the run"
        assert context.repository not in scratch.parents, (
            "neutral files live outside the checkout"
        )

    def test_arguments_are_a_list_never_a_shell_string(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Shell-sensitive characters in roots and globs reach the argv literally."""
        runner = FakeRunner(query_stdout=report())
        repo = make_repository(
            tmp_path / "r",
            nose_table=nose_table(extra="exclude = [\"$(touch pwned) `x` 'q' é\"]\n"),
        )
        (repo / "n").write_text("", encoding="utf-8")
        context = context_module.build_context(
            repository=str(repo),
            binary="n",
            environment={},
            options=context_module.ContextOptions(runner=runner),
        )
        run_detector(load_settings(context.pyproject), context)
        assert "$(touch pwned) `x` 'q' é" in runner.query_argv, "literal argument"
        assert not (repo / "pwned").exists()


class TestBinaryResolution:
    """Override, local install and PATH, always version-checked."""

    def test_wrong_version_is_rejected(self, tmp_path: pathlib.Path) -> None:
        """A binary reporting another version cannot run the gate."""
        runner = FakeRunner(version="nose 0.19.0")
        context, settings = _prepared(tmp_path, runner)
        with pytest.raises(ToolExecutionError, match=r"pins 'nose 0\.20\.0'"):
            resolve_binary(settings, context)

    def test_failing_version_command_is_rejected(self, tmp_path: pathlib.Path) -> None:
        """A non-zero ``--version`` is not a pass even if it prints the pin."""
        runner = FakeRunner(version_status=3)
        context, settings = _prepared(tmp_path, runner)
        with pytest.raises(ToolExecutionError, match="reports"):
            resolve_binary(settings, context)

    def test_missing_binary_points_at_install(self, tmp_path: pathlib.Path) -> None:
        """No candidate gives the explicit install hint and provisions nothing."""
        repo = make_repository(tmp_path / "r")
        runner = FakeRunner()
        context = context_module.build_context(
            repository=str(repo),
            binary=None,
            environment={"PATH": ""},
            options=context_module.ContextOptions(runner=runner),
        )
        with pytest.raises(ToolExecutionError, match="df12-duplication install"):
            resolve_binary(load_settings(context.pyproject), context)
        assert not runner.calls, "checking must not run or fetch anything"

    def test_relative_override_resolves_against_the_repository(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The override is relative to --repository, not the invocation directory."""
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        runner = FakeRunner()
        context, settings = _prepared(tmp_path, runner)
        assert resolve_binary(settings, context) == str(
            context.repository / "bin" / "nose"
        )

    def test_nose_bin_environment_is_honoured_and_beaten_by_the_flag(
        self, tmp_path: pathlib.Path
    ) -> None:
        """``--binary`` wins over ``NOSE_BIN``; both are repository-relative."""
        repo = make_repository(tmp_path / "r")
        env = context_module.build_context(
            repository=str(repo), binary=None, environment={"NOSE_BIN": "a/nose"}
        )
        flag = context_module.build_context(
            repository=str(repo), binary="b/nose", environment={"NOSE_BIN": "a/nose"}
        )
        assert env.binary_override == repo.resolve() / "a" / "nose"
        assert flag.binary_override == repo.resolve() / "b" / "nose"

    def test_local_install_is_preferred_to_path(self, tmp_path: pathlib.Path) -> None:
        """``.tools/nose/nose`` wins when no override is given."""
        repo = make_repository(tmp_path / "r")
        local = repo / ".tools" / "nose" / "nose"
        local.parent.mkdir(parents=True)
        local.write_text("", encoding="utf-8")
        runner = FakeRunner()
        context = context_module.build_context(
            repository=str(repo),
            binary=None,
            environment={"PATH": "/nonexistent"},
            options=context_module.ContextOptions(runner=runner),
        )
        assert resolve_binary(load_settings(context.pyproject), context) == str(local)


class TestFailuresNeverPass:
    """Every failure class is an error, never a green gate."""

    def _run(self, tmp_path: pathlib.Path, runner: FakeRunner) -> DetectorReport:
        """Run the detector with a scripted runner."""
        context, settings = _prepared(tmp_path, runner)
        return run_detector(settings, context)

    def test_nonzero_exit_includes_stderr(self, tmp_path: pathlib.Path) -> None:
        """A failing detector surfaces its diagnostics."""
        runner = FakeRunner(query_status=2, query_stderr="boom: bad root\n")
        with pytest.raises(ToolExecutionError, match="status 2: boom: bad root"):
            self._run(tmp_path, runner)

    def test_malformed_json_is_an_execution_error(self, tmp_path: pathlib.Path) -> None:
        """Garbage on stdout is not an empty report."""
        with pytest.raises(ToolExecutionError, match="not valid JSON"):
            self._run(tmp_path, FakeRunner(query_stdout="not json"))

    def test_schema_violation_is_a_configuration_error(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A report missing consumed fields fails closed."""
        with pytest.raises(ToolConfigError, match="summary"):
            self._run(
                tmp_path,
                FakeRunner(query_stdout='{"schema_version": 9, "families": []}'),
            )

    def test_successful_but_empty_scan_warning_is_rejected(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A zero exit with nose's empty-source warning must not pass."""
        stderr = (
            "warning: no supported source files found under: src\n"
            "  (supported extensions: py)\n"
        )
        with pytest.raises(
            ToolConfigError, match="no supported source files under src"
        ):
            self._run(tmp_path, FakeRunner(query_stdout=report(), query_stderr=stderr))

    def test_each_empty_root_is_named_once(self, tmp_path: pathlib.Path) -> None:
        """Repeated warnings for one root are de-duplicated, order kept."""
        stderr = (
            "warning: no supported source files found under: b\n"
            "warning: no supported source files found under: a\n"
            "warning: no supported source files found under: b\n"
        )
        with pytest.raises(ToolConfigError, match="under b, a;"):
            self._run(tmp_path, FakeRunner(query_stdout=report(), query_stderr=stderr))

    def test_clean_report_is_returned(self, tmp_path: pathlib.Path) -> None:
        """A valid empty report is a clean scan."""
        result = self._run(tmp_path, FakeRunner(query_stdout=report()))
        assert not result.findings, "no families means clean"

    def test_timeout_is_reported_by_the_default_runner(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The real runner bounds execution and reports the timeout."""
        script = tmp_path / "slow.sh"
        script.write_text("#!/bin/sh\nexec sleep 5\n", encoding="utf-8")
        script.chmod(0o755)
        with pytest.raises(ToolExecutionError, match="timed out after 1 seconds"):
            context_module.run_command(
                [str(script)], tmp_path, {"PATH": "/bin:/usr/bin"}, 1
            )

    def test_unrunnable_binary_is_reported(self, tmp_path: pathlib.Path) -> None:
        """A non-executable binary is an execution error."""
        with pytest.raises(ToolExecutionError, match="cannot run"):
            context_module.run_command([str(tmp_path / "missing")], tmp_path, {}, 5)


def test_pinned_version_constant_matches_fixture() -> None:
    """The shared fixture pins the version the bundled digests cover."""
    assert PINNED == "0.20.0"
    assert family(location("a.py"))["witness"] == "copy-paste"
