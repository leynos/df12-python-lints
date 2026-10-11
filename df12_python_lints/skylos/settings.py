"""Execution metadata that the native Skylos schema cannot hold.

Native Skylos owns thresholds, exclusions and exceptions in ``[tool.skylos]``.
The one thing it cannot say is *which* production roots a consumer scans and
which interpreter the scan must run under, so a small wrapper-owned table
records exactly that::

    [tool.df12_skylos]
    roots = ["pkg", "scripts"]   # production roots, scanned in ONE query
    python = "3.14"              # minimum interpreter for the scan

All roots go to a single Skylos invocation, because separate scans would lose
references that cross roots.
"""

from __future__ import annotations

import dataclasses as dc
import re
import typing as typ

from df12_python_lints import _validate
from df12_python_lints._errors import ToolConfigError

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

_VERSION = re.compile(r"(\d+)\.(\d+)")
TABLE = "tool.df12_skylos"


@dc.dataclass(frozen=True, slots=True)
class ScanSettings:
    """The wrapper-owned execution metadata.

    Attributes
    ----------
    roots : tuple[str, ...]
        Repository-relative production roots (directories or files).
    python : tuple[int, int]
        Minimum ``(major, minor)`` interpreter the scan must run under, so
        source syntax newer than the interpreter is never silently skipped.
    """

    roots: tuple[str, ...]
    python: tuple[int, int]

    @property
    def python_text(self) -> str:
        """The interpreter requirement as ``major.minor``."""
        return f"{self.python[0]}.{self.python[1]}"


def load_scan_settings(
    data: cabc.Mapping[str, object], *, repository: pathlib.Path
) -> ScanSettings:
    """Validate ``[tool.df12_skylos]`` from a parsed manifest.

    Raises
    ------
    ToolConfigError
        If the table is missing, a key is malformed, or a root is absolute,
        escapes the repository or does not exist.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> with tempfile.TemporaryDirectory() as directory:
    ...     pathlib.Path(directory, "pkg").mkdir()
    ...     table = {"tool": {"df12_skylos": {"roots": ["pkg"], "python": "3.14"}}}
    ...     load_scan_settings(table, repository=pathlib.Path(directory)).python
    (3, 14)
    """
    tool = _validate.require_table(data.get("tool", {}), context="tool")
    table = _validate.require_table(tool.get("df12_skylos"), context=TABLE)
    unknown = sorted(set(table) - {"roots", "python"})
    if unknown:
        msg = (
            f"{TABLE} has unsupported keys {unknown}; native settings belong "
            "in [tool.skylos]"
        )
        raise ToolConfigError(msg)
    roots = _validate.require_string_tuple(table.get("roots"), context=f"{TABLE}.roots")
    if not roots:
        msg = f"{TABLE}.roots must not be empty"
        raise ToolConfigError(msg)
    _validate_roots(roots, repository=repository)
    return ScanSettings(roots=roots, python=_python(table.get("python")))


def _python(value: object) -> tuple[int, int]:
    """Parse the minimum interpreter, which must be spelled ``major.minor``."""
    text = _validate.require_string(value, context=f"{TABLE}.python")
    match = _VERSION.fullmatch(text)
    if match is None:
        msg = (
            f"{TABLE}.python must be a 'major.minor' version such as '3.14', "
            f"got {text!r}"
        )
        raise ToolConfigError(msg)
    return int(match.group(1)), int(match.group(2))


def _validate_roots(roots: tuple[str, ...], *, repository: pathlib.Path) -> None:
    """Reject roots that are unsafe, missing or outside the repository."""
    base = repository.resolve()
    for root in roots:
        if root.startswith("-"):
            msg = f"{TABLE}.roots entry {root!r} must not start with '-'"
            raise ToolConfigError(msg)
        if _validate.is_escaping_path(root):
            msg = (
                f"{TABLE}.roots entry {root!r} must be a repository-relative POSIX path"
            )
            raise ToolConfigError(msg)
        try:
            resolved = (base / root).resolve(strict=True)
        except OSError as error:
            msg = f"{TABLE}.roots entry {root!r} does not exist: {error}"
            raise ToolConfigError(msg) from error
        if not resolved.is_relative_to(base):
            msg = f"{TABLE}.roots entry {root!r} escapes the repository"
            raise ToolConfigError(msg)
