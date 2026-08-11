"""Focused class-cell boundary tests for dataclass slot analysis."""

from __future__ import annotations

from tests.dataclass_slots_support import DataclassSlotsTestCase


class TestDataclassSlotsClassCells(DataclassSlotsTestCase):
    """Exercise nested class boundaries in replacement-class analysis."""

    def test_nested_helper_class_super_still_reports(self) -> None:
        """A helper class's class cell does not belong to the outer dataclass."""
        self.assert_reports(
            """
            import dataclasses

            @dataclasses.dataclass
            class Record:
                value: int

                def make_helper(self):
                    class Helper:
                        def method(self):
                            return super().method()

                    return Helper()
            """,
            "Record",
        )
