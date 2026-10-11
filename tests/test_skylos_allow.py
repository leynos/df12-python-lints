"""Safe authoring of documented Skylos exceptions."""

from __future__ import annotations

import multiprocessing
import tomllib
import typing as typ

import pytest
from skylos_support import POLICY, make_repository

from df12_python_lints._errors import ToolConfigError
from df12_python_lints.skylos import cli
from df12_python_lints.skylos.allow import record_whitelist_entry, validate_symbol

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib


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


def _skylos_worker(path: str, prefix: str, repeat: int) -> None:
    """Record ``repeat`` distinct Skylos exceptions from another process."""
    import pathlib as pl

    for index in range(repeat):
        record_whitelist_entry(pl.Path(path), symbol=f"{prefix}{index}", reason="r")


def _nose_worker(path: str, prefix: str, repeat: int) -> None:
    """Record ``repeat`` distinct duplication exceptions from another process."""
    import pathlib as pl

    from df12_python_lints.duplication.allowlist import (
        record_allow_entry,
    )

    for index in range(repeat):
        record_allow_entry(
            pl.Path(path),
            members=[f"{prefix}{index}.py", f"{prefix}{index}b.py"],
            reason="r",
        )


def _run_workers(
    manifest: pathlib.Path, workers: list[tuple[cabc.Callable[..., None], str]]
) -> None:
    """Start one spawned process per worker and require clean exits."""
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=target, args=(str(manifest), prefix, 6))
        for target, prefix in workers
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=180)
        assert process.exitcode == 0, "a worker failed"


class TestConcurrentAuthoring:
    """Real concurrent processes share one lock protocol."""

    def test_skylos_with_skylos_loses_nothing(self, tmp_path: pathlib.Path) -> None:
        """Four processes recording symbols keep every symbol."""
        manifest = _manifest(tmp_path)
        _run_workers(manifest, [(_skylos_worker, f"p{n}_") for n in range(4)])
        assert len(_documented(manifest)) == 24

    def test_skylos_with_nose_loses_nothing(self, tmp_path: pathlib.Path) -> None:
        """Skylos and nose authoring on one manifest keep both sets of edits."""
        manifest = _manifest(tmp_path)
        _run_workers(
            manifest,
            [
                (_skylos_worker, "s0_"),
                (_nose_worker, "n0_"),
                (_skylos_worker, "s1_"),
                (_nose_worker, "n1_"),
            ],
        )
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        assert len(data["tool"]["skylos"]["whitelist"]["documented"]) == 12, (
            "Skylos edits"
        )
        assert len(data["tool"]["duplication_gate"]["allow"]) == 12, "nose edits"
        assert data["tool"]["skylos"]["gate"]["strict"] is True, "unrelated policy"
