"""Python 3.12 compatibility shims shared by the console commands.

The package supports Python 3.12, so ``typing.TypeIs`` (3.13) comes from
``typing_extensions`` there. Every use is a postponed annotation behind
``typing.TYPE_CHECKING``, so the shim is never imported at run time and the
installed package needs no ``typing_extensions`` (type checkers, which run
in the development environment, do).
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 13):
    from typing import TypeIs  # ruff: ignore[banned-import-from]
else:
    from typing_extensions import TypeIs

__all__ = ["TypeIs"]
