"""Safe authoring of documented Skylos exceptions."""

from __future__ import annotations

import keyword
import pathlib
import tempfile
import tomllib
import unicodedata

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from skylos_support import POLICY, make_repository
from worker_support import run_workers

from df12_python_lints._errors import ToolConfigError
from df12_python_lints.skylos import cli
from df12_python_lints.skylos.allow import record_whitelist_entry, validate_symbol


def _documented(manifest: pathlib.Path) -> dict[str, str]:
    """Read the documented whitelist of a manifest."""
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    return data["tool"]["skylos"]["whitelist"]["documented"]


def _manifest(tmp_path: pathlib.Path, policy: str = POLICY) -> pathlib.Path:
    """Create a repository and return its manifest path."""
    return make_repository(tmp_path, policy=policy) / "pyproject.toml"


class TestSymbolSyntax:
    """Only a plain identifier is accepted, per the native simple-name match."""

    @pytest.mark.parametrize("symbol", ["_write_mode", "file_extension", "ünï", "A"])
    def test_plain_identifiers_are_accepted(self, symbol: str) -> None:
        """Ordinary and Unicode identifiers pass through unchanged."""
        assert validate_symbol(symbol) == symbol

    @pytest.mark.parametrize(
        "symbol",
        [
            "",
            "   ",
            "handle_*",
            "a?",
            "[ab]",
            "pkg.mod.func",
            "two words",
            "class",
            "1abc",
            " pad ",
            "a\nb",
        ],
    )
    def test_wildcards_dotted_and_malformed_names_are_rejected(
        self, symbol: str
    ) -> None:
        """No silent wildcard, no qualified name, no whitespace."""
        with pytest.raises(ToolConfigError):
            validate_symbol(symbol)


class TestRecording:
    """The documented whitelist is written in the native schema."""

    def test_new_entry_creates_the_native_table(self, tmp_path: pathlib.Path) -> None:
        """The entry lands under ``[tool.skylos.whitelist.documented]``."""
        manifest = _manifest(tmp_path)
        assert (
            record_whitelist_entry(
                manifest, symbol="_write_mode", reason="Read at runtime."
            )
            == "added"
        )
        assert _documented(manifest) == {"_write_mode": "Read at runtime."}
        assert "[tool.skylos.whitelist.documented]" in manifest.read_text(
            encoding="utf-8"
        )

    def test_repeating_a_symbol_neither_duplicates_nor_rewrites(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Same symbol and reason is a no-op."""
        manifest = _manifest(tmp_path)
        record_whitelist_entry(manifest, symbol="x", reason="why")
        before = manifest.read_bytes()
        assert record_whitelist_entry(manifest, symbol="x", reason="why") == "unchanged"
        assert manifest.read_bytes() == before, "an unchanged request must not rewrite"

    def test_a_different_reason_updates_in_place(self, tmp_path: pathlib.Path) -> None:
        """The reason is replaced; the symbol stays single."""
        manifest = _manifest(tmp_path)
        record_whitelist_entry(manifest, symbol="x", reason="old")
        assert record_whitelist_entry(manifest, symbol="x", reason="new") == "updated"
        assert _documented(manifest) == {"x": "new"}

    def test_shell_sensitive_unicode_reason_is_preserved_literally(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Quotes, dollars, backticks, backslashes, newlines and Unicode survive."""
        manifest = _manifest(tmp_path)
        reason = ' it\'s "q" $(rm -rf /) `x` \\ é\nsecond line '
        record_whitelist_entry(manifest, symbol="callback", reason=reason)
        assert _documented(manifest) == {"callback": reason}

    @pytest.mark.parametrize(
        ("symbol", "reason"),
        [("x", ""), ("x", " \t\n"), ("", "why"), ("a.b", "why"), ("a*", "why")],
    )
    def test_invalid_requests_leave_the_manifest_byte_identical(
        self, tmp_path: pathlib.Path, symbol: str, reason: str
    ) -> None:
        """Validation runs before any write."""
        manifest = _manifest(tmp_path)
        before = manifest.read_bytes()
        with pytest.raises(ToolConfigError):
            record_whitelist_entry(manifest, symbol=symbol, reason=reason)
        assert manifest.read_bytes() == before

    def test_comments_unrelated_tables_modes_and_nose_entries_are_preserved(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Only the documented table changes."""
        extra = (
            "# keep me\n[tool.other]\nx = 1  # inline\n"
            '[[tool.duplication_gate.allow]]\nunit = "a.py"\nreason = "nose entry"\n'
        )
        manifest = _manifest(tmp_path, POLICY + extra)
        manifest.chmod(0o640)
        record_whitelist_entry(manifest, symbol="x", reason="why")
        text = manifest.read_text(encoding="utf-8")
        assert "# keep me" in text
        assert "x = 1  # inline" in text
        assert 'reason = "nose entry"' in text
        assert manifest.stat().st_mode & 0o777 == 0o640

    def test_an_invalid_existing_value_is_refused_not_reported_unchanged(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An existing non-string value is never mistaken for a matching reason."""
        policy = POLICY + "[tool.skylos.whitelist.documented]\nx = 3\n"
        manifest = _manifest(tmp_path, policy)
        before = manifest.read_bytes()
        with pytest.raises(ToolConfigError, match="is not a string"):
            record_whitelist_entry(manifest, symbol="x", reason="3")
        assert manifest.read_bytes() == before

    @pytest.mark.parametrize("control", ["\x1b", "\x00", "\x07", "\x7f", "\r"])
    def test_a_reason_with_a_control_character_is_rejected(
        self, tmp_path: pathlib.Path, control: str
    ) -> None:
        """Control characters cannot be written back readably, so they are refused."""
        manifest = _manifest(tmp_path)
        before = manifest.read_bytes()
        with pytest.raises(ToolConfigError, match="control characters"):
            record_whitelist_entry(manifest, symbol="x", reason=f"bad{control}x")
        assert manifest.read_bytes() == before

    def test_runtime_entry_points_are_never_created(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An ordinary whitelist request never becomes a typed exemption."""
        manifest = _manifest(tmp_path)
        record_whitelist_entry(manifest, symbol="x", reason="why")
        assert "entrypoints" not in manifest.read_text(encoding="utf-8")

    def test_existing_documented_entries_and_entry_points_stay_distinct(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Adding a symbol keeps the existing exemption table intact."""
        extra = (
            '[[tool.skylos.dead_code.entrypoints]]\ntype = "method"\n'
            'full_name = "a.b"\nreason = "r"\n'
        )
        manifest = _manifest(tmp_path, POLICY + extra)
        record_whitelist_entry(manifest, symbol="x", reason="why")
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))["tool"]["skylos"]
        assert data["dead_code"]["entrypoints"][0]["full_name"] == "a.b"
        assert data["whitelist"]["documented"] == {"x": "why"}

    @pytest.mark.parametrize(
        ("policy", "fragment"),
        [
            ("[project.x]\na = 1\n", "tool.skylos is required"),
            ("[tool]\nskylos = 3\n", "must be a table"),
            ("[tool.skylos]\nwhitelist = ['a']\n", "must be a table"),
            ("[tool.skylos.whitelist]\ndocumented = 3\n", "must be a table"),
        ],
    )
    def test_wrong_manifest_shapes_are_refused_without_writing(
        self, tmp_path: pathlib.Path, policy: str, fragment: str
    ) -> None:
        """A shape the editor cannot extend safely is reported and left alone."""
        manifest = _manifest(tmp_path, policy)
        before = manifest.read_bytes()
        with pytest.raises(ToolConfigError, match=fragment):
            record_whitelist_entry(manifest, symbol="x", reason="why")
        assert manifest.read_bytes() == before

    def test_command_line_records_and_reports(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``allow`` prints what it did and exits zero."""
        manifest = _manifest(tmp_path)
        code = cli.main([
            "allow",
            "--repository",
            str(manifest.parent),
            "--symbol",
            "x",
            "--reason",
            "why",
        ])
        assert code == 0
        assert "recorded documented Skylos exception for x" in capsys.readouterr().out
        assert _documented(manifest) == {"x": "why"}

    def test_command_line_rejects_invalid_requests_with_status_two(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A wildcard symbol is exit 2 and does not mutate."""
        manifest = _manifest(tmp_path)
        before = manifest.read_bytes()
        code = cli.main([
            "allow",
            "--repository",
            str(manifest.parent),
            "--symbol",
            "x*",
            "--reason",
            "why",
        ])
        assert code == 2
        assert "plain Python identifier" in capsys.readouterr().err
        assert manifest.read_bytes() == before


class TestConcurrentAuthoring:
    """Real concurrent processes share one lock protocol."""

    def test_skylos_with_skylos_loses_nothing(self, tmp_path: pathlib.Path) -> None:
        """Four processes recording symbols keep every symbol."""
        manifest = _manifest(tmp_path)
        run_workers([
            (manifest, [("skylos", f"p{n}_{i}") for i in range(6)]) for n in range(4)
        ])
        assert len(_documented(manifest)) == 24

    def test_skylos_with_nose_loses_nothing(self, tmp_path: pathlib.Path) -> None:
        """Skylos and nose authoring on one manifest keep both sets of edits."""
        manifest = _manifest(tmp_path)
        jobs = []
        for n in range(2):
            jobs.extend([
                (manifest, [("skylos", f"s{n}_{i}") for i in range(6)]),
                (manifest, [("allow", f"n{n}_{i}.py") for i in range(6)]),
            ])
        run_workers(jobs)
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))["tool"]
        assert len(data["skylos"]["whitelist"]["documented"]) == 12, "Skylos edits"
        assert len(data["duplication_gate"]["allow"]) == 12, "nose edits"
        assert data["skylos"]["gate"]["strict"] is True, "unrelated policy"


_IDENTIFIERS = st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,12}", fullmatch=True).filter(
    lambda name: name.isidentifier() and not keyword.iskeyword(name)
)
_REASONS = st.text(min_size=1, max_size=40).filter(
    lambda text: (
        bool(text.strip())
        and all(unicodedata.category(c) != "Cc" or c in "\n\t" for c in text)
    )
)


@given(symbol=_IDENTIFIERS)
def test_every_plain_identifier_is_a_valid_symbol(symbol: str) -> None:
    """The symbol contract accepts exactly plain identifiers."""
    assert validate_symbol(symbol) == symbol


@given(
    head=_IDENTIFIERS,
    junk=st.sampled_from(["*", "?", "[", "]", ".", " ", "-", "\n", "/", "::"]),
    tail=st.text(alphabet="ab", max_size=3),
)
def test_a_name_with_wildcard_or_separator_characters_is_rejected(
    head: str, junk: str, tail: str
) -> None:
    """Wildcards, dots, spaces and separators can never become a symbol."""
    with pytest.raises(ToolConfigError):
        validate_symbol(head + junk + tail)


@settings(max_examples=30, deadline=None)
@given(
    steps=st.lists(st.tuples(_IDENTIFIERS, _REASONS), min_size=1, max_size=8),
)
def test_any_authoring_sequence_matches_a_last_write_wins_model(
    steps: list[tuple[str, str]],
) -> None:
    """Replaying requests yields one entry per symbol holding its latest reason."""
    with tempfile.TemporaryDirectory() as scratch:
        manifest = _manifest(pathlib.Path(scratch))
        model: dict[str, str] = {}
        for symbol, reason in steps:
            outcome = record_whitelist_entry(manifest, symbol=symbol, reason=reason)
            expected = (
                "added"
                if symbol not in model
                else "unchanged"
                if model[symbol] == reason
                else "updated"
            )
            assert outcome == expected, f"{symbol!r}: {outcome} != {expected}"
            model[symbol] = reason
        assert _documented(manifest) == model, "the manifest must equal the model"
