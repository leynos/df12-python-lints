"""Validation of the consumed nose report and of ``[tool.nose]``."""

from __future__ import annotations

import json
import typing as typ

import pytest
from duplication_support import (
    PINNED,
    family,
    location,
    make_repository,
    nose_table,
    report,
)

from df12_python_lints._errors import ToolConfigError
from df12_python_lints.duplication.schema import normalize_report
from df12_python_lints.duplication.settings import load_settings

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib


class TestReportNormalization:
    """Reports are validated closed: unreadable shapes never read as clean."""

    def test_orders_by_descending_value_then_location(self) -> None:
        """Higher value first; equal values fall back to the label."""
        low = family(location("b.py"), location("c.py"), value=1.0)
        high = family(location("z.py"), location("y.py"), value=9.0)
        result = normalize_report(json.loads(report(low, high)))
        assert [f.value for f in result.findings] == [9.0, 1.0], (
            "value must order first"
        )

    def test_summary_counts_expose_budget_saturation(self) -> None:
        """A report that shows fewer families than exist is saturated."""
        found = family(location("a.py"), location("b.py"))
        result = normalize_report(json.loads(report(found, total=30)))
        assert (result.total, result.shown, result.is_saturated) == (30, 1, True)

    @pytest.mark.parametrize(
        ("mutate", "fragment"),
        [
            (lambda d: d.update(schema_version=7), "schema_version"),
            (lambda d: d.pop("summary"), "summary"),
            (lambda d: d.update(families="x"), "families must be an array"),
            (lambda d: d["summary"].update(shown=5), "summary.shown"),
            (lambda d: d["families"][0].update(value=True), "value must be a number"),
            (lambda d: d["families"][0].update(witness=""), "witness"),
            (lambda d: d["families"][0].update(locations=[]), "must not be empty"),
            (lambda d: d["families"][0]["locations"][0].update(start=0), "start"),
            (lambda d: d["families"][0]["locations"][0].update(end=0), "end"),
            (lambda d: d["families"][0]["locations"][0].update(name=3), "name"),
            (lambda d: d["families"][0]["locations"][0].pop("file"), "file"),
        ],
    )
    def test_malformed_reports_are_rejected(
        self, mutate: cabc.Callable[[dict[str, typ.Any]], object], fragment: str
    ) -> None:
        """Each broken field produces a diagnostic that names it."""
        data = json.loads(report(family(location("a.py"), location("b.py"))))
        mutate(data)
        with pytest.raises(ToolConfigError, match=fragment):
            normalize_report(data)

    def test_non_table_report_is_rejected(self) -> None:
        """A JSON array is not a report."""
        with pytest.raises(ToolConfigError, match="nose report"):
            normalize_report([])


class TestSettings:
    """``[tool.nose]`` is validated before the detector runs."""

    def test_valid_table_round_trips(self, tmp_path: pathlib.Path) -> None:
        """Every key is read, with the documented defaults."""
        repo = make_repository(tmp_path)
        settings = load_settings(repo / "pyproject.toml")
        assert (settings.version, settings.roots, settings.top) == (
            PINNED,
            ("src",),
            30,
        )

    def test_top_zero_means_unlimited_and_is_accepted(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The explicit unlimited report budget is a supported opt-in."""
        table = nose_table(extra="top = 0\n")
        repo = make_repository(tmp_path, nose_table=table)
        assert load_settings(repo / "pyproject.toml").top == 0, "top = 0 must be kept"

    @pytest.mark.parametrize(
        ("old", "new", "fragment"),
        [
            ('roots = ["src"]', "roots = []", "must not be empty"),
            ('roots = ["src"]', 'roots = ["/etc"]', "repository-relative"),
            ('roots = ["src"]', 'roots = ["../x"]', "repository-relative"),
            ('roots = ["src"]', 'roots = ["missing"]', "does not exist"),
            ('roots = ["src"]', "roots = 3", "array of strings"),
            ('surface = "all"', 'surface = "most"', "surface"),
            ("min-size = 24", "min-size = 0", "positive integer"),
            ("min-size = 24", "min-size = true", "positive integer"),
            ("top = 30", "top = -1", "top"),
            ('mode = "syntax,semantic,near"', 'mode = "syntax,syntax"', "once"),
            ('version = "0.20.0"', "version = 20", "version"),
        ],
    )
    def test_invalid_settings_name_the_key(
        self, tmp_path: pathlib.Path, old: str, new: str, fragment: str
    ) -> None:
        """Each invalid value is rejected with its configuration path."""
        repo = make_repository(tmp_path)
        text = (repo / "pyproject.toml").read_text(encoding="utf-8").replace(old, new)
        (repo / "pyproject.toml").write_text(text, encoding="utf-8")
        with pytest.raises(ToolConfigError, match=fragment):
            load_settings(repo / "pyproject.toml")

    def test_root_symlink_escaping_the_repository_is_rejected(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A root that resolves outside the checkout is refused."""
        outside = tmp_path / "outside"
        outside.mkdir()
        repo = make_repository(tmp_path / "repo")
        (repo / "link").symlink_to(outside, target_is_directory=True)
        text = (repo / "pyproject.toml").read_text(encoding="utf-8")
        (repo / "pyproject.toml").write_text(
            text.replace('roots = ["src"]', 'roots = ["link"]'), encoding="utf-8"
        )
        with pytest.raises(ToolConfigError, match="escapes"):
            load_settings(repo / "pyproject.toml")

    def test_missing_nose_table_is_rejected(self, tmp_path: pathlib.Path) -> None:
        """A repository without ``[tool.nose]`` cannot run the gate."""
        repo = make_repository(tmp_path, nose_table="")
        with pytest.raises(ToolConfigError, match=r"tool\.nose"):
            load_settings(repo / "pyproject.toml")

    def test_invalid_toml_is_a_configuration_error(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Unparseable TOML is reported, not raised as a traceback."""
        repo = make_repository(tmp_path)
        (repo / "pyproject.toml").write_text("[nope\n", encoding="utf-8")
        with pytest.raises(ToolConfigError, match="cannot read"):
            load_settings(repo / "pyproject.toml")
