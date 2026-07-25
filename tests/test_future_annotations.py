"""Tests for the redundant future-annotations checker."""

from __future__ import annotations

import typing as typ

import astroid
from pylint import testutils
from pylint.testutils import set_config

from df12_python_lints.future_annotations import FutureAnnotationsChecker


def _extract_importfrom(code: str) -> astroid.nodes.ImportFrom:
    """Extract the ``#@``-marked from-import statement from *code*."""
    return typ.cast("astroid.nodes.ImportFrom", astroid.extract_node(code))


class TestFutureAnnotationsChecker(testutils.CheckerTestCase):
    """Exercise the py-version-gated future-import check."""

    CHECKER_CLASS = FutureAnnotationsChecker

    @set_config(py_version=(3, 14))
    def test_flags_future_annotations_on_modern_baseline(self) -> None:
        """The future import is reported once the baseline reaches 3.14."""
        node = _extract_importfrom("from __future__ import annotations  #@")
        with self.assertAddsMessages(
            testutils.MessageTest("redundant-future-annotations", node=node),
            ignore_position=True,
        ):
            self.checker.visit_importfrom(node)

    @set_config(py_version=(3, 15))
    def test_flags_on_later_baselines_too(self) -> None:
        """Baselines beyond 3.14 keep reporting the import."""
        node = _extract_importfrom("from __future__ import annotations  #@")
        with self.assertAddsMessages(
            testutils.MessageTest("redundant-future-annotations", node=node),
            ignore_position=True,
        ):
            self.checker.visit_importfrom(node)

    @set_config(py_version=(3, 13))
    def test_silent_below_baseline(self) -> None:
        """Projects still supporting 3.13 keep the import without noise."""
        node = _extract_importfrom("from __future__ import annotations  #@")
        with self.assertNoMessages():
            self.checker.visit_importfrom(node)

    @set_config(py_version=(3, 14))
    def test_ignores_other_future_imports(self) -> None:
        """Future imports other than ``annotations`` are left alone."""
        node = _extract_importfrom("from __future__ import barry_as_FLUFL  #@")
        with self.assertNoMessages():
            self.checker.visit_importfrom(node)

    @set_config(py_version=(3, 14))
    def test_ignores_ordinary_from_imports(self) -> None:
        """A from-import of a name called annotations is not the pragma."""
        node = _extract_importfrom("from mypkg import annotations  #@")
        with self.assertNoMessages():
            self.checker.visit_importfrom(node)
