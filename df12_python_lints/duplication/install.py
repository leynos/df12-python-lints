"""Explicit, pinned, binary-only installation of the nose detector.

Only official release archives whose SHA-256 appears in the bundled
``releases.json`` are accepted. The installer never compiles anything, never
runs a downloaded installer script and never resolves "latest". Checking a
repository (``df12-duplication check``) never calls it.

The archive is verified, its single executable read from memory (no archive
path is ever written to disk), the executable proved to report the pinned
version from a scratch location, and only then moved into place atomically.
"""

from __future__ import annotations

import dataclasses as dc
import hashlib
import importlib.resources
import io
import json
import pathlib
import platform
import re
import tarfile
import tempfile
import typing as typ
import urllib.error
import urllib.parse
import urllib.request

from df12_python_lints import _validate
from df12_python_lints._atomic import atomic_replace
from df12_python_lints._errors import (
    ToolConfigError,
    ToolExecutionError,
    ToolPlatformError,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from .context import RunContext

RELEASE_BASE = "https://github.com/corca-ai/nose/releases/download"
_RELEASE_PATH_PREFIX = "/corca-ai/nose/releases/download/v"
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60
_VERSION = re.compile(r"\d+\.\d+\.\d+")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_OPERATING_SYSTEMS = {"Linux": "unknown-linux-gnu", "Darwin": "apple-darwin"}
_ARCHITECTURES = {
    "x86_64": "x86_64",
    "AMD64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}


@dc.dataclass(frozen=True, slots=True)
class HostPlatform:
    """The host identity used to select a release asset."""

    system: str
    machine: str
    libc: str

    @classmethod
    def detect(cls) -> HostPlatform:
        """Describe the running host."""
        return cls(platform.system(), platform.machine(), platform.libc_ver()[0])


def download_archive(url: str) -> bytes:
    """Download one bounded release archive from the official GitHub URL.

    Raises
    ------
    ToolExecutionError
        If the URL is not the official release path, the download fails, or
        the archive is empty or larger than 100 MiB.
    """
    if not _is_trusted_release_url(url):
        msg = "refusing a nose archive URL outside the pinned GitHub release"
        raise ToolExecutionError(msg)
    try:
        with urllib.request.urlopen(  # ruff: ignore[suspicious-url-open-usage] - HTTPS GitHub release path; digest verified.
            url, timeout=DOWNLOAD_TIMEOUT_SECONDS
        ) as response:
            archive = response.read(MAX_ARCHIVE_BYTES + 1)
    except (OSError, urllib.error.URLError) as error:
        msg = f"cannot download the pinned nose release from GitHub: {error}"
        raise ToolExecutionError(msg) from error
    if not archive or len(archive) > MAX_ARCHIVE_BYTES:
        msg = "the pinned nose release archive is empty or exceeds the 100 MiB limit"
        raise ToolExecutionError(msg)
    return archive


def _is_trusted_release_url(url: str) -> bool:
    """Report whether a URL names the HTTPS nose release path on github.com."""
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.netloc == "github.com"
        and parsed.username is None
        and parsed.password is None
        and port is None
        and parsed.path.startswith(_RELEASE_PATH_PREFIX)
        and not parsed.query
        and not parsed.fragment
    )


@dc.dataclass(frozen=True, slots=True)
class InstallBoundary:
    """Injectable I/O edges: host identity, download and output."""

    host: HostPlatform
    downloader: cabc.Callable[[str], bytes] = download_archive
    output: cabc.Callable[[str], None] = print


def platform_target(host: HostPlatform) -> str:
    """Map the host to an upstream release target triple.

    Raises
    ------
    ToolPlatformError
        If no checksum-approved binary exists for the host.

    Examples
    --------
    >>> platform_target(HostPlatform("Darwin", "arm64", ""))
    'aarch64-apple-darwin'
    """
    operating_system = _OPERATING_SYSTEMS.get(host.system)
    architecture = _ARCHITECTURES.get(host.machine)
    if operating_system is None or architecture is None:
        msg = (
            f"nose has no checksum-approved prebuilt binary for "
            f"{host.system}/{host.machine}; supported: Linux (glibc) and macOS "
            "on x86-64 or AArch64"
        )
        raise ToolPlatformError(msg)
    if host.system == "Linux" and host.libc != "glibc":
        msg = (
            "nose has checksum-approved Linux binaries for glibc only; "
            f"detected {host.libc or 'an unknown libc'}"
        )
        raise ToolPlatformError(msg)
    return f"{architecture}-{operating_system}"


def release_digests(version: str) -> dict[str, str]:
    """Return the approved platform digests for one nose release.

    Raises
    ------
    ToolConfigError
        If the version is malformed or no digests are approved for it.
    """
    if not _VERSION.fullmatch(version):
        msg = f"tool.nose.version must be a pinned X.Y.Z release, got {version!r}"
        raise ToolConfigError(msg)
    text = (
        importlib.resources
        .files(__package__)
        .joinpath("releases.json")
        .read_text("utf-8")
    )
    releases = _validate.require_table(
        _validate.require_table(json.loads(text), context="releases.json").get(
            "releases"
        ),
        context="releases.json releases",
    )
    if version not in releases:
        known = ", ".join(sorted(releases))
        msg = f"nose {version} has no approved release digests; approved: {known}"
        raise ToolConfigError(msg)
    table = _validate.require_table(
        releases[version], context=f"releases.json {version}"
    )
    digests = {target: str(digest) for target, digest in table.items()}
    if not all(_DIGEST.fullmatch(digest) for digest in digests.values()):
        msg = f"releases.json has an invalid SHA-256 digest for nose {version}"
        raise ToolConfigError(msg)
    return digests


def release_url(version: str, target: str) -> str:
    """Return the official release URL for a version and target.

    Examples
    --------
    >>> release_url("0.20.0", "aarch64-apple-darwin")
    'https://github.com/corca-ai/nose/releases/download/v0.20.0/nose-cli-aarch64-apple-darwin.tar.xz'
    """
    return f"{RELEASE_BASE}/v{version}/nose-cli-{target}.tar.xz"


def verified_executable(archive: bytes, *, expected_sha256: str) -> bytes:
    """Verify an archive digest and return its single nose executable.

    Raises
    ------
    ToolExecutionError
        On a digest mismatch, an unreadable archive, or anything other than
        exactly one regular, path-safe ``nose`` file.
    """
    actual = hashlib.sha256(archive).hexdigest()
    if actual != expected_sha256:
        msg = f"nose release SHA-256 mismatch: expected {expected_sha256}, got {actual}"
        raise ToolExecutionError(msg)
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:xz") as release:
            candidates = [m for m in release.getmembers() if _is_executable(m)]
            if len(candidates) != 1 or candidates[0].size > MAX_ARCHIVE_BYTES:
                msg = (
                    "nose release archive must contain exactly one bounded "
                    "nose executable"
                )
                raise ToolExecutionError(msg)
            stream = release.extractfile(candidates[0])
            payload = b"" if stream is None else stream.read(MAX_ARCHIVE_BYTES + 1)
    except (OSError, tarfile.TarError, EOFError) as error:
        msg = f"cannot read the verified nose release archive: {error}"
        raise ToolExecutionError(msg) from error
    if not payload or len(payload) != candidates[0].size:
        msg = "nose release executable is empty or truncated"
        raise ToolExecutionError(msg)
    return payload


def _is_executable(member: tarfile.TarInfo) -> bool:
    """Accept only a regular file named ``nose`` on a path that cannot escape."""
    path = pathlib.PurePosixPath(member.name)
    return (
        member.isfile()
        and path.name == "nose"
        and ".." not in path.parts
        and not path.is_absolute()
    )


def install_detector(
    context: RunContext, *, version: str, boundary: InstallBoundary
) -> pathlib.Path:
    """Install the pinned detector at the context's binary location.

    An already-installed binary that reports the pinned version is reused
    without any download.

    Raises
    ------
    ToolConfigError
        If ``version`` has no approved digests.
    ToolPlatformError
        If the host has no approved binary.
    ToolExecutionError
        On download, integrity, version or write failure.
    """
    target = platform_target(boundary.host)
    digests = release_digests(version)
    digest = digests.get(target)
    if digest is None:
        msg = f"nose {version} has no checksum-approved release for {target}"
        raise ToolPlatformError(msg)
    destination = context.binary_override or context.default_binary
    if destination.is_file() and _reports(destination, version, context):
        boundary.output(f"nose {version} already installed at {destination}")
        return destination
    boundary.output(f"Installing nose {version} for {target} into {destination}")
    payload = verified_executable(
        boundary.downloader(release_url(version, target)), expected_sha256=digest
    )
    _prove_version(payload, version, context)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_replace(destination, payload, mode=0o755)
    except OSError as error:
        msg = f"cannot install nose at {destination}: {error}"
        raise ToolExecutionError(msg) from error
    boundary.output(f"Verified {destination}: nose {version}")
    return destination


def _reports(binary: pathlib.Path, version: str, context: RunContext) -> bool:
    """Report whether ``binary`` runs and reports exactly ``nose <version>``."""
    try:
        result = context.runner(
            [str(binary), "--version"],
            context.repository,
            context.environment,
            context.timeout_seconds,
        )
    except ToolExecutionError:
        return False
    return result.returncode == 0 and result.stdout.strip() == f"nose {version}"


def _prove_version(payload: bytes, version: str, context: RunContext) -> None:
    """Run the verified payload from a scratch directory before installing it."""
    with tempfile.TemporaryDirectory(prefix="df12-duplication-install-") as scratch:
        candidate = pathlib.Path(scratch) / "nose"
        candidate.write_bytes(payload)
        candidate.chmod(0o755)
        if not _reports(candidate, version, context):
            msg = f"the verified executable does not report 'nose {version}'"
            raise ToolExecutionError(msg)
