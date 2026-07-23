"""df12-python-lints: pylint checkers for df12 Python conventions.

The package is a pylint plugin. Loading it registers two checkers:

- ``prefer-structural-pattern-matching`` (R9101) flags ``isinstance``
  dispatch chains better expressed as ``match`` statements;
- ``assert-missing-message`` (C9102) flags ``assert`` statements without a
  failure message; and
- ``prefer-match-over-constant-chain`` (R9103) flags ``if``/``elif``
  chains that only compare one subject with constants, enum members, or
  literals.

Examples
--------
Load the plugin from a pylint configuration::

    [tool.pylint.main]
    load-plugins = ["df12_python_lints"]

or from the command line::

    pylint --load-plugins=df12_python_lints my_package
"""

from __future__ import annotations

import typing as typ

from .assert_messages import AssertMessageChecker
from .constant_chain import ConstantChainChecker
from .match_dispatch import MatchDispatchChecker

if typ.TYPE_CHECKING:
    from pylint.lint import PyLinter

__all__ = [
    "AssertMessageChecker",
    "ConstantChainChecker",
    "MatchDispatchChecker",
    "register",
]


def register(linter: PyLinter) -> None:
    """Register the df12 checkers with *linter*.

    Pylint calls this entry point when the plugin loads.

    Examples
    --------
    Invoked automatically by ``pylint --load-plugins=df12_python_lints``.
    """
    linter.register_checker(MatchDispatchChecker(linter))
    linter.register_checker(AssertMessageChecker(linter))
    linter.register_checker(ConstantChainChecker(linter))
