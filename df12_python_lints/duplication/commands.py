"""The ``check``, ``allow`` and ``install`` operations.

Each function takes an explicit :class:`~.context.RunContext`, writes to the
streams it is given, and returns the documented exit status: ``0`` for no
blocking findings, ``1`` for blocking findings, ``2`` for an invalid
invocation or configuration or a failed analysis.
"""

from __future__ import annotations

import contextlib
import pathlib
import tempfile
import typing as typ

from df12_python_lints._errors import ToolConfigError

from .allowlist import load_allowlist, record_allow_entry
from .detector import NeutralFiles, resolve_binary, run_detector, write_neutral_files
from .install import InstallBoundary, install_detector
from .policy import partition_findings
from .settings import load_settings

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from .context import RunContext
    from .policy import AllowEntry
    from .schema import DetectorReport, Finding

EXIT_OK = 0
EXIT_BLOCKING = 1
EXIT_ERROR = 2
ALLOW_HINT = (
    "df12-duplication allow --member '<path[::name]>' [--member '<path[::name]>' ...] "
    "--reason '<why this stays>'"
)


class Streams(typ.NamedTuple):
    """Where a command writes its report and its diagnostics."""

    out: typ.TextIO
    err: typ.TextIO


@contextlib.contextmanager
def _neutral_files() -> cabc.Iterator[NeutralFiles]:
    """Own the lifecycle of the empty native configuration files for one query.

    Yields
    ------
    NeutralFiles
        Empty ``--config`` and ``--ignore-file`` files in a scratch directory
        outside the checkout, removed when the query ends.
    """
    with tempfile.TemporaryDirectory(prefix="df12-duplication-") as scratch:
        yield write_neutral_files(pathlib.Path(scratch))


def run_check(context: RunContext, streams: Streams) -> int:
    """Run the blocking duplication gate.

    Returns
    -------
    int
        ``0`` when nothing blocks, ``1`` for blocking findings, ``2`` when
        the configuration is invalid or the analysis failed.
    """
    try:
        settings = load_settings(context.pyproject)
        allowlist = load_allowlist(context.pyproject)
        with _neutral_files() as neutral:
            report = run_detector(settings, context, neutral)
    except ToolConfigError as error:
        print(f"configuration error: {error}", file=streams.err)
        return EXIT_ERROR
    blocking, allowed, unmatched = partition_findings(report.findings, allowlist)
    _print_diagnostics(report, unmatched, streams)
    if report.is_saturated and not blocking:
        # A capped report that shows nothing blocking cannot prove the rest is
        # clean: allowed families consume the budget, so unseen ones go
        # unchecked. Fail closed rather than pass.
        print(
            f"error: the gate cannot prove a clean scan: nose reported "
            f"{report.total} families but returned only {report.shown}. Set "
            "tool.nose.top = 0 (every family) or raise it above the total, "
            "adjudicating any newly visible families.",
            file=streams.err,
        )
        return EXIT_ERROR
    return _print_outcome(blocking, allowed, settings.version, streams)


def _print_diagnostics(
    report: DetectorReport, unmatched: cabc.Sequence[AllowEntry], streams: Streams
) -> None:
    """Report unmatched entries and report-budget saturation."""
    for entry in unmatched:
        print(
            f"allow entry ({' ~ '.join(entry.keys)}) is unmatched in this scan: "
            "ranking, the report budget, thresholds, file selection or a changed "
            "family can all cause this. Review it; it is not removed automatically.",
            file=streams.err,
        )
    if report.is_saturated:
        print(
            f"report budget saturated: nose returned {report.shown} of "
            f"{report.total} families, and allowed families consume budget "
            "places, so families beyond the budget are not enforced. Raise "
            "tool.nose.top, or set it to 0 for every family, as a reviewed "
            "policy change.",
            file=streams.err,
        )


def _print_outcome(
    blocking: cabc.Sequence[Finding],
    allowed: cabc.Sequence[Finding],
    version: str,
    streams: Streams,
) -> int:
    """Print the gate verdict and return its exit status."""
    if not blocking:
        suffix = f"; {len(allowed)} allowed by reasoned exceptions" if allowed else ""
        print(f"duplication gate passed (nose {version}){suffix}", file=streams.out)
        return EXIT_OK
    print(
        f"duplicate code: {len(blocking)} unsuppressed family/families",
        file=streams.out,
    )
    for finding in blocking:
        print(
            f"  {finding.label} ({finding.witness}, value {finding.value:.1f})",
            file=streams.out,
        )
    print(
        "Extract the shared logic into one helper, or record a considered "
        f"exception that names every location in the family:\n  {ALLOW_HINT}",
        file=streams.out,
    )
    return EXIT_BLOCKING


def run_allow(
    context: RunContext,
    *,
    members: cabc.Sequence[str],
    reason: str,
    streams: Streams,
) -> int:
    """Record one exception in ``[[tool.duplication_gate.allow]]``.

    Returns
    -------
    int
        ``0`` once recorded, ``2`` if the request or manifest is invalid;
        an invalid request never modifies the manifest.
    """
    try:
        outcome = record_allow_entry(context.pyproject, members=members, reason=reason)
    except ToolConfigError as error:
        print(f"configuration error: {error}", file=streams.err)
        return EXIT_ERROR
    verb = {
        "added": "recorded",
        "updated": "updated the reason of",
        "unchanged": "kept",
    }
    covered = " ~ ".join(dict.fromkeys(members))
    print(f"{verb[outcome]} duplication exception for {covered}", file=streams.out)
    return EXIT_OK


def run_install(
    context: RunContext, *, boundary: InstallBoundary, streams: Streams
) -> int:
    """Install the detector pinned by ``[tool.nose].version``.

    Returns
    -------
    int
        ``0`` once a verified binary is in place, ``2`` otherwise.
    """
    try:
        settings = load_settings(context.pyproject)
        install_detector(context, version=settings.version, boundary=boundary)
    except ToolConfigError as error:
        print(f"installation error: {error}", file=streams.err)
        return EXIT_ERROR
    return EXIT_OK


def describe_detector(context: RunContext) -> str:
    """Return the verified detector version line, for diagnostics.

    Raises
    ------
    ToolConfigError
        If the settings are invalid or the detector is missing or wrong.
    """
    settings = load_settings(context.pyproject)
    binary = resolve_binary(settings, context)
    return f"nose {settings.version} at {binary}"
