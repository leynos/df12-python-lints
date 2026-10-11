"""Boundary observability shared by the ``df12-*`` console commands.

The commands are short-lived tools, so their observability is deliberately
small: structured ``key=value`` records on the standard ``logging`` module,
silent by default (a library-style ``NullHandler``) and switched on by
``--verbose``. One record per operation carries the operation name, the
repository scope, the outcome and the elapsed time; subprocess and download
boundaries add debug records.
"""

from __future__ import annotations

import logging
import time
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

_OUTCOMES = {0: "ok", 1: "blocking", 2: "error"}

logger = logging.getLogger("df12_python_lints")
logger.addHandler(logging.NullHandler())


def configure(*, verbose: bool) -> None:
    """Send the command records to standard error when ``verbose`` is set."""
    if not verbose:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


def observe(
    operation: str, repository: pathlib.Path, run: cabc.Callable[[], int]
) -> int:
    """Run one command operation and log its outcome and elapsed time.

    Parameters
    ----------
    operation : str
        The operation name, for example ``"check"``.
    repository : pathlib.Path
        The repository scope of the operation.
    run : collections.abc.Callable[[], int]
        The operation; it returns the exit status.

    Returns
    -------
    int
        The operation's exit status, unchanged.
    """
    started = time.monotonic()
    status = run()
    logger.info(
        "operation=%s repository=%s outcome=%s exit_status=%d elapsed_seconds=%.3f",
        operation,
        repository,
        _OUTCOMES.get(status, "error"),
        status,
        time.monotonic() - started,
    )
    return status
