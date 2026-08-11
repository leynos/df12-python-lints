"""Recognition and state tests for the closed-dataclass slots checker."""

from __future__ import annotations

import pytest
from pylint import testutils

from df12_python_lints.dataclass_slots import _MSGS, DataclassSlotsChecker
from tests.dataclass_slots_support import (
    DataclassSlotsTestCase,
    module_classes,
    parse_module,
)


class TestDataclassSlotsChecker(DataclassSlotsTestCase):
    """Exercise decorator recognition and closed-state evidence."""

    @pytest.mark.parametrize(
        ("class_var_import", "annotation"),
        [
            ("import typing_extensions", "typing_extensions.ClassVar[int]"),
            ("from typing_extensions import ClassVar as CV", "CV[int]"),
        ],
    )
    def test_typing_extensions_classvar_is_class_only_state(
        self, class_var_import: str, annotation: str
    ) -> None:
        """Backport ClassVar imports do not declare slotted instance state."""
        self.assert_silent(
            f"""
            import dataclasses
            {class_var_import}

            @dataclasses.dataclass
            class Record:
                value: int
                cache: {annotation} = 0

                def reset(self):
                    self.cache = 1
            """
        )

    def test_diagnostic_contract_includes_decorator_location(self) -> None:
        """The stable diagnostic payload identifies the class and decorator."""
        module = parse_module(
            """
            import dataclasses

            @dataclasses.dataclass
            class Record:
                value: int
            """
        )
        class_node = module_classes(module)[0]
        linter = testutils.UnittestLinter()
        checker = DataclassSlotsChecker(linter)
        checker.visit_module(module)
        checker.visit_classdef(class_node)
        message = linter.release_messages()[0]
        assert {
            "symbol": message.msg_id,
            "message": _MSGS["R9111"][0] % message.args,
            "class_argument": message.args,
            "line": message.line,
            "column": message.col_offset,
        } == {
            "symbol": "prefer-slots-for-dataclass",
            "message": "Dataclass 'Record' should declare slots=True",
            "class_argument": ("Record",),
            "line": 4,
            "column": 1,
        }, "the diagnostic contract or decorator attachment changed"

    @pytest.mark.parametrize(
        "decorator",
        [
            "dataclasses.dataclass",
            "dataclasses.dataclass()",
            "dataclasses.dataclass(slots=False)",
            "dataclasses.dataclass(slots=1)",
            "dataclasses.dataclass(slots=SLOTS)",
            "dataclasses.dataclass(**DATACLASS_OPTIONS)",
            "dataclasses.dataclass(frozen=True)",
            "dataclasses.dataclass(order=True)",
            "dataclasses.dataclass(eq=False)",
            "dataclasses.dataclass(kw_only=True)",
            "dataclasses.dataclass(weakref_slot=True)",
        ],
    )
    def test_reports_non_literal_slots(self, decorator: str) -> None:
        """Only the singleton literal ``True`` requests generated slots."""
        self.assert_reports(
            f"""
            import dataclasses
            SLOTS = True
            DATACLASS_OPTIONS = {{"slots": True}}

            @{decorator}
            class Record:
                value: int
            """,
            "Record",
        )

    @pytest.mark.parametrize(
        ("import_line", "decorator"),
        [
            ("import dataclasses as dc", "dc.dataclass"),
            ("from dataclasses import dataclass as record", "record"),
        ],
    )
    def test_reports_import_aliases(self, import_line: str, decorator: str) -> None:
        """Module and direct decorator aliases retain their stdlib identity."""
        self.assert_reports(
            f"""
            {import_line}

            @{decorator}
            class Record:
                value: int
            """,
            "Record",
        )

    def test_reports_public_private_nested_and_zero_field_classes(self) -> None:
        """Naming, nesting, exports, and field count do not create exemptions."""
        self.assert_reports(
            """
            import dataclasses
            __all__ = ["Public"]

            @dataclasses.dataclass
            class Public:
                value: int

            @dataclasses.dataclass
            class _Private:
                pass

            class Namespace:
                @dataclasses.dataclass
                class Nested:
                    value: int
            """,
            "Public",
            "_Private",
            "Nested",
        )

    def test_reports_safe_decorator_orderings(self) -> None:
        """Outer decorators and an identity-preserving inner final are safe."""
        self.assert_reports(
            """
            import dataclasses
            import typing

            def register(cls):
                return cls

            @register
            @dataclasses.dataclass
            class Outer:
                value: int

            @dataclasses.dataclass
            @typing.final
            class Final:
                value: int
            """,
            "Outer",
            "Final",
        )

    @pytest.mark.parametrize(
        "decorator",
        [
            "dataclasses.dataclass(slots=True)",
            "dataclasses.dataclass(slots=True, weakref_slot=True)",
        ],
    )
    def test_literal_slots_is_silent(self, decorator: str) -> None:
        """Literal generated slots satisfy the policy."""
        self.assert_silent(
            f"""
            import dataclasses

            @{decorator}
            class Record:
                value: int
            """
        )

    @pytest.mark.parametrize(
        "declaration",
        [
            '__slots__ = "value"',
            '__slots__ = ("value", "__dict__")',
            '__slots__ = ["value"]',
            '__slots__ = {"value"}',
            '__slots__ = {"value": "field documentation"}',
            '__slots__: typing.ClassVar[tuple[str, ...]] = ("value",)',
            '_SLOT_NAMES = ("value",)\n__slots__ = _SLOT_NAMES',
        ],
    )
    def test_manual_slots_is_silent(self, declaration: str) -> None:
        """Valid literal and locally resolved slot layouts satisfy the rule."""
        declaration = declaration.replace("\n", "\n                ")
        self.assert_silent(
            f"""
            import dataclasses
            import typing

            @dataclasses.dataclass
            class Record:
                {declaration}
                value: int
            """
        )

    def test_annotation_only_slots_still_reports(self) -> None:
        """A slots annotation without a runtime value creates no layout."""
        self.assert_reports(
            """
            import dataclasses
            import typing

            @dataclasses.dataclass
            class Record:
                __slots__: typing.ClassVar[tuple[str, ...]]
                value: int
            """,
            "Record",
        )

    @pytest.mark.parametrize(
        "slot_value",
        [
            "42",
            '("value", 42)',
            '"not a valid identifier"',
            "SLOT_NAMES",
            '("value",) if condition else ("other",)',
        ],
        ids=["integer", "mixed", "invalid-name", "unresolved", "ambiguous"],
    )
    def test_unvalidated_manual_slots_still_reports(self, slot_value: str) -> None:
        """Invalid, unresolved, and ambiguous slot values do not qualify."""
        self.assert_reports(
            f"""
            import dataclasses

            @dataclasses.dataclass
            class Record:
                __slots__ = {slot_value}
                value: int
            """,
            "Record",
        )

    @pytest.mark.parametrize(
        "source",
        [
            """
            def dataclass(cls): return cls
            @dataclass
            class Record: pass
            """,
            """
            import dataclasses
            dataclasses = factory()
            @dataclasses.dataclass
            class Record: pass
            """,
            """
            import pydantic.dataclasses
            @pydantic.dataclasses.dataclass
            class Record: pass
            """,
            """
            import attrs
            @attrs.define
            class Record: pass
            """,
            """
            import msgspec
            class Record(msgspec.Struct): pass
            """,
            """
            import typing
            @typing.dataclass_transform()
            def model(cls): return cls
            @model
            class Record: pass
            """,
        ],
    )
    def test_unrelated_decorators_are_silent(self, source: str) -> None:
        """Spelling and dataclass-like frameworks cannot trigger the rule."""
        self.assert_silent(source)

    @pytest.mark.parametrize(
        "method",
        [
            "def reveal(this): return this.__dict__",
            "def reveal(this): return vars(this)",
            "def mutate(this, name): setattr(this, name, 1)",
            "def mutate(this, name): delattr(this, name)",
            "def mutate(this): this.extra = 1",
            "def mutate(this): this.extra += 1",
            "def mutate(this): del this.extra",
            "def mutate(this, name): object.__setattr__(this, name, 1)",
            'def mutate(this): object.__setattr__(this, "extra", 1)',
        ],
    )
    def test_open_state_evidence_is_silent(self, method: str) -> None:
        """Direct method evidence of dictionary-backed state suppresses."""
        self.assert_silent(
            f"""
            import dataclasses

            @dataclasses.dataclass
            class Record:
                value: int
                {method}
            """
        )

    def test_cached_property_is_silent(self) -> None:
        """The real dictionary-backed cached property suppresses."""
        self.assert_silent(
            """
            import dataclasses
            import functools

            @dataclasses.dataclass
            class Record:
                value: int

                @functools.cached_property
                def doubled(self):
                    return self.value * 2
            """
        )

    def test_declared_init_false_field_assignment_still_reports(self) -> None:
        """Assignments to declared fields remain slot-compatible."""
        self.assert_reports(
            """
            import dataclasses

            @dataclasses.dataclass
            class Record:
                value: int
                cached: int = dataclasses.field(init=False)

                def __post_init__(instance):
                    instance.cached = instance.value
            """,
            "Record",
        )

    @pytest.mark.parametrize(
        "declaration",
        [
            "cache = 0",
            "cache: typing.ClassVar[int] = 0",
            "cache: dataclasses.InitVar[int] = 0",
        ],
    )
    def test_class_only_attribute_assignment_is_open_state(
        self, declaration: str
    ) -> None:
        """Assigning through an instance to class-only state requires a dict."""
        self.assert_silent(
            f"""
            import dataclasses
            import typing

            @dataclasses.dataclass
            class Record:
                value: int
                {declaration}

                def reset(self):
                    self.cache = 1
            """
        )
