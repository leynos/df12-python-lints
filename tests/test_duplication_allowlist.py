"""Exception semantics: whole-family matching, keys, and safe authoring."""

from __future__ import annotations

import tomllib
import typing as typ

import pytest
from duplication_support import dedent, make_repository

from df12_python_lints._errors import ToolConfigError
from df12_python_lints.duplication.allowlist import (
    AllowEntry,
    key_matches,
    load_allowlist,
    record_allow_entry,
    validate_key,
)
from df12_python_lints.duplication.commands import partition_findings
from df12_python_lints.duplication.schema import Finding, Location

if typ.TYPE_CHECKING:
    import pathlib


def _place(file: str, name: str | None = None, start: int = 1) -> Location:
    """Build a location."""
    return Location(file=file, start=start, end=start + 9, name=name)


def _finding(*places: Location) -> Finding:
    """Build a finding over ``places``."""
    return Finding(witness="copy-paste", value=1.0, locations=places)


class TestKeyMatching:
    """Keys match by repository-relative path glob and optional unit name."""

    def test_name_qualified_key_never_matches_unnamed_fragment(self) -> None:
        """A ``::name`` key cannot excuse a fragment-level location."""
        assert not key_matches("pkg/a.py::run", _place("pkg/a.py")), (
            "fragment has no name"
        )

    def test_path_key_matches_any_unit_in_the_file(self) -> None:
        """A bare path covers named and unnamed locations alike."""
        assert key_matches("pkg/a.py", _place("pkg/a.py", "run")), "named"
        assert key_matches("pkg/a.py", _place("pkg/a.py")), "unnamed"

    def test_glob_keeps_full_match_scope(self) -> None:
        """``*`` does not cross directories, ``**`` does."""
        assert not key_matches("pkg/*.py", _place("pkg/sub/a.py")), (
            "* stays in a segment"
        )
        assert key_matches("pkg/**/*.py", _place("pkg/sub/a.py")), "** spans segments"

    def test_matching_is_stable_across_line_movement(self) -> None:
        """Keys carry no line numbers."""
        moved = [
            _place("pkg/a.py", "run", start=1),
            _place("pkg/a.py", "run", start=400),
        ]
        assert all(key_matches("pkg/a.py::run", place) for place in moved), (
            "line-stable"
        )


class TestWholeFamilyScope:
    """One exception covers every location; partial entries are never unioned."""

    def _entry(self, *keys: str) -> AllowEntry:
        """Build an entry covering ``keys``."""
        return AllowEntry(keys=keys, reason="because")

    def test_entry_silences_the_family_it_names_completely(self) -> None:
        """Every location matched means allowed."""
        family = _finding(_place("a.py", "f"), _place("b.py", "f"))
        blocking, allowed, unmatched = partition_findings(
            [family], [self._entry("a.py::f", "b.py::f")]
        )
        assert (len(blocking), len(allowed), len(unmatched)) == (0, 1, 0)

    def test_a_third_unlisted_copy_blocks(self) -> None:
        """Adding a copy outside the entry's keys makes the family block again."""
        grown = _finding(_place("a.py", "f"), _place("b.py", "f"), _place("c.py", "f"))
        blocking, _, unmatched = partition_findings(
            [grown], [self._entry("a.py::f", "b.py::f")]
        )
        assert len(blocking) == 1, "a grown family must remain blocking"
        assert len(unmatched) == 1, "the stale entry is reported as unmatched"

    def test_partial_entries_are_not_unioned(self) -> None:
        """Two entries that each cover part of a family do not excuse it."""
        family = _finding(_place("a.py", "f"), _place("b.py", "f"), _place("c.py", "f"))
        blocking, _, _ = partition_findings(
            [family],
            [self._entry("a.py::f", "b.py::f"), self._entry("c.py::f", "d.py::f")],
        )
        assert len(blocking) == 1, (
            "union of partial exceptions must not excuse a family"
        )

    def test_unmatched_entry_is_reported_without_failing(self) -> None:
        """An entry that matches nothing is surfaced, never silently deleted."""
        blocking, allowed, unmatched = partition_findings(
            [], [self._entry("x.py", "y.py")]
        )
        assert (blocking, allowed, len(unmatched)) == ([], [], 1)


class TestKeyValidation:
    """Malformed keys are rejected with the offending text."""

    @pytest.mark.parametrize(
        "key",
        ["", "  ", "::name", "a.py::", "/abs.py", "../up.py", "a/../b.py", "a\\b.py"],
    )
    def test_rejected(self, key: str) -> None:
        """Empty, escaping and malformed keys fail."""
        with pytest.raises(ToolConfigError):
            validate_key(key, context="--member")

    @pytest.mark.parametrize(
        "key", ["a.py", "pkg/**/x.py", "pkg/a.py::run", "é.py::ünï"]
    )
    def test_accepted(self, key: str) -> None:
        """Well-formed keys pass through unchanged."""
        assert validate_key(key, context="--member") == key


class TestLoading:
    """The manifest's entry tables are validated closed."""

    def _load(self, tmp_path: pathlib.Path, extra: str) -> tuple[AllowEntry, ...]:
        """Load the allowlist of a repository with ``extra`` appended."""
        repo = make_repository(tmp_path, extra=extra)
        return load_allowlist(repo / "pyproject.toml")

    def test_unit_and_members_entries(self, tmp_path: pathlib.Path) -> None:
        """Both entry shapes load in file order."""
        entries = self._load(
            tmp_path,
            dedent(
                """
                [[tool.duplication_gate.allow]]
                unit = "a.py::f"
                reason = "r1"

                [[tool.duplication_gate.allow]]
                members = ["a.py", "b.py"]
                reason = "r2"
                """
            ),
        )
        assert [e.keys for e in entries] == [("a.py::f",), ("a.py", "b.py")]

    @pytest.mark.parametrize(
        ("body", "fragment"),
        [
            ('unit = "a.py"', "non-empty reason"),
            ('unit = "a.py"\nreason = "  "', "non-empty reason"),
            ('reason = "r"', "exactly one"),
            ('unit = "a.py"\nmembers = ["a.py", "b.py"]\nreason = "r"', "exactly one"),
            ('members = ["a.py"]\nreason = "r"', "two or more"),
            ('members = ["a.py", 3]\nreason = "r"', "two or more"),
            ('unit = 3\nreason = "r"', "unit must be"),
            ('unit = "../x"\nreason = "r"', "repository-relative"),
        ],
    )
    def test_invalid_entries_are_rejected(
        self, tmp_path: pathlib.Path, body: str, fragment: str
    ) -> None:
        """Each malformed entry names what is wrong."""
        with pytest.raises(ToolConfigError, match=fragment):
            self._load(tmp_path, f"[[tool.duplication_gate.allow]]\n{body}\n")

    def test_allow_must_be_an_array(self, tmp_path: pathlib.Path) -> None:
        """A table where an array belongs is rejected."""
        with pytest.raises(ToolConfigError, match="array"):
            self._load(tmp_path, '[tool.duplication_gate]\nallow = "x"\n')


class TestAuthoring:
    """``record_allow_entry`` edits in place, idempotently and safely."""

    def _repo(self, tmp_path: pathlib.Path, extra: str = "") -> pathlib.Path:
        """Return the manifest of a disposable repository."""
        return make_repository(tmp_path, extra=extra) / "pyproject.toml"

    def test_one_member_makes_a_unit_entry_and_many_a_members_entry(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Arity selects the entry shape."""
        manifest = self._repo(tmp_path)
        record_allow_entry(manifest, members=["a.py::f"], reason="one")
        record_allow_entry(manifest, members=["a.py", "b.py", "c.py"], reason="three")
        entries = tomllib.loads(manifest.read_text(encoding="utf-8"))["tool"][
            "duplication_gate"
        ]["allow"]
        assert entries[0] == {"unit": "a.py::f", "reason": "one"}
        assert entries[1] == {"members": ["a.py", "b.py", "c.py"], "reason": "three"}

    def test_same_member_set_updates_the_reason_without_duplicating(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Order does not matter; a changed reason updates, an equal one is a no-op."""
        manifest = self._repo(tmp_path)
        assert (
            record_allow_entry(manifest, members=["a.py", "b.py"], reason="r1")
            == "added"
        )
        assert (
            record_allow_entry(manifest, members=["b.py", "a.py"], reason="r2")
            == "updated"
        )
        before = manifest.read_bytes()
        assert (
            record_allow_entry(manifest, members=["a.py", "b.py"], reason="r2")
            == "unchanged"
        )
        assert manifest.read_bytes() == before, "an unchanged request must not rewrite"
        data = tomllib.loads(before.decode())
        assert len(data["tool"]["duplication_gate"]["allow"]) == 1, "no duplicate entry"

    def test_repeated_identical_members_collapse(self, tmp_path: pathlib.Path) -> None:
        """Duplicate ``--member`` values are one key."""
        manifest = self._repo(tmp_path)
        record_allow_entry(manifest, members=["a.py", "a.py"], reason="r")
        table = tomllib.loads(manifest.read_text(encoding="utf-8"))["tool"][
            "duplication_gate"
        ]
        assert table["allow"][0]["unit"] == "a.py", (
            "one distinct key becomes a unit entry"
        )

    @pytest.mark.parametrize(
        ("members", "reason"),
        [
            (["a.py"], ""),
            (["a.py"], "   \n"),
            ([], "r"),
            (["../x"], "r"),
            (["a.py::"], "r"),
        ],
    )
    def test_invalid_requests_leave_the_manifest_byte_identical(
        self, tmp_path: pathlib.Path, members: list[str], reason: str
    ) -> None:
        """Validation happens before any write or lock."""
        manifest = self._repo(tmp_path)
        before = manifest.read_bytes()
        with pytest.raises(ToolConfigError):
            record_allow_entry(manifest, members=members, reason=reason)
        assert manifest.read_bytes() == before, "invalid input must not mutate"

    def test_shell_sensitive_unicode_reason_is_preserved_literally(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Quotes, dollars, backticks, newlines and Unicode survive."""
        manifest = self._repo(tmp_path)
        reason = 'it\'s "quoted" $(rm -rf /) `x` \\ é\nsecond line'
        record_allow_entry(manifest, members=["a b.py::f g"], reason=reason)
        entry = tomllib.loads(manifest.read_text(encoding="utf-8"))["tool"][
            "duplication_gate"
        ]["allow"][0]
        assert entry == {"unit": "a b.py::f g", "reason": reason}

    def test_comments_unrelated_tables_and_mode_are_preserved(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Only the allow table changes; comments and permissions stay."""
        manifest = self._repo(
            tmp_path, extra="# keep me\n[tool.other]\nx = 1  # inline\n"
        )
        manifest.chmod(0o640)
        record_allow_entry(manifest, members=["a.py"], reason="r")
        text = manifest.read_text(encoding="utf-8")
        assert "# keep me" in text, "the table comment must survive"
        assert "x = 1  # inline" in text, "the inline comment must survive"
        assert manifest.stat().st_mode & 0o777 == 0o640, "file mode must survive"

    def test_symlinked_manifest_is_edited_in_place(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The link stays a link; the real file changes."""
        manifest = self._repo(tmp_path / "real")
        link_dir = tmp_path / "linked"
        link_dir.mkdir()
        (link_dir / "pyproject.toml").symlink_to(manifest)
        record_allow_entry(link_dir / "pyproject.toml", members=["a.py"], reason="r")
        assert (link_dir / "pyproject.toml").is_symlink(), "the symlink must survive"
        assert "duplication_gate" in manifest.read_text(encoding="utf-8")

    def test_inline_allow_array_is_refused_without_writing(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An inline array cannot be edited safely, so the manifest is untouched."""
        manifest = self._repo(
            tmp_path,
            extra='[tool.duplication_gate]\nallow = [{unit = "a.py", reason = "r"}]\n',
        )
        before = manifest.read_bytes()
        with pytest.raises(ToolConfigError, match="tables to be edited"):
            record_allow_entry(manifest, members=["b.py"], reason="r")
        assert manifest.read_bytes() == before
