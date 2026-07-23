"""Tests for the ambrleaks snapshot scanner and its CLI."""

from __future__ import annotations

import json
import typing as typ

from df12_python_lints.ambrleaks import DEFAULT_RULES, main, scan_file
from df12_python_lints.ambrleaks.cli import (
    default_config,
    load_config,
    select_rules,
)

if typ.TYPE_CHECKING:
    import pathlib

    import pytest

_HIGH_ENTROPY_HEX = "0123456789abcdef0123456789abcdef"

_SNAPSHOT = f"""\
# serializer version: 1
# name: test_user
  dict({{
    'email': 'alice@realcorp.io',
    'id': '{_HIGH_ENTROPY_HEX}',
    'homepage': 'https://realcorp.io/alice',
    'workspace': '/home/alice/projects/demo',
  }})
# ---
# name: test_clean
  dict({{
    'email': 'bob@example.com',
    'docs': 'https://example.com/docs',
    'low_entropy': '{"a" * 32}',
  }})
# ---
"""


def _write_snapshot(directory: pathlib.Path, content: str) -> pathlib.Path:
    """Write *content* as a snapshot file and return its path."""
    snapshot_dir = directory / "__snapshots__"
    snapshot_dir.mkdir()
    path = snapshot_dir / "test_demo.ambr"
    path.write_text(content, encoding="utf-8")
    return path


class TestScanner:
    """Exercise detection and attribution over the Amber format."""

    def test_detects_and_attributes_findings(self, tmp_path: pathlib.Path) -> None:
        """Each unredacted value is reported against its test block."""
        path = _write_snapshot(tmp_path, _SNAPSHOT)
        findings = scan_file(path, DEFAULT_RULES)
        reported = {(f.rule_id, f.test_name) for f in findings}
        expected = {
            ("snapshot-email", "test_user"),
            ("snapshot-hex", "test_user"),
            ("snapshot-url", "test_user"),
            ("snapshot-posix-path", "test_user"),
        }
        assert reported == expected, "findings must match the seeded values"

    def test_allowlists_and_entropy_suppress_noise(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Example domains and low-entropy hex are not reported."""
        path = _write_snapshot(tmp_path, _SNAPSHOT)
        findings = scan_file(path, DEFAULT_RULES)
        clean_block = [f for f in findings if f.test_name == "test_clean"]
        assert not clean_block, "allowlisted and low-entropy values must pass"

    def test_control_lines_are_never_scanned(self, tmp_path: pathlib.Path) -> None:
        """Values in column-zero comment lines are ignored."""
        content = (
            "# serializer version: 1\n"
            f"# name: test_{_HIGH_ENTROPY_HEX}\n"
            "  'clean body'\n"
            "# ---\n"
        )
        path = _write_snapshot(tmp_path, content)
        assert not scan_file(path, DEFAULT_RULES), (
            "control lines must not produce findings"
        )

    def test_phone_rule_is_opt_in(self, tmp_path: pathlib.Path) -> None:
        """The E.164 rule stays off until enabled in configuration."""
        content = "# name: test_contact\n  'phone': '+442071234567'\n# ---\n"
        path = _write_snapshot(tmp_path, content)
        default_findings = scan_file(path, select_rules(default_config()))
        assert not default_findings, "phone detection must be opt-in"


class TestCli:
    """Exercise configuration, baselining, and exit codes."""

    def test_reports_findings_with_exit_code_one(self, tmp_path: pathlib.Path) -> None:
        """A dirty tree exits nonzero and prints each finding."""
        _write_snapshot(tmp_path, _SNAPSHOT)
        assert main([str(tmp_path)]) == 1, "findings must fail the run"

    def test_clean_tree_exits_zero(self, tmp_path: pathlib.Path) -> None:
        """A tree without .ambr files passes."""
        assert main([str(tmp_path)]) == 0, "a clean tree must pass"

    def test_config_enables_phone_rule(self, tmp_path: pathlib.Path) -> None:
        """A configuration override switches the phone rule on."""
        config_path = tmp_path / "ambrleaks.toml"
        config_path.write_text(
            "[rules.snapshot-phone]\nenabled = true\n", encoding="utf-8"
        )
        config = load_config(config_path)
        rule_ids = {rule.rule_id for rule in select_rules(config)}
        assert "snapshot-phone" in rule_ids, "override must enable the rule"

    def test_config_allowlist_suppresses_by_test_name(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A test-name glob in the configuration suppresses findings."""
        _write_snapshot(tmp_path, _SNAPSHOT)
        config_path = tmp_path / "ambrleaks.toml"
        config_path.write_text(
            '[allowlist]\ntests = ["test_user*"]\n', encoding="utf-8"
        )
        exit_code = main([str(tmp_path), "--config", str(config_path)])
        assert exit_code == 0, "allowlisted tests must not fail the run"

    def test_baseline_grandfathers_existing_findings(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Baselined findings pass; a new finding still fails."""
        path = _write_snapshot(tmp_path, _SNAPSHOT)
        baseline = tmp_path / "baseline.json"
        assert main([str(tmp_path), "--write-baseline", str(baseline)]) == 0, (
            "writing a baseline must succeed"
        )
        fingerprints = json.loads(baseline.read_text(encoding="utf-8"))
        assert fingerprints, "the baseline must record the seeded findings"
        assert main([str(tmp_path), "--baseline", str(baseline)]) == 0, (
            "baselined findings must not fail the run"
        )
        extra = "# name: test_new\n  'contact': 'carol@realcorp.io'\n# ---\n"
        path.write_text(_SNAPSHOT + extra, encoding="utf-8")
        assert main([str(tmp_path), "--baseline", str(baseline)]) == 1, (
            "a new finding must fail despite the baseline"
        )

    def test_baseline_preserves_duplicate_multiplicity(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Each baselined occurrence suppresses exactly one finding.

        Fingerprints exclude line numbers, so a repeated value in one
        block shares a fingerprint; an extra occurrence beyond the
        baselined count must still fail the scan.
        """
        duplicated = (
            "# name: test_contacts\n"
            "  'primary': 'carol@realcorp.io'\n"
            "  'backup': 'carol@realcorp.io'\n"
            "# ---\n"
        )
        path = _write_snapshot(tmp_path, duplicated)
        baseline = tmp_path / "baseline.json"
        assert main([str(tmp_path), "--write-baseline", str(baseline)]) == 0, (
            "writing a baseline must succeed"
        )
        fingerprints = json.loads(baseline.read_text(encoding="utf-8"))
        assert len(fingerprints) == 2, (
            "the baseline must record one entry per occurrence"
        )
        assert main([str(tmp_path), "--baseline", str(baseline)]) == 0, (
            "an unchanged snapshot with the same occurrence count must pass"
        )
        tripled = duplicated.replace(
            "# ---\n", "  'escalation': 'carol@realcorp.io'\n# ---\n"
        )
        path.write_text(tripled, encoding="utf-8")
        capsys.readouterr()
        assert main([str(tmp_path), "--baseline", str(baseline)]) == 1, (
            "an occurrence beyond the baselined count must fail"
        )
        reported = capsys.readouterr().out.strip().splitlines()
        assert len(reported) == 1, "exactly the surplus occurrence must be reported"
