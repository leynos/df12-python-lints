"""Platform selection, the digest manifest and archive verification."""

from __future__ import annotations

import hashlib
import io
import tarfile

import pytest
from duplication_support import PINNED

from df12_python_lints._errors import (
    ToolConfigError,
    ToolExecutionError,
    ToolPlatformError,
)
from df12_python_lints.duplication import install

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


class TestPlatformSelection:
    """Only checksum-approved platforms are served."""

    @pytest.mark.parametrize(
        ("host", "target"),
        [
            (
                install.HostPlatform("Linux", "x86_64", "glibc"),
                "x86_64-unknown-linux-gnu",
            ),
            (
                install.HostPlatform("Linux", "aarch64", "glibc"),
                "aarch64-unknown-linux-gnu",
            ),
            (install.HostPlatform("Darwin", "x86_64", ""), "x86_64-apple-darwin"),
            (install.HostPlatform("Darwin", "arm64", ""), "aarch64-apple-darwin"),
        ],
    )
    def test_supported_targets(self, host: install.HostPlatform, target: str) -> None:
        """Each supported host maps to its upstream triple."""
        assert install.platform_target(host) == target, (
            "expected: install.platform_target(host) == target"
        )

    @pytest.mark.parametrize(
        ("host", "fragment"),
        [
            (install.HostPlatform("Linux", "x86_64", "musl"), "glibc only"),
            (install.HostPlatform("Linux", "x86_64", ""), "unknown libc"),
            (install.HostPlatform("Windows", "AMD64", ""), "no checksum-approved"),
            (install.HostPlatform("Linux", "riscv64", "glibc"), "no checksum-approved"),
        ],
    )
    def test_unsupported_platforms_are_rejected(
        self, host: install.HostPlatform, fragment: str
    ) -> None:
        """Anything else fails with an actionable platform error."""
        with pytest.raises(ToolPlatformError, match=fragment):
            install.platform_target(host)


class TestManifest:
    """The bundled digest table is the single authority for pins."""

    def test_every_supported_target_has_a_sha256(self) -> None:
        """The pinned release covers all four supported targets."""
        digests = install.release_digests(PINNED)
        assert sorted(digests) == [
            "aarch64-apple-darwin",
            "aarch64-unknown-linux-gnu",
            "x86_64-apple-darwin",
            "x86_64-unknown-linux-gnu",
        ], "expected: sorted(digests) == [ 'aarch64-apple-darwin', 'aarch64-unknown..."

    def test_unknown_or_floating_versions_are_rejected(self) -> None:
        """There is no 'latest' and no unreviewed release."""
        with pytest.raises(ToolConfigError, match="no approved release digests"):
            install.release_digests("9.9.9")
        with pytest.raises(ToolConfigError, match=r"pinned X\.Y\.Z"):
            install.release_digests("latest")

    def test_release_url_names_the_official_asset(self) -> None:
        """The URL is built, never configured."""
        assert install.release_url(PINNED, "x86_64-apple-darwin") == (
            "https://github.com/corca-ai/nose/releases/download/v0.20.0/"
            "nose-cli-x86_64-apple-darwin.tar.xz"
        ), (
            "expected: install.release_url(PINNED, 'x86_64-apple-darwin') == ( 'https://gi..."
        )

    @pytest.mark.parametrize(
        "url",
        [
            "http://github.com/corca-ai/nose/releases/download/v0.20.0/x.tar.xz",
            "https://evil.example/corca-ai/nose/releases/download/v0.20.0/x.tar.xz",
            "https://user@github.com/corca-ai/nose/releases/download/v0.20.0/x.tar.xz",
            "https://notgithub.com/corca-ai/nose/releases/download/v0.20.0/x.tar.xz",
            "https://github.com:8443/corca-ai/nose/releases/download/v0.20.0/x.tar.xz",
            "https://github.com/other/nose/releases/download/v0.20.0/x.tar.xz",
            "https://github.com/corca-ai/nose/releases/download/v0.20.0/x.tar.xz?a=b",
            "https://github.com/corca-ai/nose/releases/latest/download/x.tar.xz",
            "file:///etc/passwd",
        ],
    )
    def test_download_refuses_untrusted_urls_before_any_network_use(
        self, url: str
    ) -> None:
        """Only the official release path is ever fetched."""
        with pytest.raises(ToolExecutionError, match="refusing"):
            install.download_archive(url)


class TestArchiveVerification:
    """Digest first, then path-safe extraction of one executable."""

    def test_good_archive_yields_the_executable(self) -> None:
        """A matching digest returns the single ``nose`` payload."""
        data = _good()
        assert (
            install.verified_executable(data, expected_sha256=_sha(data)) == _SCRIPT
        ), "expected: install.verified_executable(data, expected_sha256=_sha(data))..."

    def test_digest_mismatch_is_rejected_before_reading_the_archive(self) -> None:
        """A tampered archive never reaches extraction."""
        with pytest.raises(ToolExecutionError, match="SHA-256 mismatch"):
            install.verified_executable(_good(), expected_sha256="0" * 64)

    @pytest.mark.parametrize(
        "members",
        [
            [("nose-cli-x/README.md", b"x", None)],
            [("a/nose", b"x", None), ("b/nose", b"y", None)],
            [("nose-cli-x/nose", b"", b"/bin/sh")],
            [("../nose", b"x", None)],
            [("/abs/nose", b"x", None)],
            [("nose-cli-x/nose", b"", None)],
        ],
    )
    def test_unsafe_or_ambiguous_members_are_rejected(
        self, members: list[tuple[str, bytes, bytes | None]]
    ) -> None:
        """Links, traversal, absolute paths, duplicates and empties all fail."""
        data = _archive(members)
        with pytest.raises(ToolExecutionError):
            install.verified_executable(data, expected_sha256=_sha(data))

    def test_corrupt_archive_is_reported(self) -> None:
        """Bytes that are not xz-compressed tar fail cleanly."""
        data = b"not an archive"
        with pytest.raises(ToolExecutionError, match="cannot read"):
            install.verified_executable(data, expected_sha256=_sha(data))
