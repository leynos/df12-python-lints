"""Explicit, pinned, binary-only installation of the nose detector.

The installer never compiles anything, never runs a downloaded installer
script and never resolves "latest". Checking a repository
(``df12-duplication check``) never calls it. The release archive is verified
(see :mod:`.release`), the executable it holds is proved to report the pinned
version from a scratch location, and only then moved into place atomically.
"""

from __future__ import annotations

import dataclasses as dc
import pathlib
import platform
import tempfile
import typing as typ

from df12_python_lints._atomic import atomic_replace
from df12_python_lints._errors import ToolExecutionError, ToolPlatformError

from .release import download_archive, release_digests, release_url, verified_executable

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from .context import RunContext

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
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
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
