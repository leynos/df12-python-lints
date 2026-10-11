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
