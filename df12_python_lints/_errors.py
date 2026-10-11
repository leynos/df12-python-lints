"""Error vocabulary shared by the ``df12-*`` console commands.

Both commands map these errors to the documented exit status ``2``
(invalid invocation or configuration, or a failed analysis), so every
expected failure is reported without a traceback.
"""

from __future__ import annotations


class ToolConfigError(ValueError):
    """Raised when configuration, arguments, or a detector report are invalid."""


class ToolExecutionError(ToolConfigError):
    """Raised when a required backend is missing, wrong, or fails to run."""


class ToolPlatformError(ToolExecutionError):
    """Raised when the host platform cannot support the requested operation."""


def describe(error: ToolConfigError) -> str:
    """Render an error for the diagnostic stream.

    Configuration problems are labelled as such; a backend that is missing,
    wrong or failing is labelled a plain error, since the configuration may be
    fine.

    Examples
    --------
    >>> describe(ToolConfigError("bad key"))
    'configuration error: bad key'
    >>> describe(ToolExecutionError("no binary"))
    'error: no binary'
    """
    prefix = "error" if isinstance(error, ToolExecutionError) else "configuration error"
    return f"{prefix}: {error}"
