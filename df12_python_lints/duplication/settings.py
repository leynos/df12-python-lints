"""The consumer-owned detector policy read from ``[tool.nose]``."""

from __future__ import annotations

import dataclasses as dc
import tomllib
import typing as typ

from df12_python_lints import _validate
from df12_python_lints._errors import ToolConfigError

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

_SURFACES = frozenset({"default", "all"})


@dc.dataclass(frozen=True, slots=True)
class NoseSettings:
    """Gate settings read from ``[tool.nose]``.

    Attributes
    ----------
    version : str
        Version string the detector binary must report.
    roots : tuple[str, ...]
        Repository-relative paths, all submitted in one detector query so
        families that span roots stay visible.
    mode : str
        Comma-separated detection channels, pinned so a change to nose's
        defaults cannot silently widen or narrow the gate.
    min_size : int
        Smallest unit size, in nose IL tokens, that may be reported.
    surface : str
        ``"default"`` for nose's ranked dashboard, or ``"all"`` to include
        families it keeps off the dashboard.
    top : int | None
        Report budget: how many ranked families nose returns. ``None`` keeps
        nose's own view size (30 in 0.20.0); ``0`` asks for every family.
    exclude : tuple[str, ...]
        Gitignore-style globs excluded from the scan.
    """

    version: str
    roots: tuple[str, ...]
    mode: str
    min_size: int
    surface: str
    top: int | None
    exclude: tuple[str, ...]


def load_settings(pyproject: pathlib.Path) -> NoseSettings:
    """Load and validate the detector settings.

    Parameters
    ----------
    pyproject : pathlib.Path
        The target repository's ``pyproject.toml``.

    Raises
    ------
    ToolConfigError
        If the file is unreadable or invalid, or a setting is wrong. A root
        that is absolute, escapes the repository or does not exist is
        rejected here; whether the roots contain source is checked from the
        detector's own report.
    """
    data = _read_toml(pyproject)
    tool = _validate.require_table(data.get("tool", {}), context="tool")
    nose = _validate.require_table(tool.get("nose"), context="tool.nose")
    surface = _validate.require_string(
        nose.get("surface", "all"), context="tool.nose.surface"
    )
    if surface not in _SURFACES:
        msg = "tool.nose.surface must be 'default' or 'all'"
        raise ToolConfigError(msg)
    roots = _validate.require_string_tuple(nose.get("roots"), context="tool.nose.roots")
    if not roots:
        msg = "tool.nose.roots must not be empty"
        raise ToolConfigError(msg)
    _validate_roots(roots, repository=pyproject.parent)
    return NoseSettings(
        version=_validate.require_string(
            nose.get("version"), context="tool.nose.version"
        ),
        roots=roots,
        mode=_mode(nose.get("mode")),
        min_size=_validate.require_integer(
            nose.get("min-size"), context="tool.nose.min-size", minimum=1
        ),
        surface=surface,
        top=_top(nose.get("top")),
        exclude=_validate.require_string_tuple(
            nose.get("exclude", []), context="tool.nose.exclude"
        ),
    )


def _read_toml(path: pathlib.Path) -> cabc.Mapping[str, object]:
    """Read one TOML file, naming it in any failure."""
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        msg = f"cannot read {path}: {error}"
        raise ToolConfigError(msg) from error


def _mode(value: object) -> str:
    """Validate the comma-separated channel list."""
    mode = _validate.require_string(value, context="tool.nose.mode")
    channels = [channel.strip() for channel in mode.split(",")]
    if not all(channels) or len(set(channels)) != len(channels):
        msg = "tool.nose.mode must list each detection channel once"
        raise ToolConfigError(msg)
    return mode


def _top(value: object) -> int | None:
    """Validate the optional report budget; ``0`` means unlimited."""
    if value is None:
        return None
    return _validate.require_integer(value, context="tool.nose.top", minimum=0)


def _validate_roots(roots: tuple[str, ...], *, repository: pathlib.Path) -> None:
    """Reject roots that are unsafe, missing or outside the repository."""
    base = repository.resolve()
    for root in roots:
        if _validate.is_escaping_path(root):
            msg = (
                f"tool.nose.roots entry {root!r} must be a repository-relative "
                "POSIX path"
            )
            raise ToolConfigError(msg)
        try:
            resolved = (base / root).resolve(strict=True)
        except OSError as error:
            msg = f"tool.nose.roots entry {root!r} does not exist: {error}"
            raise ToolConfigError(msg) from error
        if not resolved.is_relative_to(base):
            msg = f"tool.nose.roots entry {root!r} escapes the repository"
            raise ToolConfigError(msg)
