"""df12-python-lints: pylint checkers for df12 Python conventions.

The package is a pylint plugin. Loading it registers two checkers:

- ``prefer-structural-pattern-matching`` (R9101) flags ``isinstance``
  dispatch chains better expressed as ``match`` statements;
- ``assert-missing-message`` (C9102) flags ``assert`` statements without a
  failure message;
- ``prefer-match-over-constant-chain`` (R9103) flags ``if``/``elif``
  chains that only compare one subject with constants, enum members, or
  literals;
- ``trivial-attribute-wrapper`` (R9104) flags functions with no logic
  beyond attribute access or a proxied call;
- ``reexport-by-assignment`` (C9105) flags module-level aliases of
  imported names made by assignment rather than import; and
- ``lint-suppression-without-explanation`` (C9106) with
  ``typecheck-suppression-without-explanation`` (C9107) flag suppression
  pragmas that record no reason.

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
from .reexports import ReexportAssignmentChecker
from .suppressions import SuppressionCommentChecker
from .wrappers import TrivialWrapperChecker

if typ.TYPE_CHECKING:
    from pylint.lint import PyLinter

__all__ = [
    "AssertMessageChecker",
    "ConstantChainChecker",
    "MatchDispatchChecker",
    "ReexportAssignmentChecker",
    "SuppressionCommentChecker",
    "TrivialWrapperChecker",
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
    linter.register_checker(TrivialWrapperChecker(linter))
    linter.register_checker(ReexportAssignmentChecker(linter))
    linter.register_checker(SuppressionCommentChecker(linter))
