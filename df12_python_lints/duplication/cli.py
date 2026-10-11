r"""``df12-duplication``: the blocking code-duplication gate over nose.

Operations
----------
``check``
    Run the pinned detector with the consumer's ``[tool.nose]`` policy and
    fail on families not covered by a reasoned exception.
``allow``
    Record one reasoned exception naming every location in a family.
``install``
    Explicitly install the pinned, checksum-verified nose release binary.

Exit status: ``0`` no blocking findings, ``1`` blocking findings, ``2``
invalid invocation or configuration, or a failed analysis.

Examples
--------
::

    df12-duplication check --repository .
    df12-duplication allow --repository . --member 'src/a.py::parse' \\
        --member 'src/b.py::parse' --reason 'Independently versioned entry points.'
    df12-duplication install --repository .
"""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import sys
import typing as typ

from df12_python_lints._errors import ToolConfigError

from . import commands
from .context import ContextOptions, build_context
from .install import HostPlatform, InstallBoundary

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser; it imports nothing outside the standard library."""
    parser = argparse.ArgumentParser(
        prog="df12-duplication",
        description="Run or configure the blocking code-duplication gate.",
    )
    parser.add_argument(
        "--version", action="store_true", help="print the version and exit"
    )
    commands = parser.add_subparsers(dest="command")
    for name, summary in (
        ("check", "run the gate (exit 1 on blocking findings)"),
        ("allow", "record one reasoned exception"),
        ("install", "install the pinned nose release binary"),
    ):
        sub = commands.add_parser(name, help=summary, description=summary)
        sub.add_argument(
            "--repository", help="target checkout (default: current directory)"
        )
        sub.add_argument(
            "--binary",
            help="nose binary to use; relative paths resolve against --repository "
            "(default: $NOSE_BIN, then .tools/nose/nose, then PATH)",
        )
        sub.add_argument(
            "--timeout", type=int, default=120, help="detector timeout in seconds"
        )
    allow = commands.choices["allow"]
    allow.add_argument(
        "--member",
        action="append",
        default=[],
        help="location key 'path[::name]'; repeat to cover every location of a family",
    )
    allow.add_argument("--first", help="deprecated alias for the first --member")
    allow.add_argument(
        "--second",
        action="append",
        default=[],
        help="deprecated alias for a further --member",
    )
    allow.add_argument("--reason", required=True, help="why this duplication stays")
    return parser


def main(argv: cabc.Sequence[str] | None = None) -> int:
    """Run the command line.

    Parameters
    ----------
    argv : collections.abc.Sequence[str] | None
        Arguments after the program name; ``sys.argv[1:]`` when ``None``.

    Returns
    -------
    int
        ``0`` no blocking findings, ``1`` blocking findings, ``2`` invalid
        invocation or configuration, or a failed analysis.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"df12-duplication {importlib.metadata.version('df12-python-lints')}")
        return commands.EXIT_OK
    if args.command is None:
        parser.print_usage(sys.stderr)
        return commands.EXIT_ERROR
    streams = commands.Streams(sys.stdout, sys.stderr)
    try:
        context = build_context(
            repository=args.repository,
            binary=args.binary,
            environment=os.environ,
            options=ContextOptions(timeout_seconds=args.timeout),
        )
    except ToolConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return commands.EXIT_ERROR
    if args.command == "check":
        return commands.run_check(context, streams)
    if args.command == "install":
        boundary = InstallBoundary(HostPlatform.detect())
        return commands.run_install(context, boundary=boundary, streams=streams)
    members = [*args.member, *([args.first] if args.first else []), *args.second]
    return commands.run_allow(
        context, members=members, reason=args.reason, streams=streams
    )
