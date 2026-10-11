"""Explicit, digest-verified, binary-only provisioning of the nose detector."""

from __future__ import annotations

import hashlib
import io
import pathlib
import sys
import tarfile

import pytest
from duplication_support import PINNED, make_repository, nose_table

from df12_python_lints._errors import (
    ToolExecutionError,
    ToolPlatformError,
)
from df12_python_lints._runtime import Streams
from df12_python_lints.duplication import context as context_module
from df12_python_lints.duplication import install
from df12_python_lints.duplication.commands import run_install

_LINUX = install.HostPlatform("Linux", "x86_64", "glibc")
_SCRIPT = f"#!/bin/sh\necho 'nose {PINNED}'\n".encode()


def _archive(members: list[tuple[str, bytes, bytes | None]]) -> bytes:
    """Build an in-memory ``tar.xz`` of ``(name, payload, link_type)`` members."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as bundle:
        for name, payload, link in members:
            info = tarfile.TarInfo(name)
            if link is not None:
                info.type = tarfile.SYMTYPE
                info.linkname = link.decode()
                bundle.addfile(info)
                continue
            info.size = len(payload)
            bundle.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _good() -> bytes:
    """Build a release archive holding one working ``nose`` executable."""
    return _archive([
        ("nose-cli-x/nose", _SCRIPT, None),
        ("nose-cli-x/README.md", b"hi", None),
    ])


def _sha(data: bytes) -> str:
    """Return the SHA-256 hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


class TestInstallation:
    """The explicit install operation."""

    def _setup(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, archive: bytes
    ) -> tuple[context_module.RunContext, list[str], list[str]]:
        """Create a context and approve ``archive``'s digest."""
        repo = make_repository(tmp_path / "repo")
        context = context_module.build_context(
            repository=str(repo), binary=None, environment={}
        )
        digest = _sha(archive)
        monkeypatch.setattr(
            install, "release_digests", lambda _v: {"x86_64-unknown-linux-gnu": digest}
        )
        return context, [], []

    def _boundary(
        self, archive: bytes, urls: list[str], lines: list[str]
    ) -> install.InstallBoundary:
        """Build an install boundary recording URLs and output."""

        def download(url: str) -> bytes:
            """Record the URL and serve the archive."""
            urls.append(url)
            return archive

        return install.InstallBoundary(_LINUX, downloader=download, output=lines.append)

    def test_installs_atomically_with_mode_and_verified_version(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The binary lands at the repository-local path, executable."""
        archive = _good()
        context, urls, lines = self._setup(tmp_path, monkeypatch, archive)
        target = install.install_detector(
            context, version=PINNED, boundary=self._boundary(archive, urls, lines)
        )
        assert target == context.default_binary, "installed at the local path"
        assert target.stat().st_mode & 0o777 == 0o755, "installed executable"
        assert urls == [install.release_url(PINNED, "x86_64-unknown-linux-gnu")], (
            "expected: urls == [install.release_url(PINNED, 'x86_64-unknown-linux-gn..."
        )
        leftovers = [p.name for p in target.parent.iterdir()]
        assert leftovers == ["nose"], f"no temporary file may remain: {leftovers}"

    def test_second_install_reuses_the_binary_without_downloading(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An already-correct binary is left alone."""
        archive = _good()
        context, urls, lines = self._setup(tmp_path, monkeypatch, archive)
        boundary = self._boundary(archive, urls, lines)
        install.install_detector(context, version=PINNED, boundary=boundary)
        install.install_detector(context, version=PINNED, boundary=boundary)
        assert len(urls) == 1, "the second run must not download"
        assert any("already installed" in line for line in lines), (
            "expected: any('already installed' in line for line in lines)"
        )

    def test_payload_reporting_the_wrong_version_is_never_installed(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The executable is proved from scratch before it replaces anything."""
        wrong = b"#!/bin/sh\necho 'nose 0.1.0'\n"
        archive = _archive([("x/nose", wrong, None)])
        context, urls, lines = self._setup(tmp_path, monkeypatch, archive)
        with pytest.raises(
            ToolExecutionError, match=r"does not report 'nose 0\.20\.0'"
        ):
            install.install_detector(
                context, version=PINNED, boundary=self._boundary(archive, urls, lines)
            )
        assert not context.default_binary.exists(), "nothing may be installed"

    def test_digest_mismatch_installs_nothing(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A download that does not match the approved digest is rejected."""
        context, urls, lines = self._setup(tmp_path, monkeypatch, _good())
        with pytest.raises(ToolExecutionError, match="mismatch"):
            install.install_detector(
                context,
                version=PINNED,
                boundary=self._boundary(_good() + b"x", urls, lines),
            )
        assert not context.default_binary.exists(), (
            "expected: not context.default_binary.exists()"
        )

    def test_explicit_binary_override_is_the_destination(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--binary`` selects where the detector is installed."""
        archive = _good()
        repo = make_repository(tmp_path / "repo")
        context = context_module.build_context(
            repository=str(repo), binary="vendor/nose", environment={}
        )
        monkeypatch.setattr(
            install,
            "release_digests",
            lambda _v: {"x86_64-unknown-linux-gnu": _sha(archive)},
        )
        target = install.install_detector(
            context, version=PINNED, boundary=self._boundary(archive, [], [])
        )
        assert target == repo.resolve() / "vendor" / "nose", (
            "expected: target == repo.resolve() / 'vendor' / 'nose'"
        )

    def test_host_without_an_approved_asset_fails_before_downloading(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Unsupported platforms never reach the network."""
        repo = make_repository(tmp_path / "repo")
        context = context_module.build_context(
            repository=str(repo), binary=None, environment={}
        )
        urls: list[str] = []
        boundary = install.InstallBoundary(
            install.HostPlatform("Windows", "AMD64", ""),
            downloader=lambda u: urls.append(u) or b"",
            output=lambda _m: None,
        )
        with pytest.raises(ToolPlatformError):
            install.install_detector(context, version=PINNED, boundary=boundary)
        assert not urls, "nothing may be downloaded"

    def test_an_uncreatable_destination_is_a_tool_error(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A destination whose parent is a file fails cleanly, not with a traceback."""
        archive = _good()
        repo = make_repository(tmp_path / "repo")
        (repo / "blocker").write_text("a file, not a directory", encoding="utf-8")
        context = context_module.build_context(
            repository=str(repo), binary="blocker/nose", environment={}
        )
        monkeypatch.setattr(
            install,
            "release_digests",
            lambda _v: {"x86_64-unknown-linux-gnu": _sha(archive)},
        )
        with pytest.raises(ToolExecutionError, match="cannot install nose"):
            install.install_detector(
                context, version=PINNED, boundary=self._boundary(archive, [], [])
            )

    def test_command_reports_failures_as_exit_two(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The install command maps expected failures to status two."""
        repo = make_repository(
            tmp_path / "repo",
            nose_table=nose_table(version="9.9.9"),
        )
        context = context_module.build_context(
            repository=str(repo), binary=None, environment={}
        )
        boundary = install.InstallBoundary(
            _LINUX, downloader=lambda _u: b"", output=print
        )
        streams = Streams(__import__("sys").stdout, __import__("sys").stderr)
        assert run_install(context, boundary=boundary, streams=streams) == 2, (
            "expected: run_install(context, boundary=boundary, streams=streams) == 2"
        )
        assert "no approved release digests" in capsys.readouterr().err, (
            "expected: 'no approved release digests' in capsys.readouterr().err"
        )


def test_a_staging_write_failure_is_a_tool_error(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An executable that cannot be staged for its version check fails cleanly."""
    context = context_module.build_context(
        repository=str(make_repository(tmp_path / "repo")), binary=None, environment={}
    )

    def refuse(self: pathlib.Path, _data: bytes) -> int:
        """Simulate a full scratch directory."""
        msg = "no space left"
        raise OSError(msg)

    monkeypatch.setattr(pathlib.Path, "write_bytes", refuse)
    with pytest.raises(ToolExecutionError, match="cannot stage"):
        install._prove_version(b"x", PINNED, context)


def test_a_scratch_directory_failure_makes_install_exit_two(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If the version-check scratch directory cannot be created, install exits 2."""
    archive = _good()
    repo = make_repository(tmp_path / "repo")
    context = context_module.build_context(
        repository=str(repo), binary=None, environment={}
    )
    monkeypatch.setattr(
        install,
        "release_digests",
        lambda _v: {"x86_64-unknown-linux-gnu": _sha(archive)},
    )

    def refuse(*_args: object, **_kwargs: object) -> None:
        """Simulate a full or read-only temporary directory."""
        msg = "no space left"
        raise OSError(msg)

    monkeypatch.setattr(install.tempfile, "TemporaryDirectory", refuse)
    boundary = install.InstallBoundary(
        _LINUX, downloader=lambda _url: archive, output=lambda _m: None
    )
    streams = Streams(sys.stdout, sys.stderr)
    assert run_install(context, boundary=boundary, streams=streams) == 2, (
        "expected: run_install(context, boundary=boundary, streams=streams) == 2"
    )
    err = capsys.readouterr().err
    assert "cannot create the scratch directory" in err, (
        "expected: 'cannot create the scratch directory' in err"
    )
    assert "Traceback" not in err, "expected: 'Traceback' not in err"
