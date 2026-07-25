"""Tests for the ambrleaks CLI error boundary and path handling."""

from __future__ import annotations

import typing as typ

import pytest

from df12_python_lints.ambrleaks import DEFAULT_RULES, main, scan_file, shannon_entropy

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

_SNAPSHOT = """\
# serializer version: 1
# name: test_user
  dict({
    'email': 'alice@realcorp.io',
  })
# ---
"""


class TestConfigErrors:
    """Exercise the CLI's configuration and I/O error boundary."""

    @pytest.mark.parametrize(
        ("content", "fragment"),
        [
            ("rules = 5\n", "[rules] must be a table"),
            ("[rules]\nsnapshot-phone = true\n", "must be a table"),
            ('[rules.snapshot-phone]\nenabled = "yes"\n', "must be a boolean"),
            ("allowlist = 3\n", "[allowlist] must be a table"),
            ("[allowlist]\ntests = [1]\n", "list of strings"),
            ('[allowlist]\nvalues = "x"\n', "list of strings"),
        ],
    )
    def test_invalid_config_shapes_exit_two(
        self,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture[str],
        content: str,
        fragment: str,
    ) -> None:
        """Structurally invalid configuration reports an error and exits 2."""
        config_path = tmp_path / "ambrleaks.toml"
        config_path.write_text(content, encoding="utf-8")
        exit_code = main([str(tmp_path), "--config", str(config_path)])
        captured = capsys.readouterr()
        assert exit_code == 2, "invalid configuration must exit 2"
        assert "ambrleaks: error:" in captured.err, "errors must go to stderr"
        assert fragment in captured.err, "the message must name the problem"

    def test_invalid_toml_syntax_exits_two(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Unparseable TOML reports an error rather than a traceback."""
        config_path = tmp_path / "ambrleaks.toml"
        config_path.write_text("not = [toml\n", encoding="utf-8")
        exit_code = main([str(tmp_path), "--config", str(config_path)])
        assert exit_code == 2, "TOML syntax errors must exit 2"
        assert "ambrleaks: error:" in capsys.readouterr().err, (
            "TOML errors must be reported to stderr"
        )

    def test_missing_config_file_exits_two(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A nonexistent --config path reports an error and exits 2."""
        exit_code = main([str(tmp_path), "--config", str(tmp_path / "absent.toml")])
        assert exit_code == 2, "an unreadable configuration must exit 2"
        assert "ambrleaks: error:" in capsys.readouterr().err, (
            "filesystem errors must be reported to stderr"
        )

    def test_corrupt_baseline_exits_two(
        self,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture[str],
        write_snapshot: cabc.Callable[[pathlib.Path, str], pathlib.Path],
    ) -> None:
        """A baseline that is not valid JSON reports an error and exits 2."""
        write_snapshot(tmp_path, _SNAPSHOT)
        baseline = tmp_path / "baseline.json"
        baseline.write_text("not json", encoding="utf-8")
        exit_code = main([str(tmp_path), "--baseline", str(baseline)])
        assert exit_code == 2, "a corrupt baseline must exit 2"
        assert "ambrleaks: error:" in capsys.readouterr().err, (
            "baseline errors must be reported to stderr"
        )


class TestDiscoveryAndPaths:
    """Exercise path discovery and canonicalization."""

    def test_scans_explicit_file_argument(
        self,
        tmp_path: pathlib.Path,
        write_snapshot: cabc.Callable[[pathlib.Path, str], pathlib.Path],
    ) -> None:
        """A direct .ambr file argument is scanned without discovery."""
        path = write_snapshot(tmp_path, _SNAPSHOT)
        assert main([str(path)]) == 1, "a directly named file must be scanned"

    def test_default_config_discovered_from_cwd(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        write_snapshot: cabc.Callable[[pathlib.Path, str], pathlib.Path],
    ) -> None:
        """An ambrleaks.toml in the working directory is picked up."""
        write_snapshot(tmp_path, _SNAPSHOT)
        (tmp_path / "ambrleaks.toml").write_text(
            '[allowlist]\ntests = ["test_user*"]\n', encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        assert main(["."]) == 0, "the conventional config file must be honoured"

    def test_cli_reports_working_directory_relative_paths(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        write_snapshot: cabc.Callable[[pathlib.Path, str], pathlib.Path],
    ) -> None:
        """Resolve the base directory from cwd once and report relatively.

        The CLI renders findings beneath the working directory relative to
        it. The scanner core no longer consults the working directory; this
        cwd-relative rendering is a property of the CLI boundary, which
        injects ``Path.cwd()`` as the base directory.
        """
        write_snapshot(tmp_path, _SNAPSHOT)
        monkeypatch.chdir(tmp_path)
        assert main(["."]) == 1, "the seeded snapshot must produce findings"
        out = capsys.readouterr().out
        assert "__snapshots__/test_demo.ambr:" in out, (
            "paths under the working directory must be reported relative to it"
        )


def test_entropy_of_empty_text_is_zero() -> None:
    """The entropy gate treats empty text as zero entropy."""
    assert abs(shannon_entropy("")) < 1e-12, "empty text must score zero entropy"


class TestScanBoundaries:
    """Exercise decode failures and base-directory injection."""

    def test_invalid_utf8_snapshot_exits_two(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A snapshot that is not valid UTF-8 reports an error, exits 2."""
        snapshot_dir = tmp_path / "__snapshots__"
        snapshot_dir.mkdir()
        (snapshot_dir / "test_demo.ambr").write_bytes(b"# name: t\n\xff\xfe\n")
        exit_code = main([str(tmp_path)])
        assert exit_code == 2, "invalid UTF-8 input must exit 2"
        assert "ambrleaks: error:" in capsys.readouterr().err, (
            "decode errors must be reported to stderr"
        )

    def test_scan_file_honours_injected_base_dir(
        self,
        tmp_path: pathlib.Path,
        write_snapshot: cabc.Callable[[pathlib.Path, str], pathlib.Path],
    ) -> None:
        """Paths are canonicalized against the injected base directory."""
        path = write_snapshot(tmp_path, _SNAPSHOT)
        findings = scan_file(path, DEFAULT_RULES, base_dir=tmp_path)
        assert findings, "the seeded snapshot must produce findings"
        assert all(
            finding.path == "__snapshots__/test_demo.ambr" for finding in findings
        ), "paths must be rendered relative to the injected base directory"
