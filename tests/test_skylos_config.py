"""Native ``[tool.skylos]`` validation and the wrapper-owned table."""

from __future__ import annotations

import tomllib
import typing as typ

import pytest
from skylos_support import POLICY, make_repository

from df12_python_lints._errors import ToolConfigError
from df12_python_lints.skylos.config import validate_native
from df12_python_lints.skylos.settings import ScanSettings, load_scan_settings

if typ.TYPE_CHECKING:
    import pathlib


def _validate(text: str) -> tuple[str, ...]:
    """Validate a manifest given as TOML text."""
    return validate_native(tomllib.loads(text))


_STRICT = "[tool.skylos.gate]\nstrict = true\n"


class TestGate:
    """The strict gate is required: a lax gate exits zero with findings."""

    def test_strict_gate_is_valid(self) -> None:
        """A strict gate with nothing else is valid and warning-free."""
        assert not _validate(_STRICT), "no warnings expected"

    @pytest.mark.parametrize(
        ("text", "fragment"),
        [
            ("[project]\nname = 'x'\n", "tool.skylos is required"),
            ("[tool.skylos]\n", "tool.skylos.gate"),
            ("[tool.skylos.gate]\nstrict = false\n", "strict must be true"),
            ("[tool.skylos.gate]\nstrict = 'yes'\n", "strict must be true"),
            ("[tool.skylos.gate]\n", "strict must be true"),
            ("[tool.skylos]\ngate = 3\n", "tool.skylos.gate"),
            (_STRICT + "[tool.skylos]\nexclude = 'tests'\n", "exclude"),
        ],
    )
    def test_invalid_gate_or_exclude_is_rejected(
        self, text: str, fragment: str
    ) -> None:
        """Each broken shape names the offending key."""
        with pytest.raises(ToolConfigError, match=fragment):
            _validate(text)


class TestDocumentedWhitelist:
    """Documented exceptions need a non-blank reason; names are only advised."""

    def test_documented_entries_with_reasons_are_valid(self) -> None:
        """A reasoned entry passes."""
        text = (
            _STRICT
            + '[tool.skylos.whitelist.documented]\n_write_mode = "Read at runtime."\n'
        )
        assert not _validate(text), "no warnings expected"

    @pytest.mark.parametrize("reason", ['""', '"  "', "3", "true"])
    def test_blank_or_non_string_reasons_are_rejected(self, reason: str) -> None:
        """Every documented exception must record a textual reason."""
        text = _STRICT + f"[tool.skylos.whitelist.documented]\nname = {reason}\n"
        with pytest.raises(ToolConfigError, match="reason"):
            _validate(text)

    def test_undocumented_names_are_an_advisory_not_an_error(self) -> None:
        """Existing undocumented names keep working but are flagged."""
        text = _STRICT + '[tool.skylos.whitelist]\nnames = ["legacy"]\n'
        warnings = _validate(text)
        assert len(warnings) == 1
        assert "no reason" in warnings[0]

    @pytest.mark.parametrize(
        "text",
        [
            _STRICT + "[tool.skylos]\nwhitelist = ['a']\n",
            _STRICT + "[tool.skylos.whitelist]\nnames = 'a'\n",
            _STRICT + "[tool.skylos.whitelist]\nnames = [1]\n",
            _STRICT + "[tool.skylos.whitelist]\ndocumented = 3\n",
        ],
    )
    def test_malformed_whitelist_shapes_are_rejected(self, text: str) -> None:
        """Wrong container shapes are refused rather than ignored."""
        with pytest.raises(ToolConfigError):
            _validate(text)


class TestRuntimeEntryPoints:
    """Typed runtime entry-point exemptions stay distinct and reasoned."""

    _OK = (
        '[[tool.skylos.dead_code.entrypoints]]\ntype = "method"\n'
        'full_name = ["pkg.A.run"]\nreason = "The framework calls run."\n'
    )

    def test_typed_reasoned_rule_is_valid(self) -> None:
        """A complete rule passes without warnings."""
        assert not _validate(_STRICT + self._OK), "no warnings expected"

    def test_rule_without_type_is_valid_but_advised(self) -> None:
        """Native Skylos accepts a typeless rule; the contract advises one."""
        text = (
            _STRICT
            + "[[tool.skylos.dead_code.entrypoints]]\n"
            + 'full_name = "pkg.f"\nreason = "r"\n'
        )
        assert "no type" in _validate(text)[0]

    @pytest.mark.parametrize(
        ("body", "fragment"),
        [
            ('type = "method"\nfull_name = "a.b"', "reason"),
            ('type = "method"\nfull_name = "a.b"\nreason = ""', "reason"),
            ('type = "method"\nreason = "r"', "selects nothing"),
            ('type = "method"\nfull_name = []\nreason = "r"', "full_name"),
            ('type = "method"\nfull_name = [1]\nreason = "r"', "full_name"),
            ('type = 3\nfull_name = "a.b"\nreason = "r"', "type"),
            ('type = "  "\nfull_name = "a.b"\nreason = "r"', "type"),
            ('type = "method"\nfull_name = "a.b"\nreason = "r"\nparent = 3', "parent"),
        ],
    )
    def test_invalid_rules_are_rejected_naming_the_key(
        self, body: str, fragment: str
    ) -> None:
        """A rule that Skylos would silently drop is an error here."""
        text = _STRICT + f"[[tool.skylos.dead_code.entrypoints]]\n{body}\n"
        with pytest.raises(ToolConfigError, match=fragment):
            _validate(text)

    def test_entrypoints_must_be_an_array_of_tables(self) -> None:
        """A table where an array belongs is rejected."""
        text = _STRICT + "[tool.skylos.dead_code]\nentrypoints = 'x'\n"
        with pytest.raises(ToolConfigError, match="array of tables"):
            _validate(text)

    def test_parent_only_selector_counts(self) -> None:
        """A rule selecting through its parent class is a real selector."""
        text = _STRICT + (
            '[[tool.skylos.dead_code.entrypoints]]\ntype = "method"\nreason = "r"\n'
            'parent = { name = "Main" }\n'
        )
        assert not _validate(text), "no warnings expected"

    def test_whitelist_and_entrypoints_are_validated_together(self) -> None:
        """Both kinds of exception may coexist and stay separate."""
        text = _STRICT + self._OK + '[tool.skylos.whitelist.documented]\nx = "why"\n'
        assert not _validate(text), "no warnings expected"


class TestScanSettings:
    """The wrapper table holds only execution metadata."""

    def _load(self, tmp_path: pathlib.Path, policy: str) -> ScanSettings:
        """Load the settings of a repository holding ``policy``."""
        repo = make_repository(tmp_path, policy=policy)
        data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
        return load_scan_settings(data, repository=repo)

    def test_valid_table(self, tmp_path: pathlib.Path) -> None:
        """Roots and the minimum interpreter are read."""
        settings = self._load(tmp_path, POLICY)
        assert settings.roots == ("pkg",)
        assert settings.python == (3, 12)

    @pytest.mark.parametrize(
        ("old", "new", "fragment"),
        [
            ('roots = ["pkg"]', "roots = []", "must not be empty"),
            ('roots = ["pkg"]', 'roots = ["/etc"]', "repository-relative"),
            ('roots = ["pkg"]', 'roots = ["../x"]', "repository-relative"),
            ('roots = ["pkg"]', 'roots = ["missing"]', "does not exist"),
            ('roots = ["pkg"]', 'roots = ["-x"]', "must not start with"),
            ('python = "3.12"', 'python = "3"', "major.minor"),
            ('python = "3.12"', "python = 3.12", "non-empty string"),
            ('python = "3.12"', 'python = "3.12"\nthreshold = 3', "unsupported keys"),
        ],
    )
    def test_invalid_table_is_rejected(
        self, tmp_path: pathlib.Path, old: str, new: str, fragment: str
    ) -> None:
        """Each invalid value names its key."""
        with pytest.raises(ToolConfigError, match=fragment):
            self._load(tmp_path, POLICY.replace(old, new))

    def test_missing_table_is_rejected(self, tmp_path: pathlib.Path) -> None:
        """Without the wrapper table the roots are unknown."""
        with pytest.raises(ToolConfigError, match=r"tool\.df12_skylos"):
            self._load(tmp_path, "[tool.skylos.gate]\nstrict = true\n")

    def test_python_must_be_required_even_when_roots_are_given(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The scan interpreter is never defaulted."""
        with pytest.raises(ToolConfigError, match="python"):
            self._load(tmp_path, POLICY.replace('python = "3.12"\n', ""))

    def test_a_root_that_resolves_outside_the_repository_is_rejected(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A symlinked root cannot point the scan at another checkout."""
        outside = tmp_path / "outside"
        outside.mkdir()
        repo = make_repository(tmp_path / "repo", policy=POLICY)
        (repo / "link").symlink_to(outside, target_is_directory=True)
        data = tomllib.loads(
            (repo / "pyproject.toml")
            .read_text(encoding="utf-8")
            .replace('roots = ["pkg"]', 'roots = ["link"]')
        )
        with pytest.raises(ToolConfigError, match="escapes the repository"):
            load_scan_settings(data, repository=repo)
