"""df12-python-lints: pylint checkers for df12 Python conventions.

The package is a pylint plugin. Loading it registers ten checkers
providing thirteen messages:

- ``prefer-structural-pattern-matching`` (R9101) flags ``isinstance``
  dispatch chains better expressed as ``match`` statements;
- ``assert-missing-message`` (C9102) flags ``assert`` statements without a
  failure message;
- ``prefer-match-over-constant-chain`` (R9103) flags ``if``/``elif``
  chains that only compare one subject with constants, enum members, or
  literals;
- ``trivial-attribute-wrapper`` (R9104) flags functions with no logic
  beyond attribute access or a proxied call, and
  ``trivial-alias-wrapper`` (R9110) flags functions that only forward
  their arguments to another function;
- ``reexport-by-assignment`` (C9105) flags module-level aliases of
  imported names made by assignment rather than import; and
- ``lint-suppression-without-explanation`` (C9106) with
  ``typecheck-suppression-without-explanation`` (C9107) flag suppression
  pragmas that record no reason; and
- ``prefer-snapshot-assertion`` (R9108) with
  ``prefer-snapshot-substring`` (R9109) flag test assertions better
  expressed as syrupy snapshots; and
- ``prefer-slots-for-dataclass`` (R9111) flags closed standard-library
  dataclasses that do not request or declare slots;
- ``prefer-type-statement`` (R9112) flags module-level type aliases
  better declared with the PEP 695 ``type`` statement, while
  ``redundant-future-annotations`` (C9112) flags ``from __future__
  import annotations`` on a 3.14+ baseline; both respect pylint's
  ``py-version`` option.

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
from .dataclass_slots import DataclassSlotsChecker
from .future_annotations import FutureAnnotationsChecker
from .match_dispatch import MatchDispatchChecker
from .reexports import ReexportAssignmentChecker
from .snapshot_asserts import SnapshotAssertionChecker
from .suppressions import SuppressionCommentChecker
from .type_aliases import TypeAliasChecker
from .wrappers import TrivialWrapperChecker

if typ.TYPE_CHECKING:
    from pylint.lint import PyLinter

__all__ = [
    "AssertMessageChecker",
    "ConstantChainChecker",
    "DataclassSlotsChecker",
    "FutureAnnotationsChecker",
    "MatchDispatchChecker",
    "ReexportAssignmentChecker",
    "SnapshotAssertionChecker",
    "SuppressionCommentChecker",
    "TrivialWrapperChecker",
    "TypeAliasChecker",
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
    linter.register_checker(DataclassSlotsChecker(linter))
    linter.register_checker(TrivialWrapperChecker(linter))
    linter.register_checker(ReexportAssignmentChecker(linter))
    linter.register_checker(SuppressionCommentChecker(linter))
    linter.register_checker(SnapshotAssertionChecker(linter))
    linter.register_checker(TypeAliasChecker(linter))
    linter.register_checker(FutureAnnotationsChecker(linter))
