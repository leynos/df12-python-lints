"""The adapter around native Skylos.

Native Skylos decides what is dead code and whether the gate fails. This
module owns only the invocation and a small, documented translation of its
outcome, so that a failed analysis can never read as a clean one.

Pin
---
The one authoritative Skylos pin is the ``skylos`` extra in this package's
own metadata (``skylos==X.Y.Z``). The installed backend must equal it, so a
Makefile, a workflow and the package cannot drift apart: provisioning installs
the extra, and ``check`` verifies the result.

Exit statuses of the pinned Skylos (4.33.2) with ``--gate``
-----------------------------------------------------------
``0`` the gate passed; ``1`` blocking findings; ``2`` an invalid or missing
configuration file or an incomplete analysis (``SKY-ANALYSIS-INCOMPLETE``,
for example source the running interpreter cannot parse). Native Skylos
cannot tell the causes of ``2`` apart, so they are reported together rather
than inferred from prose. One failure it reports on a ``0`` exit: a root with
no Python files only logs ``No Python files found in <root>``; that warning is
treated as a failed scan.
"""

from __future__ import annotations

import dataclasses as dc
import importlib.metadata
import re
import sys
import typing as typ

from df12_python_lints._errors import ToolConfigError, ToolExecutionError

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    from df12_python_lints._runtime import CommandResult

    from .settings import ScanSettings

DISTRIBUTION = "df12-python-lints"
BACKEND = "skylos"
INSTALL_HINT = (
    "provision the pinned backend with `pip install 'df12-python-lints[skylos]'` "
    "or an isolated `uv tool run --python <version> --with skylos==<pin> ...`"
)
EXIT_FAILED_ANALYSIS = 2
EXIT_BLOCKING = 1
_PIN = re.compile(r"\s*skylos\s*==\s*([0-9A-Za-z.+!-]+)\s*")
_EMPTY_MARKER = "No Python files found in"
# Skylos exposes `skylos.cli:main` and has no `__main__`, so the scan runs it
# in a child interpreter. The child is `sys.executable`, so the scan uses the
# very interpreter this command was started under.
_BOOTSTRAP = "import sys; from skylos.cli import main; sys.argv[0] = 'skylos'; main()"
# Local-only intent: no cloud upload, no provenance lookup, no grep
# verification; dead-code analysis only. Nothing here contacts an AI service.
_SCAN_FLAGS = (
    "--category",
    "dead_code",
    "--gate",
    "--format",
    "concise",
    "--no-upload",
    "--no-provenance",
    "--no-grep-verify",
)


@dc.dataclass(frozen=True, slots=True)
class BackendProbe:
    """What the scan can learn about its own runtime and backend.

    Attributes
    ----------
    executable : str
        The interpreter that runs the scan.
    interpreter : tuple[int, int]
        Its ``(major, minor)`` version.
    pinned : collections.abc.Callable[[], str]
        Returns the authoritative Skylos pin from package metadata.
    installed : collections.abc.Callable[[], str | None]
        Returns the installed Skylos version, or ``None`` when absent.
    """

    executable: str
    interpreter: tuple[int, int]
    pinned: cabc.Callable[[], str]
    installed: cabc.Callable[[], str | None]

    @classmethod
    def detect(cls) -> BackendProbe:
        """Probe the running interpreter and the installed distributions."""
        return cls(
            executable=sys.executable,
            interpreter=(sys.version_info.major, sys.version_info.minor),
            pinned=pinned_version,
            installed=installed_version,
        )


def pinned_version() -> str:
    """Return the Skylos version pinned by this package's ``skylos`` extra.

    Raises
    ------
    ToolExecutionError
        If the extra does not pin an exact ``==`` version.
    """
    for requirement in importlib.metadata.requires(DISTRIBUTION) or ():
        spec, _, marker = requirement.partition(";")
        if "skylos" not in marker.replace("'", '"'):
            continue
        match = _PIN.fullmatch(spec)
        if match:
            return match.group(1)
    msg = f"the {BACKEND} extra of {DISTRIBUTION} does not pin an exact version"
    raise ToolExecutionError(msg)


def installed_version() -> str | None:
    """Return the installed Skylos version, or ``None`` when it is absent."""
    try:
        return importlib.metadata.version(BACKEND)
    except importlib.metadata.PackageNotFoundError:
        return None


def verify_backend(settings: ScanSettings, probe: BackendProbe) -> str:
    """Check the interpreter and backend before any analysis.

    Returns
    -------
    str
        A one-line description, for example ``skylos 4.33.2 under Python 3.14``.

    Raises
    ------
    ToolExecutionError
        If the interpreter is older than the consumer requires, Skylos is not
        installed, or it differs from the authoritative pin.
    """
    if probe.interpreter < settings.python:
        running = f"{probe.interpreter[0]}.{probe.interpreter[1]}"
        msg = (
            f"the scan runs under Python {running} but tool.df12_skylos.python "
            f"requires {settings.python_text} or newer: run the command in an "
            f"isolated environment on that interpreter (for example "
            f"`uv tool run --python {settings.python_text} ...`)"
        )
        raise ToolExecutionError(msg)
    pinned, installed = probe.pinned(), probe.installed()
    if installed is None:
        msg = f"{BACKEND} is not installed in this environment: {INSTALL_HINT}"
        raise ToolExecutionError(msg)
    if installed != pinned:
        msg = (
            f"{BACKEND} {installed} is installed but this package pins "
            f"{pinned}: {INSTALL_HINT}"
        )
        raise ToolExecutionError(msg)
    return f"{BACKEND} {installed} under Python {settings.python_text}+"


def build_command(
    executable: str, pyproject: pathlib.Path, settings: ScanSettings
) -> list[str]:
    """Build the single scan argument vector.

    The order is the pinned release's: ``--config-file`` precedes the roots
    and every scan option follows them. All roots share one invocation so
    references across roots are seen.

    Examples
    --------
    >>> import pathlib
    >>> from df12_python_lints.skylos.settings import ScanSettings
    >>> settings = ScanSettings(("a", "b"), (3, 14))
    >>> command = build_command("py", pathlib.Path("/r/pyproject.toml"), settings)
    >>> command[3:8]
    ['--config-file', '/r/pyproject.toml', 'a', 'b', '--category']
    """
    return [
        executable,
        "-c",
        _BOOTSTRAP,
        "--config-file",
        str(pyproject),
        *settings.roots,
        *_SCAN_FLAGS,
    ]


def classify(result: CommandResult) -> str:
    """Translate a native outcome into ``clean`` or ``blocking``.

    Raises
    ------
    ToolConfigError
        If a ``0`` exit logged that a root held no Python files.
    ToolExecutionError
        If the analysis failed or ended with an unexpected status.
    """
    if result.returncode == EXIT_BLOCKING:
        return "blocking"
    if result.returncode == EXIT_FAILED_ANALYSIS:
        msg = (
            "skylos reported an invalid configuration or an incomplete analysis "
            "(exit status 2); a failed analysis is never a clean gate"
        )
        raise ToolExecutionError(msg)
    if result.returncode != 0:
        msg = f"skylos exited with unexpected status {result.returncode}"
        raise ToolExecutionError(msg)
    empty = [line for line in result.stderr.splitlines() if _EMPTY_MARKER in line]
    if empty:
        msg = (
            f"skylos found no Python files in a configured root "
            f"({empty[0].split(_EMPTY_MARKER)[-1].strip()}): check "
            "tool.df12_skylos.roots and tool.skylos.exclude"
        )
        raise ToolConfigError(msg)
    return "clean"
