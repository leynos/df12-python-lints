"""The shared manifest transaction: lock protocol, atomicity and platform edges."""

from __future__ import annotations

import builtins
import errno
import os
import pathlib
import sys
import tempfile
import tomllib
import typing as typ

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from worker_support import run_workers

from df12_python_lints import _manifest
from df12_python_lints._atomic import atomic_replace
from df12_python_lints._errors import (
    ToolConfigError,
    ToolExecutionError,
    ToolPlatformError,
)

_KEYS = ["a", "b", "c", "d", "e", "f"]
_BASE = '[project]\nname = "demo"\nversion = "0"\n'

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def _write_manifest(directory: pathlib.Path, text: str = _BASE) -> pathlib.Path:
    """Create a manifest in ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "pyproject.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _set_key(key: str) -> cabc.Callable[[typ.Any], bool]:
    """Return an edit that sets ``[tool.probe].key = true``."""

    def edit(document: typ.Any) -> bool:  # ruff: ignore[any-type] - tomlkit document.
        """Set the probe key."""
        import tomlkit

        tool = document.setdefault("tool", tomlkit.table(is_super_table=True))
        tool.setdefault("probe", tomlkit.table())[key] = True
        return True

    return edit


class TestTransaction:
    """Read, edit and replace under one lock."""

    def test_edit_rewrites_and_reports_a_change(self, tmp_path: pathlib.Path) -> None:
        """A changing edit is written and reported."""
        manifest = _write_manifest(tmp_path)
        assert (
            _manifest.edit_manifest(manifest, _set_key("a"), extra="duplication")
            is True
        )
        assert (
            tomllib.loads(manifest.read_text(encoding="utf-8"))["tool"]["probe"]["a"]
            is True
        )

    def test_no_change_writes_nothing(self, tmp_path: pathlib.Path) -> None:
        """An edit that reports no change leaves the file untouched."""
        manifest = _write_manifest(tmp_path)
        before = manifest.stat().st_mtime_ns
        assert (
            _manifest.edit_manifest(manifest, lambda _d: False, extra="duplication")
            is False
        )
        assert manifest.stat().st_mtime_ns == before, "no rewrite for a no-op"

    def test_rejecting_edit_leaves_the_manifest_intact(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An edit raising ``ToolConfigError`` aborts the transaction."""
        manifest = _write_manifest(tmp_path)
        before = manifest.read_bytes()

        def reject(_document: typ.Any) -> bool:  # ruff: ignore[any-type] - a tomlkit document
            """Reject the request."""
            msg = "nope"
            raise ToolConfigError(msg)

        with pytest.raises(ToolConfigError, match="nope"):
            _manifest.edit_manifest(manifest, reject, extra="duplication")
        assert manifest.read_bytes() == before

    def test_invalid_toml_is_a_configuration_error(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Unparseable input is reported and left alone."""
        manifest = _write_manifest(tmp_path, "[broken\n")
        with pytest.raises(ToolConfigError, match="cannot parse"):
            _manifest.edit_manifest(manifest, _set_key("a"), extra="duplication")
        assert manifest.read_text(encoding="utf-8") == "[broken\n"

    def test_missing_manifest_is_a_configuration_error(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A missing target is reported, not created."""
        with pytest.raises(ToolConfigError, match="cannot read"):
            _manifest.edit_manifest(
                tmp_path / "pyproject.toml", _set_key("a"), extra="x"
            )

    def test_directory_target_is_rejected(self, tmp_path: pathlib.Path) -> None:
        """A directory is not a manifest."""
        with pytest.raises(ToolConfigError, match="not a regular file"):
            _manifest.resolve_manifest(tmp_path)

    def test_replace_failure_keeps_original_and_removes_temporary(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failing rename is reported; the original and directory stay clean."""
        manifest = _write_manifest(tmp_path)
        before = manifest.read_bytes()

        def failing(self: pathlib.Path, target: object) -> pathlib.Path:
            """Fail the final rename."""
            del self, target
            msg = "disk full"
            raise OSError(msg)

        monkeypatch.setattr(pathlib.Path, "replace", failing)
        with pytest.raises(ToolExecutionError, match="cannot write"):
            _manifest.edit_manifest(manifest, _set_key("a"), extra="duplication")
        monkeypatch.undo()
        assert manifest.read_bytes() == before, "the original must survive"
        names = sorted(p.name for p in tmp_path.iterdir())
        assert names == [".pyproject.toml.df12.lock", "pyproject.toml"], names

    def test_missing_tomlkit_gives_an_actionable_message(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without the extra, the error names the extra to install."""
        manifest = _write_manifest(tmp_path)
        real_import = builtins.__import__

        def refuse(name: str, *args: typ.Any, **kwargs: typ.Any) -> typ.Any:  # ruff: ignore[any-type] - mirrors builtins.__import__
            """Refuse to import tomlkit."""
            if name == "tomlkit":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", refuse)
        with pytest.raises(ToolExecutionError, match=r"df12-python-lints\[skylos\]"):
            _manifest.edit_manifest(manifest, _set_key("a"), extra="skylos")


class TestLockIdentity:
    """The lock file is a stable sidecar keyed on the real target."""

    def test_lock_survives_replacement_and_is_not_unlinked(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Two edits reuse the same lock inode."""
        manifest = _write_manifest(tmp_path)
        _manifest.edit_manifest(manifest, _set_key("a"), extra="duplication")
        lock = _manifest.lock_path_for(manifest.resolve())
        first = lock.stat().st_ino
        _manifest.edit_manifest(manifest, _set_key("b"), extra="duplication")
        assert lock.stat().st_ino == first, "the lock identity must be stable"

    def test_symlink_and_real_path_share_one_lock(self, tmp_path: pathlib.Path) -> None:
        """Every spelling of one manifest locks the same sidecar."""
        manifest = _write_manifest(tmp_path / "real")
        link = tmp_path / "link.toml"
        link.symlink_to(manifest)
        _manifest.edit_manifest(link, _set_key("a"), extra="duplication")
        assert _manifest.lock_path_for(manifest.resolve()).exists(), (
            "lock beside real file"
        )
        assert not (tmp_path / ".link.toml.df12.lock").exists(), (
            "no lock beside the link"
        )

    def test_non_posix_platform_fails_safely_before_editing(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without ``fcntl`` the transaction refuses rather than edit unlocked."""
        manifest = _write_manifest(tmp_path)
        before = manifest.read_bytes()
        monkeypatch.setitem(sys.modules, "fcntl", None)
        with pytest.raises(ToolPlatformError, match="POSIX advisory locks"):
            _manifest.edit_manifest(manifest, _set_key("a"), extra="duplication")
        assert manifest.read_bytes() == before


class TestFailureModes:
    """Environmental failures are tool errors, and leave nothing behind."""

    def test_a_failed_fsync_removes_the_temporary_file(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A write failure (for example ENOSPC) leaves the original and no debris."""
        target = tmp_path / "f"
        target.write_text("original", encoding="utf-8")

        def full(_descriptor: int) -> None:
            """Simulate a full disk at fsync."""
            raise OSError(errno.ENOSPC, "no space left on device")

        monkeypatch.setattr(os, "fsync", full)
        with pytest.raises(OSError, match="no space"):
            atomic_replace(target, b"replacement")
        monkeypatch.undo()
        assert target.read_text(encoding="utf-8") == "original"
        assert [p.name for p in tmp_path.iterdir()] == ["f"], "no temporary file"

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
    def test_an_unlockable_directory_is_a_tool_error_not_a_traceback(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A read-only manifest directory fails with the tool's own error."""
        manifest = _write_manifest(tmp_path / "ro")
        manifest.parent.chmod(0o500)
        try:
            with pytest.raises(
                ToolExecutionError, match="cannot open the manifest lock"
            ):
                _manifest.edit_manifest(manifest, _set_key("a"), extra="duplication")
        finally:
            manifest.parent.chmod(0o700)

    def test_a_filesystem_that_refuses_flock_is_a_tool_error(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An ``flock`` failure names the lock file and is not an ``OSError``."""
        import fcntl

        def refuse(_descriptor: int, _operation: int) -> None:
            """Simulate a filesystem without advisory locks."""
            raise OSError(errno.ENOLCK, "no locks available")

        monkeypatch.setattr(fcntl, "flock", refuse)
        manifest = _write_manifest(tmp_path)
        before = manifest.read_bytes()
        with pytest.raises(ToolExecutionError, match="cannot lock"):
            _manifest.edit_manifest(manifest, _set_key("a"), extra="duplication")
        assert manifest.read_bytes() == before


class TestAtomicReplace:
    """The low-level replacement keeps modes and cleans up."""

    def test_existing_mode_is_kept_and_explicit_mode_wins(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Mode comes from the destination unless overridden."""
        target = tmp_path / "f"
        target.write_text("x", encoding="utf-8")
        target.chmod(0o600)
        atomic_replace(target, b"y")
        assert target.stat().st_mode & 0o777 == 0o600, "existing mode kept"
        atomic_replace(target, b"z", mode=0o755)
        assert target.stat().st_mode & 0o777 == 0o755, "explicit mode applied"


class TestConcurrency:
    """Real concurrent processes must not lose each other's edits."""

    def test_concurrent_set_and_allow_workers_keep_every_edit(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Eight processes mix generic edits and ``allow`` runs; all survive."""
        manifest = _write_manifest(tmp_path)
        jobs = [
            (manifest, [("set", f"p{n}_{i}") for i in range(6)]) for n in range(4)
        ] + [
            (manifest, [("allow", f"a{n}_{i}.py") for i in range(4)]) for n in range(4)
        ]
        run_workers(jobs)
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))["tool"]
        assert len(data["probe"]) == 24, "every generic edit must survive"
        assert len(data["duplication_gate"]["allow"]) == 16, "every allow entry"

    @settings(
        max_examples=12,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        plans=st.lists(
            st.lists(
                st.tuples(st.sampled_from(["set", "noop"]), st.sampled_from(_KEYS)),
                min_size=1,
                max_size=5,
            ),
            min_size=2,
            max_size=4,
        ),
        spell_with_symlink=st.booleans(),
    )
    @pytest.mark.timeout(240)
    def test_any_interleaving_of_edits_converges_to_their_union(
        self,
        plans: list[list[tuple[str, str]]],
        spell_with_symlink: bool,  # ruff: ignore[boolean-type-hint-positional-argument] - a Hypothesis-injected argument.
    ) -> None:
        """The final manifest holds exactly the keys that some worker set.

        Worker counts, operation sequences (duplicates and no-ops included) and
        the spelling of the manifest path (real path or symlink) all vary.
        """
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            manifest = _write_manifest(root / "real")
            link = root / "link.toml"
            link.symlink_to(manifest)
            jobs = [
                (link if spell_with_symlink and index % 2 else manifest, plan)
                for index, plan in enumerate(plans)
            ]
            run_workers(jobs)
            expected = {key for plan in plans for op, key in plan if op == "set"}
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
            actual = set(data.get("tool", {}).get("probe", {}))
        assert actual == expected, f"lost or invented edits: {actual ^ expected}"
