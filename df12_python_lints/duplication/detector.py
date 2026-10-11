"""Adapter around the pinned ``nose`` binary.

Everything that touches the external detector lives here: locating and
verifying the binary, building one ``nose query`` argument vector, running it
and normalizing its report. Nothing in this module downloads anything.

Native configuration
--------------------
nose reads ``nose.toml``/``.nose.toml`` and ``nose.ignore.json`` from its
working directory on its own. Either file could silently suppress or reshape
what this gate sees, creating a second, unreviewed policy. Every query is
therefore given an explicit empty ``--config`` and an explicit empty
``--ignore-file``, so the consumer's ``[tool.nose]`` table and
``[[tool.duplication_gate.allow]]`` entries are the only policy. Inline
``nose-ignore`` comments and in-tree ``.gitignore`` files are source-level
selection that nose applies itself; they are part of the scanned source and
are documented as such rather than disabled.
"""

from __future__ import annotations

import dataclasses as dc
import json
import pathlib
import shutil
import typing as typ

from df12_python_lints._errors import ToolConfigError, ToolExecutionError

from .schema import DetectorReport, normalize_report

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from .context import RunContext
    from .settings import NoseSettings

INSTALL_HINT = "run `df12-duplication install` to install the pinned detector"
# nose reports a root with no scannable source as a warning on a zero exit.
_EMPTY_SOURCE_MARKER = "no supported source files found under:"
_EMPTY_IGNORE_FILE = '{"ignores": []}\n'


@dc.dataclass(frozen=True, slots=True)
class NeutralFiles:
    """Empty native configuration and ignore files for one detector query.

    The command boundary owns their lifecycle (see
    :func:`write_neutral_files`); the detector adapter only passes them on.

    Attributes
    ----------
    config_file : pathlib.Path
        An empty file given as ``--config``.
    ignore_file : pathlib.Path
        A file with no ignores given as ``--ignore-file``.
    """

    config_file: pathlib.Path
    ignore_file: pathlib.Path


def resolve_binary(settings: NoseSettings, context: RunContext) -> str:
    """Locate the pinned binary and verify that it reports the pinned version.

    The search order is the explicit override (``--binary`` or ``NOSE_BIN``),
    the repository-local ``.tools/nose/nose``, then ``nose`` on ``PATH``. An
    override is never silently replaced by a later candidate.

    Raises
    ------
    ToolExecutionError
        If no binary is found or the reported version does not match.
    """
    candidate = _find_binary(context)
    if candidate is None:
        msg = (
            f"nose {settings.version} was not found at {context.default_binary} "
            f"or on PATH: {INSTALL_HINT}"
        )
        raise ToolExecutionError(msg)
    result = context.runner(
        [str(candidate), "--version"],
        context.repository,
        context.environment,
        context.timeout_seconds,
    )
    reported = result.stdout.strip()
    expected = f"nose {settings.version}"
    if result.returncode != 0 or reported != expected:
        msg = (
            f"{candidate} reports {reported or 'no version'!r} but the gate pins "
            f"{expected!r}: {INSTALL_HINT}"
        )
        raise ToolExecutionError(msg)
    return str(candidate)


def _find_binary(context: RunContext) -> pathlib.Path | None:
    """Return the override, else the local install, else a ``PATH`` match."""
    if context.binary_override is not None:
        return context.binary_override
    if context.default_binary.is_file():
        return context.default_binary
    found = shutil.which("nose", path=context.environment.get("PATH"))
    return None if found is None else pathlib.Path(found)


def build_command(
    binary: str, settings: NoseSettings, neutral: NeutralFiles
) -> list[str]:
    """Build the ``nose query`` argument vector for the configured policy.

    Parameters
    ----------
    binary : str
        Verified binary path.
    settings : NoseSettings
        The consumer's detector policy.
    neutral : NeutralFiles
        Empty native configuration and ignore files that stop ambient
        ``nose.toml`` and ``nose.ignore.json`` files taking effect.

    Returns
    -------
    list[str]
        The argument vector; never passed through a shell.
    """
    command = [binary, "query"]
    for root in settings.roots:
        command.extend(("--root", root))
    if settings.surface == "all":
        # The bare `all` term unhides families nose keeps off its dashboard.
        command.append("all")
    if settings.top is not None:
        command.append(f"top={settings.top}")
    command.extend(("--mode", settings.mode, "--min-size", str(settings.min_size)))
    for glob in settings.exclude:
        command.extend(("--exclude", glob))
    command.extend(("--config", str(neutral.config_file)))
    command.extend(("--ignore-file", str(neutral.ignore_file)))
    command.extend(("--format", "json"))
    return command


def run_detector(
    settings: NoseSettings, context: RunContext, neutral: NeutralFiles
) -> DetectorReport:
    """Run the pinned detector once over every root and normalize its report.

    Parameters
    ----------
    settings : NoseSettings
        The consumer's detector policy.
    context : RunContext
        The explicit repository, environment and subprocess boundary.
    neutral : NeutralFiles
        Empty native configuration and ignore files, owned by the caller.

    Raises
    ------
    ToolExecutionError
        If the binary is missing or wrong, the run fails or times out, or
        the output is not JSON.
    ToolConfigError
        If the report violates the consumed schema, or the effective scan
        contained no supported source files.
    """
    binary = resolve_binary(settings, context)
    result = context.runner(
        build_command(binary, settings, neutral),
        context.repository,
        context.environment,
        context.timeout_seconds,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        msg = f"{binary} exited with status {result.returncode}: {detail}"
        raise ToolExecutionError(msg)
    _reject_empty_sources(result.stderr)
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        msg = f"nose report is not valid JSON: {error}"
        raise ToolExecutionError(msg) from error
    return normalize_report(report)


def write_neutral_files(directory: pathlib.Path) -> NeutralFiles:
    """Create the empty native configuration and ignore files in ``directory``."""
    config_file = directory / "empty-nose.toml"
    ignore_file = directory / "empty-nose.ignore.json"
    config_file.write_text("", encoding="utf-8")
    ignore_file.write_text(_EMPTY_IGNORE_FILE, encoding="utf-8")
    return NeutralFiles(config_file, ignore_file)


def _reject_empty_sources(stderr: str) -> None:
    """Fail when nose warned that a root selected no supported source files.

    A successful query over an empty effective scan is indistinguishable
    from a clean one in the report, so the warning is the only signal.
    """
    roots = _empty_roots(stderr.splitlines())
    if roots:
        msg = (
            f"nose selected no supported source files under {', '.join(roots)}; "
            "check tool.nose.roots, tool.nose.exclude and any .gitignore rules "
            "inside those roots"
        )
        raise ToolConfigError(msg)


def _empty_roots(lines: cabc.Iterable[str]) -> list[str]:
    """Return each distinct root named by an empty-source warning, in order."""
    named = (
        line.partition(_EMPTY_SOURCE_MARKER)[2].strip()
        for line in lines
        if _EMPTY_SOURCE_MARKER in line
    )
    return list(dict.fromkeys(named))
