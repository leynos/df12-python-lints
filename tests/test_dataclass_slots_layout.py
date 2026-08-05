"""Focused inherited-layout tests for manual dataclass slots."""

from __future__ import annotations

from df12_python_lints._dataclass_analysis import LayoutAnalyzer
from df12_python_lints._dataclass_inference import Layout
from tests.dataclass_slots_support import (
    DataclassSlotsTestCase,
    module_classes,
    parse_module,
)


class TestDataclassSlotsLayout(DataclassSlotsTestCase):
    """Exercise explicit layouts that retain an instance dictionary."""

    def test_manual_dict_slot_base_makes_child_unsafe(self) -> None:
        """An inherited explicit dictionary cannot become a closed layout."""
        source = """
            import dataclasses

            @dataclasses.dataclass
            class Base:
                __slots__ = ("__dict__",)
                value: int

            @dataclasses.dataclass
            class Child(Base):
                label: str
        """
        module = parse_module(source)
        child = next(node for node in module_classes(module) if node.name == "Child")
        analyzer = LayoutAnalyzer(module)

        assert analyzer._base_layout(child.bases[0]) is Layout.UNSAFE
        assert not analyzer.is_eligible(child)
        self.assert_silent(source)
