r"""``df12-skylos``: the dead-code gate over the pinned native Skylos.

Operations
----------
``check``
    Validate the configuration, verify the interpreter and backend pin, and
    run the native gate over the production roots in one invocation.
``validate-config``
    Validate the configuration only: no analysis, no provisioning, no edits.
``allow``
    Record one documented whitelist exception, with a reason.

Exit status: ``0`` completed clean gate (or valid configuration), ``1``
blocking findings, ``2`` invalid configuration or a failed analysis.

Examples
--------
::

    df12-skylos check --repository .
    df12-skylos validate-config --repository .
    df12-skylos allow --repository . --symbol '_write_mode' \
        --reason 'The framework invokes this override through its dispatch contract.'
"""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import sys
import typing as typ

from df12_python_lints._errors import ToolConfigError
from df12_python_lints._runtime import Streams

from . import commands
from .backend import BackendProbe
from .context import build_context

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser; it imports nothing outside the standard library."""
    parser = argparse.ArgumentParser(
        prog="df12-skylos",
        description="Run or configure the Skylos dead-code gate.",
    )
    parser.add_argument(
        "--version", action="store_true", help="print versions and exit"
    )
    sub = parser.add_subparsers(dest="command")
    for name, summary in (
        ("check", "run the gate (exit 1 on blocking findings)"),
        ("validate-config", "validate the configuration only"),
        ("allow", "record one documented whitelist exception"),
    ):
        command = sub.add_parser(name, help=summary, description=summary)
        command.add_argument(
            "--repository", help="target checkout (default: current directory)"
        )
    sub.choices["check"].add_argument(
        "--timeout", type=int, default=600, help="scan timeout in seconds"
    )
    allow = sub.choices["allow"]
    allow.add_argument("--symbol", required=True, help="plain identifier to whitelist")
    allow.add_argument("--reason", required=True, help="why this symbol stays")
    return parser


def _version() -> str:
    """Describe the package, the backend pin and the running interpreter."""
    probe = BackendProbe.detect()
    try:
        pin = probe.pinned()
    except ToolConfigError:
        pin = "unpinned"
    installed = probe.installed() or "not installed"
    package = importlib.metadata.version("df12-python-lints")
    return (
        f"df12-skylos {package} (skylos pin {pin}, installed {installed}, "
        f"Python {probe.interpreter[0]}.{probe.interpreter[1]})"
    )


def main(argv: cabc.Sequence[str] | None = None) -> int:
    """Run the command line.

    Parameters
    ----------
    argv : collections.abc.Sequence[str] | None
        Arguments after the program name; ``sys.argv[1:]`` when ``None``.

    Returns
    -------
    int
        ``0`` clean (or valid), ``1`` blocking findings, ``2`` invalid
        invocation or configuration, or a failed analysis.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(_version())
        return commands.EXIT_OK
    if args.command is None:
        parser.print_usage(sys.stderr)
        return commands.EXIT_ERROR
    streams = Streams(sys.stdout, sys.stderr)
    try:
        context = build_context(
            repository=args.repository,
            environment=os.environ,
            timeout_seconds=getattr(args, "timeout", 600),
        )
    except ToolConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return commands.EXIT_ERROR
    if args.command == "check":
        return commands.run_check(context, streams)
    if args.command == "validate-config":
        return commands.run_validate_config(context, streams)
    return commands.run_allow(
        context, symbol=args.symbol, reason=args.reason, streams=streams
    )
