"""The Skylos adapter: pin, runtime checks, command shape and outcome mapping."""

from __future__ import annotations

import importlib.metadata
import pathlib
import typing as typ

import pytest
from skylos_support import PIN, FakeRunner, context_for, make_repository, probe

from df12_python_lints._errors import ToolConfigError, ToolExecutionError
from df12_python_lints._runtime import CommandResult, Streams
from df12_python_lints.skylos import backend, commands
from df12_python_lints.skylos.settings import ScanSettings

if typ.TYPE_CHECKING:
    import io

_SETTINGS = ScanSettings(roots=("a", "b/c.py"), python=(3, 14))


class TestPin:
    """The package metadata is the one authoritative pin."""

    def test_pin_is_read_from_the_skylos_extra(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the exact ``==`` requirement of the skylos extra counts."""
        monkeypatch.setattr(
            importlib.metadata,
            "requires",
            lambda _name: [
                "tomlkit<1,>=0.13; extra == 'duplication'",
                "tomlkit<1,>=0.13; extra == 'skylos'",
                "skylos==9.8.7; extra == 'skylos'",
                "pylint<5,>=3.3",
            ],
        )
        assert backend.pinned_version() == "9.8.7"

    @pytest.mark.parametrize(
        "requirements",
        [
            [],
            ["pylint<5"],
            ["skylos>=4; extra == 'skylos'"],
            ["skylos~=4.33; extra == 'skylos'"],
        ],
    )
    def test_a_missing_or_loose_pin_is_an_error(
        self, monkeypatch: pytest.MonkeyPatch, requirements: list[str]
    ) -> None:
        """A range is not an authoritative pin."""
        monkeypatch.setattr(importlib.metadata, "requires", lambda _name: requirements)
        with pytest.raises(ToolExecutionError, match="does not pin an exact version"):
            backend.pinned_version()

    def test_real_metadata_pins_a_version(self) -> None:
        """The shipped extra pins an exact release."""
        assert backend.pinned_version() == PIN

    def test_installed_version_is_none_when_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing distribution is reported as absent, not an exception."""

        def missing(_name: str) -> str:
            """Pretend the distribution is not installed."""
            raise importlib.metadata.PackageNotFoundError

        monkeypatch.setattr(importlib.metadata, "version", missing)
        assert backend.installed_version() is None


class TestVerification:
    """Backend and interpreter are verified before any analysis."""

    def test_matching_backend_and_interpreter_pass(self) -> None:
        """The description names backend and interpreter."""
        assert (
            backend.verify_backend(_SETTINGS, probe())
            == f"skylos {PIN} under Python 3.14+"
        )

    def test_older_interpreter_is_rejected_with_the_way_to_select_one(self) -> None:
        """A scan that cannot parse the syntax must not run."""
        with pytest.raises(
            ToolExecutionError, match=r"requires 3\.14 or newer.*--python 3\.14"
        ):
            backend.verify_backend(_SETTINGS, probe(interpreter=(3, 13)))

    def test_missing_backend_gives_an_install_hint(self) -> None:
        """No Skylos means an actionable provisioning message."""
        with pytest.raises(ToolExecutionError, match=r"not installed.*\[skylos\]"):
            backend.verify_backend(_SETTINGS, probe(installed=None))

    def test_wrong_backend_version_is_pin_drift(self) -> None:
        """An installed Skylos that differs from the pin is rejected."""
        with pytest.raises(
            ToolExecutionError,
            match=r"4\.40\.0 is installed but this package pins 4\.33\.2",
        ):
            backend.verify_backend(_SETTINGS, probe(installed="4.40.0"))


class TestCommand:
    """One argument vector, in the pinned release's order."""

    def test_order_roots_and_local_only_flags(self) -> None:
        """``--config-file`` precedes the roots and the scan options follow."""
        command = backend.build_command(
            "py", pathlib.Path("/r/pyproject.toml"), _SETTINGS
        )
        assert command[:3] == ["py", "-c", backend._BOOTSTRAP]
        assert command[3:8] == [
            "--config-file",
            "/r/pyproject.toml",
            "a",
            "b/c.py",
            "--category",
        ]
        assert command[7:] == [
            "--category", "dead_code", "--gate", "--format", "concise",
            "--no-upload", "--no-provenance", "--no-grep-verify",
        ]  # fmt: skip

    def test_command_never_requests_uploads_or_verification(self) -> None:
        """Flags that would contact a service are absent."""
        command = backend.build_command("py", pathlib.Path("/p"), _SETTINGS)
        assert not {"--upload", "--verify", "--llm", "--model", "--sca"} & set(command)

    def test_all_roots_share_one_invocation(self, tmp_path: pathlib.Path) -> None:
        """Cross-root references need one scan, not one per root."""
        repo = make_repository(
            tmp_path,
            policy=(
                "[tool.skylos.gate]\nstrict = true\n[tool.df12_skylos]\n"
                'roots = ["pkg", "pkg"]\npython = "3.12"\n'
            ),
        )
        runner = FakeRunner()
        commands.run_check(context_for(repo, runner), Streams(_sink(), _sink()))
        assert len(runner.calls) == 1, "exactly one scan"
        assert runner.calls[0][1] == repo.resolve(), "explicit working directory"


def _sink() -> io.StringIO:
    """Return an in-memory text stream."""
    import io

    return io.StringIO()


class TestOutcomeMapping:
    """Failed analysis can never become a clean gate."""

    @pytest.mark.parametrize(("status", "expected"), [(0, "clean"), (1, "blocking")])
    def test_success_and_blocking_stay_what_they_are(
        self, status: int, expected: str
    ) -> None:
        """Success remains success and a blocking result remains blocking."""
        assert backend.classify(CommandResult(status, "", "")) == expected

    def test_status_two_is_a_failed_analysis(self) -> None:
        """An invalid configuration or incomplete analysis is an error."""
        with pytest.raises(ToolExecutionError, match="never a clean gate"):
            backend.classify(
                CommandResult(
                    2, "pkg/x.py:1  SKY-ANALYSIS-INCOMPLETE  invalid syntax", ""
                )
            )

    @pytest.mark.parametrize("status", [3, 127, -9])
    def test_unexpected_statuses_are_errors(self, status: int) -> None:
        """Anything outside the documented statuses fails closed."""
        with pytest.raises(ToolExecutionError, match="unexpected status"):
            backend.classify(CommandResult(status, "", ""))

    def test_zero_exit_with_an_empty_root_warning_is_not_clean(self) -> None:
        """Skylos logs, rather than fails, when a root has no Python files."""
        stderr = "2026-10-11 - WARNING - No Python files found in pkg\n"
        with pytest.raises(ToolConfigError, match=r"no Python files .*pkg"):
            backend.classify(CommandResult(0, "", stderr))

    def test_unrelated_stderr_does_not_block_a_clean_scan(self) -> None:
        """Ordinary log lines are not mistaken for the empty-root warning."""
        assert (
            backend.classify(CommandResult(0, "", "INFO - scanned 3 files\n"))
            == "clean"
        )
