"""Safety-exemption and inheritance tests for dataclass slots."""

from __future__ import annotations

import pytest

from tests.dataclass_slots_support import DataclassSlotsTestCase


class TestDataclassSlotsSafety(DataclassSlotsTestCase):
    """Exercise replacement-class and inherited-layout hold-tongue rules."""

    @pytest.mark.parametrize(
        "source",
        [
            """
            import abc
            import dataclasses
            @dataclasses.dataclass
            class Record(abc.ABC): pass
            """,
            """
            import dataclasses
            import typing
            @dataclasses.dataclass
            class Record(typing.Protocol): pass
            """,
            """
            import abc
            import dataclasses
            @dataclasses.dataclass
            class Record:
                @abc.abstractmethod
                def value(self): ...
            """,
            """
            import dataclasses
            @dataclasses.dataclass
            class Record:
                def __init_subclass__(cls): pass
            """,
            """
            import dataclasses
            @dataclasses.dataclass
            class Record(metaclass=type): pass
            """,
            """
            import dataclasses
            @dataclasses.dataclass
            class Record(flag=True): pass
            """,
        ],
    )
    def test_extension_boundaries_are_silent(self, source: str) -> None:
        """Explicit extension and class-creation boundaries suppress."""
        self.assert_silent(source)

    def test_unknown_inner_decorator_is_silent(self) -> None:
        """A decorator below dataclass may retain the original class."""
        self.assert_silent(
            """
            import dataclasses
            @dataclasses.dataclass
            @register
            class Record:
                value: int
            """
        )

    @pytest.mark.parametrize(
        "method",
        [
            "def method(self): return super().method()",
            "def method(self): return __class__.__name__",
        ],
    )
    def test_class_cell_hazards_are_silent(self, method: str) -> None:
        """Replacement-class closure hazards suppress on supported runtimes."""
        self.assert_silent(
            f"""
            import dataclasses
            @dataclasses.dataclass
            class Record:
                value: int
                {method}
            """
        )

    def test_two_argument_super_still_reports(self) -> None:
        """Explicit two-argument super does not close over the class cell."""
        self.assert_reports(
            """
            import dataclasses
            @dataclasses.dataclass
            class Record:
                value: int
                def method(self): return super(Record, self).__repr__()
            """,
            "Record",
        )

    @pytest.mark.parametrize("base", ["UnknownBase", "list", "tuple"])
    def test_unsafe_or_unknown_base_is_silent(self, base: str) -> None:
        """Unprovable and variable-length inherited layouts suppress."""
        self.assert_silent(
            f"""
            import dataclasses
            @dataclasses.dataclass
            class Record({base}):
                value: int
            """
        )

    def test_unslotted_local_base_is_silent(self) -> None:
        """An ordinary unslotted base already contributes a dictionary."""
        self.assert_silent(
            """
            import dataclasses
            class Base: pass
            @dataclasses.dataclass
            class Record(Base):
                value: int
            """
        )

    def test_reports_prospectively_slotted_single_inheritance(self) -> None:
        """A local dataclass chain can be made slot-only in one lint run."""
        self.assert_reports(
            """
            import dataclasses

            @dataclasses.dataclass
            class Base:
                value: int

            @dataclasses.dataclass
            class Child(Base):
                label: str
            """,
            "Base",
            "Child",
        )

    def test_explicit_slotted_base_allows_child_report(self) -> None:
        """A child of a proven local slotted base remains eligible."""
        self.assert_reports(
            """
            import dataclasses

            class Marker:
                __slots__ = ()

            @dataclasses.dataclass
            class Record(Marker):
                value: int
            """,
            "Record",
        )

    def test_multiple_inheritance_suppresses_bases_and_child(self) -> None:
        """Reverse analysis avoids independently slotting combined bases."""
        self.assert_silent(
            """
            import dataclasses
            @dataclasses.dataclass
            class Left:
                left: int
            @dataclasses.dataclass
            class Right:
                right: int
            @dataclasses.dataclass
            class Combined(Left, Right):
                value: int
            """
        )
