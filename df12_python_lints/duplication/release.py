"""Release assets for the pinned nose detector: digests, URL trust and archives.

Only official release archives whose SHA-256 appears in the bundled
``releases.json`` are accepted. The archive is verified before anything is
read from it, and its single executable is read from memory, so no archive
path is ever written to disk.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import io
import json
import logging
import pathlib
import re
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

from df12_python_lints import _validate
from df12_python_lints._errors import ToolConfigError, ToolExecutionError

_LOG = logging.getLogger("df12_python_lints.install")
RELEASE_BASE = "https://github.com/corca-ai/nose/releases/download"
_RELEASE_PATH_PREFIX = "/corca-ai/nose/releases/download/v"
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60
_VERSION = re.compile(r"\d+\.\d+\.\d+")
_DIGEST = re.compile(r"[0-9a-f]{64}")


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
    archive = _fetch(url)
    if not archive or len(archive) > MAX_ARCHIVE_BYTES:
        msg = "the pinned nose release archive is empty or exceeds the 100 MiB limit"
        raise ToolExecutionError(msg)
    return archive


def _fetch(url: str) -> bytes:
    """Read at most one byte more than the archive limit from ``url``."""
    started = time.monotonic()
    try:
        with urllib.request.urlopen(  # ruff: ignore[suspicious-url-open-usage] - HTTPS GitHub release path; digest verified.
            url, timeout=DOWNLOAD_TIMEOUT_SECONDS
        ) as response:
            data = response.read(MAX_ARCHIVE_BYTES + 1)
    except (OSError, urllib.error.URLError) as error:
        msg = f"cannot download the pinned nose release from GitHub: {error}"
        raise ToolExecutionError(msg) from error
    _LOG.info(
        "download url=%s bytes=%d elapsed_seconds=%.3f",
        url,
        len(data),
        time.monotonic() - started,
    )
    return data


def _is_trusted_release_url(url: str) -> bool:
    """Report whether a URL names the HTTPS nose release path on github.com.

    The exact host match also rules out user information and a port, which
    would both appear in ``netloc``.
    """
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return all((
        parsed.scheme == "https",
        parsed.netloc == "github.com",
        parsed.path.startswith(_RELEASE_PATH_PREFIX),
        not parsed.query,
        not parsed.fragment,
    ))


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
    releases = _load_releases()
    if version not in releases:
        known = ", ".join(sorted(releases))
        msg = f"nose {version} has no approved release digests; approved: {known}"
        raise ToolConfigError(msg)
    return _digest_table(releases[version], version)


def _load_releases() -> dict[str, object]:
    """Read the bundled ``releases`` table."""
    text = (
        importlib.resources
        .files(__package__)
        .joinpath("releases.json")
        .read_text("utf-8")
    )
    document = _validate.require_table(json.loads(text), context="releases.json")
    return dict(_validate.require_table(document.get("releases"), context="releases"))


def _digest_table(raw: object, version: str) -> dict[str, str]:
    """Validate one release's platform digests."""
    table = _validate.require_table(raw, context=f"releases.json {version}")
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
            return _read_executable(release)
    except (OSError, tarfile.TarError, EOFError) as error:
        msg = f"cannot read the verified nose release archive: {error}"
        raise ToolExecutionError(msg) from error


def _read_executable(release: tarfile.TarFile) -> bytes:
    """Read the one bounded ``nose`` executable from an opened archive."""
    candidates = [member for member in release.getmembers() if _is_executable(member)]
    if len(candidates) != 1 or candidates[0].size > MAX_ARCHIVE_BYTES:
        msg = "nose release archive must contain exactly one bounded nose executable"
        raise ToolExecutionError(msg)
    stream = release.extractfile(candidates[0])
    payload = b"" if stream is None else stream.read(MAX_ARCHIVE_BYTES + 1)
    if not payload or len(payload) != candidates[0].size:
        msg = "nose release executable is empty or truncated"
        raise ToolExecutionError(msg)
    return payload


def _is_executable(member: tarfile.TarInfo) -> bool:
    """Accept only a regular file named ``nose`` on a path that cannot escape."""
    path = pathlib.PurePosixPath(member.name)
    return all((
        member.isfile(),
        path.name == "nose",
        ".." not in path.parts,
        not path.is_absolute(),
    ))
