"""The ``check``, ``validate-config`` and ``allow`` operations.

Each function takes an explicit :class:`~.context.SkylosContext`, writes to the
streams it is given, and returns the documented exit status: ``0`` for a
completed clean gate (or a valid configuration), ``1`` for blocking findings,
``2`` for invalid configuration or a failed analysis. Where native Skylos
cannot distinguish the causes of ``2`` the limitation is reported rather than
guessed from prose.
"""

from __future__ import annotations

import tomllib
import typing as typ

from df12_python_lints._errors import ToolConfigError, describe

from .allow import record_whitelist_entry
from .backend import build_command, classify, verify_backend
from .config import validate_native
from .settings import ScanSettings, load_scan_settings

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from df12_python_lints._runtime import Streams

    from .context import SkylosContext

EXIT_OK = 0
EXIT_BLOCKING = 1
EXIT_ERROR = 2
ALLOW_HINT = "df12-skylos allow --symbol '<name>' --reason '<why this stays>'"


def load_policy(context: SkylosContext) -> tuple[ScanSettings, tuple[str, ...]]:
    """Read and fully validate the manifest without touching the backend.

    Returns
    -------
    tuple[ScanSettings, tuple[str, ...]]
        The execution metadata and the advisory warnings.

    Raises
    ------
    ToolConfigError
        If the manifest is unreadable or any consumed table is invalid.
    """
    try:
        with context.pyproject.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        msg = f"cannot read {context.pyproject}: {error}"
        raise ToolConfigError(msg) from error
    warnings = validate_native(data)
    return load_scan_settings(data, repository=context.repository), warnings


def _warn(warnings: cabc.Iterable[str], streams: Streams) -> None:
    """Print advisory warnings to the diagnostic stream."""
    for warning in warnings:
        print(f"warning: {warning}", file=streams.err)


def run_validate_config(context: SkylosContext, streams: Streams) -> int:
    """Validate the configuration; invoke nothing, install nothing, edit nothing.

    Returns
    -------
    int
        ``0`` when valid, ``2`` otherwise.
    """
    try:
        settings, warnings = load_policy(context)
    except ToolConfigError as error:
        print(describe(error), file=streams.err)
        return EXIT_ERROR
    _warn(warnings, streams)
    print(
        f"skylos configuration valid: roots {', '.join(settings.roots)}; "
        f"scan needs Python {settings.python_text}+",
        file=streams.out,
    )
    return EXIT_OK


def run_check(context: SkylosContext, streams: Streams) -> int:
    """Validate, verify the backend, then run the native gate once.

    Returns
    -------
    int
        ``0`` clean, ``1`` blocking findings, ``2`` invalid configuration or a
        failed analysis.
    """
    try:
        settings, warnings = load_policy(context)
        backend = verify_backend(settings, context.probe)
        command = build_command(context.probe.executable, context.pyproject, settings)
        result = context.runner(
            command, context.repository, context.environment, context.timeout_seconds
        )
        _warn(warnings, streams)
        # Native findings and logs are the report; pass them through untouched.
        print(result.stdout, end="", file=streams.out)
        print(result.stderr, end="", file=streams.err)
        outcome = classify(result)
    except ToolConfigError as error:
        print(describe(error), file=streams.err)
        return EXIT_ERROR
    if outcome == "blocking":
        print(
            f"Remove the dead code, or record a considered exception:\n  {ALLOW_HINT}",
            file=streams.out,
        )
        return EXIT_BLOCKING
    print(f"skylos gate passed ({backend})", file=streams.out)
    return EXIT_OK


def run_allow(
    context: SkylosContext, *, symbol: str, reason: str, streams: Streams
) -> int:
    """Record one documented whitelist exception.

    Returns
    -------
    int
        ``0`` once recorded, ``2`` when the request or manifest is invalid;
        an invalid request never modifies the manifest.
    """
    try:
        outcome = record_whitelist_entry(
            context.pyproject, symbol=symbol, reason=reason
        )
    except ToolConfigError as error:
        print(describe(error), file=streams.err)
        return EXIT_ERROR
    verb = {
        "added": "recorded",
        "updated": "updated the reason of",
        "unchanged": "kept",
    }
    print(f"{verb[outcome]} documented Skylos exception for {symbol}", file=streams.out)
    return EXIT_OK
