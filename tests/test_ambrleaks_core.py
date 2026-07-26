"""Unit tests for the pure ambrleaks core APIs.

These exercise the filesystem-free cores directly — :func:`scan_text`,
:func:`parse_config`, and :func:`apply_baseline` — so their behaviour is
pinned without going through a file or the process working directory.
The matching boundary functions (:func:`scan_file`, :func:`read_config`,
:func:`read_baseline`) are covered where they add filesystem semantics,
and the CLI's error boundary is exercised in ``test_ambrleaks_cli``.
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import tomllib
import typing as typ

import pytest

from df12_python_lints.ambrleaks import DEFAULT_RULES, Finding, scan_file, scan_text
from df12_python_lints.ambrleaks.cli import (
    _masked_value,
    apply_baseline,
    write_baseline,
)
from df12_python_lints.ambrleaks.config import (
    ConfigError,
    default_config,
    parse_config,
    read_config,
    select_rules,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_EMAIL_BLOCK = "# name: test_user\n  'email': 'alice@realcorp.io'\n# ---\n"


class TestScanText:
    """Exercise the pure scanning core over in-memory text."""

    def test_scans_supplied_text_without_a_file(self) -> None:
        """A finding is attributed to its block without any file read."""
        findings = scan_text(
            _EMAIL_BLOCK,
            pathlib.Path("t.ambr"),
            DEFAULT_RULES,
            base_dir=pathlib.Path("/repo"),
        )
        reported = {(f.rule_id, f.test_name, f.value) for f in findings}
        assert ("snapshot-email", "test_user", "alice@realcorp.io") in reported, (
            "scan_text must attribute findings to the enclosing block"
        )

    def test_control_lines_are_not_scanned(self) -> None:
        """Column-zero comment lines never contribute findings."""
        text = "# name: test_x\n  'clean body'\n# ---\n"
        findings = scan_text(
            text, pathlib.Path("t.ambr"), DEFAULT_RULES, base_dir=pathlib.Path("/repo")
        )
        assert not findings, "control lines must not produce findings"

    def test_output_is_independent_of_working_directory(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A relative path is anchored to base_dir, never to cwd.

        Scanning identical text with the same base directory yields the
        same canonical path regardless of the process working directory,
        so the scanner core cannot silently derive output paths from a
        changed cwd.
        """
        relative = pathlib.Path("pkg/__snapshots__/t.ambr")
        first = scan_text(_EMAIL_BLOCK, relative, DEFAULT_RULES, base_dir=tmp_path)
        elsewhere = tmp_path / "nested"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        second = scan_text(_EMAIL_BLOCK, relative, DEFAULT_RULES, base_dir=tmp_path)
        assert first == second, "cwd must not affect scan_text output"
        assert all(f.path == "pkg/__snapshots__/t.ambr" for f in first), (
            "a relative path must be rendered against the injected base_dir"
        )

    def test_scan_file_requires_an_injected_base_dir(
        self,
        tmp_path: pathlib.Path,
        write_snapshot: cabc.Callable[[pathlib.Path, str], pathlib.Path],
    ) -> None:
        """The scanner boundary has no working-directory fallback."""
        path = write_snapshot(tmp_path, _EMAIL_BLOCK)
        with pytest.raises(TypeError):
            # base_dir is required; omitting it must raise rather than
            # silently fall back to the working directory.
            scan_file(path, DEFAULT_RULES)  # ty: ignore[missing-argument]


class TestParseConfig:
    """Exercise the pure TOML configuration parser."""

    def test_parses_rule_states_and_allowlists(self) -> None:
        """Rule overrides and allowlists are read from literal TOML."""
        config = parse_config(
            "[rules.snapshot-phone]\n"
            "enabled = true\n"
            "[allowlist]\n"
            'values = ["secret"]\n'
            'tests = ["test_*"]\n'
            'paths = ["*/__snapshots__/*"]\n'
        )
        assert ("snapshot-phone", True) in config.rule_states, (
            "an enabled override must be recorded"
        )
        assert config.allow_values == ("secret",)
        assert config.allow_tests == ("test_*",)
        assert config.allow_paths == ("*/__snapshots__/*",)
        assert "snapshot-phone" in {rule.rule_id for rule in select_rules(config)}, (
            "select_rules must honour the parsed override"
        )

    def test_empty_text_yields_default_shaped_config(self) -> None:
        """Empty TOML parses to empty overrides and allowlists."""
        assert parse_config("") == default_config(), (
            "empty configuration must match the defaults"
        )

    def test_ignores_unknown_allowlist_fields(self) -> None:
        """Unrecognised ``[allowlist]`` keys are ignored, not rejected."""
        config = parse_config('[allowlist]\nunknown = 5\ntests = ["t"]\n')
        assert config.allow_tests == ("t",), (
            "recognised fields must still parse alongside an ignored key"
        )

    @pytest.mark.parametrize(
        ("text", "fragment"),
        [
            ("rules = 5\n", "[rules] must be a table"),
            ("[rules]\nsnapshot-phone = true\n", "must be a table"),
            ('[rules.snapshot-phone]\nenabled = "yes"\n', "must be a boolean"),
            ("allowlist = 3\n", "[allowlist] must be a table"),
            ("[allowlist]\ntests = [1]\n", "list of strings"),
            ('[allowlist]\nvalues = "x"\n', "list of strings"),
            ("[allowlist]\npaths = [1]\n", "list of strings"),
        ],
    )
    def test_invalid_shapes_raise_config_error(self, text: str, fragment: str) -> None:
        """Structurally invalid configuration raises ConfigError."""
        with pytest.raises(ConfigError, match=re.escape(fragment)):
            parse_config(text)

    def test_malformed_toml_raises_decode_error(self) -> None:
        """Unparseable TOML surfaces as a TOMLDecodeError, not ConfigError."""
        with pytest.raises(tomllib.TOMLDecodeError):
            parse_config("not = [toml\n")


class TestReadConfig:
    """Exercise the configuration filesystem boundary."""

    def test_none_path_returns_defaults(self) -> None:
        """A ``None`` path is the no-configuration case."""
        assert read_config(None) == default_config(), (
            "the absent-config case must return the defaults"
        )

    def test_missing_file_raises_oserror(self, tmp_path: pathlib.Path) -> None:
        """An unreadable path raises OSError for the CLI to report."""
        # A missing file may surface as any OSError subtype (usually
        # FileNotFoundError); the boundary contract is only "an OSError".
        with pytest.raises(OSError):  # ruff:ignore[pytest-raises-too-broad]
            read_config(tmp_path / "absent.toml")

    def test_reads_and_parses_a_file(self, tmp_path: pathlib.Path) -> None:
        """The boundary delegates decoding to the pure parser."""
        config_path = tmp_path / "ambrleaks.toml"
        config_path.write_text(
            "[rules.snapshot-phone]\nenabled = true\n", encoding="utf-8"
        )
        assert ("snapshot-phone", True) in read_config(config_path).rule_states, (
            "read_config must return the parsed overrides"
        )


class TestApplyBaseline:
    """Exercise the streaming baseline-suppression core."""

    @staticmethod
    def _finding() -> Finding:
        """Return a representative finding for baseline assertions."""
        return Finding("p", 1, "test_user", "snapshot-email", "alice@realcorp.io")

    def test_suppresses_one_finding_per_recorded_occurrence(self) -> None:
        """A fingerprint recorded once suppresses exactly one finding."""
        finding = self._finding()
        accepted = {finding.fingerprint(): 1}
        remaining = list(apply_baseline([finding, finding], accepted))
        assert remaining == [finding], (
            "only the surplus occurrence must survive the baseline"
        )

    def test_unlisted_findings_are_kept(self) -> None:
        """Findings absent from the baseline are never dropped."""
        finding = self._finding()
        assert list(apply_baseline([finding], {})) == [finding], (
            "an empty baseline must keep every finding"
        )

    def test_does_not_mutate_the_supplied_mapping(self) -> None:
        """The core leaves its accepted-count mapping untouched."""
        finding = self._finding()
        accepted = collections.Counter({finding.fingerprint(): 2})
        list(apply_baseline([finding], accepted))
        assert accepted[finding.fingerprint()] == 2, (
            "apply_baseline must not consume the caller's counts"
        )

    def test_yields_surplus_before_consuming_the_rest(self) -> None:
        """A surplus finding is yielded before later input is read."""
        surplus = self._finding()
        sentinel = Finding("q", 9, "test_late", "snapshot-hex", "deadbeef")
        consumed: list[Finding] = []

        def _source() -> cabc.Iterator[Finding]:
            """Record each finding into ``consumed`` as it is pulled."""
            consumed.append(surplus)
            yield surplus
            consumed.append(sentinel)
            yield sentinel

        # An empty baseline grandfathers nothing, so every finding survives.
        survivors = apply_baseline(_source(), {})
        first = next(survivors)
        assert first is surplus, "the first survivor must arrive first"
        assert consumed == [surplus], (
            "suppression must yield the first survivor before reading the rest"
        )


class TestWriteBaseline:
    """Exercise the streaming baseline writer."""

    @staticmethod
    def _finding() -> Finding:
        """Return a representative finding for baseline assertions."""
        return Finding("p", 1, "test_user", "snapshot-email", "alice@realcorp.io")

    def test_writes_one_entry_per_occurrence_from_an_iterator(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A single-use iterator is consumed into a valid JSON array."""
        finding = self._finding()

        def _source() -> cabc.Iterator[Finding]:
            """Yield the same finding twice as a single-use iterator."""
            yield finding
            yield finding

        out = tmp_path / "baseline.json"
        written = write_baseline(out, _source())
        assert written == 2, "each occurrence must produce one entry"
        recorded = json.loads(out.read_text(encoding="utf-8"))
        assert recorded == [finding.fingerprint(), finding.fingerprint()], (
            "the baseline must be a JSON array with one entry per occurrence"
        )

    def test_empty_stream_writes_an_empty_json_array(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An empty scan writes a valid empty JSON array."""
        out = tmp_path / "baseline.json"
        written = write_baseline(out, iter(()))
        assert written == 0, "an empty scan writes nothing"
        assert json.loads(out.read_text(encoding="utf-8")) == [], (
            "an empty baseline must be a valid empty JSON array"
        )

    def test_write_failure_removes_temp_file_and_propagates(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A mid-write failure leaves no baseline or temporary file behind."""
        finding = self._finding()

        class _WriteError(Exception):
            """Marker error raised while the baseline is being written."""

        def _source() -> cabc.Iterator[Finding]:
            """Yield one finding, then fail before the stream completes."""
            yield finding
            raise _WriteError

        out = tmp_path / "baseline.json"
        with pytest.raises(_WriteError):
            write_baseline(out, _source())
        assert not out.exists(), "a failed write must not leave a baseline file"
        assert not list(tmp_path.iterdir()), (
            "the temporary file must be removed when the write fails"
        )


class TestMaskedValue:
    """Exercise the default finding-value masking."""

    def test_masks_interior_of_a_long_value(self) -> None:
        """Only the first and last character of a long value survive."""
        assert _masked_value("alice@realcorp.io") == "a***************o", (
            "the interior of a long value must be masked"
        )

    def test_masks_a_short_value_entirely(self) -> None:
        """A value of three characters or fewer reveals nothing."""
        assert _masked_value("ab") == "**", "short values must be fully masked"
