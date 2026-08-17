"""Hypothesis property tests for the checkers' decision kernels.

Where the example-based suites pin a handful of sizes and shapes, these
properties cover the whole bounded space: chains of any length, guard
runs of any length, arbitrarily nested literals, and generated pragma
comments.
"""

from __future__ import annotations

import math
import operator
import typing as typ

import astroid
from hypothesis import given, settings
from hypothesis import strategies as st
from pylint import testutils
from pylint.utils import ASTWalker

from df12_python_lints._chains import narrowing_prefix, repeated_subject
from df12_python_lints._dataclass_analysis import LayoutAnalyzer
from df12_python_lints.ambrleaks.scanner import shannon_entropy
from df12_python_lints.constant_chain import ConstantChainChecker
from df12_python_lints.match_dispatch import MatchDispatchChecker
from df12_python_lints.snapshot_asserts import SnapshotAssertionChecker
from tests.dataclass_slots_support import module_classes, parse_module

if typ.TYPE_CHECKING:
    from pylint.checkers import BaseChecker
# Constructed identifiers: a fixed prefix guarantees the name is never a
# Python keyword, avoiding the filtering trap.
_SUBJECTS = st.from_regex(r"v_[a-z]{1,6}", fullmatch=True)
_OTHER_NAMES = st.from_regex(r"w_[a-z]{1,6}", fullmatch=True)
_BREAKERS = st.from_regex(r"x_[a-z]{1,6}", fullmatch=True)
_WORDS = st.from_regex(r"[a-z]{2,8}", fullmatch=True)
_DATACLASS_KEYWORDS = (
    ("eq", "False"),
    ("frozen", "True"),
    ("kw_only", "True"),
    ("order", "True"),
    ("unsafe_hash", "True"),
)


def _walk_symbols(checker_class: type[BaseChecker], code: str) -> list[str]:
    """Collect the message symbols a checker emits over *code*."""
    linter = testutils.UnittestLinter()
    checker = checker_class(linter)
    walker = ASTWalker(linter)
    walker.add_checker(checker)
    walker.walk(astroid.parse(code))
    return [message.msg_id for message in linter.release_messages()]


def _constant_chain(subject: str, constants: list[int]) -> str:
    """Render an if/elif chain comparing *subject* with *constants*."""
    branches = [f"    if {subject} == {constants[0]}:\n        return 0\n"]
    branches.extend(
        f"    elif {subject} == {constant}:\n        return {index}\n"
        for index, constant in enumerate(constants[1:], start=1)
    )
    return f"def handle({subject}):\n{''.join(branches)}    return -1\n"


@st.composite
def _dataclass_keyword_order(
    draw: st.DrawFn,
) -> tuple[tuple[str, str], ...]:
    """Generate unique dataclass keywords in arbitrary lexical order."""
    irrelevant = draw(
        st.lists(
            st.sampled_from(_DATACLASS_KEYWORDS),
            unique_by=operator.itemgetter(0),
        )
    )
    slot_value = draw(st.sampled_from([None, "True", "False", "1", "SLOTS"]))
    keywords = irrelevant + ([] if slot_value is None else [("slots", slot_value)])
    return tuple(draw(st.permutations(keywords)))


class TestDataclassSlotsProperties:
    """Decorator keyword selection honours the lexical slots contract."""

    @settings(deadline=None)
    @given(keywords=_dataclass_keyword_order())
    def test_only_literal_slots_true_is_silent(
        self, keywords: tuple[tuple[str, str], ...]
    ) -> None:
        """Irrelevant options and ordering cannot change slot eligibility."""
        arguments = ", ".join(f"{name}={value}" for name, value in keywords)
        module = parse_module(
            f"""
            import dataclasses
            SLOTS = True
            @dataclasses.dataclass({arguments})
            class Record:
                value: int
            """
        )
        class_node = module_classes(module)[0]
        is_eligible = LayoutAnalyzer(module).is_eligible(class_node)
        expected = ("slots", "True") not in keywords
        assert is_eligible is expected, (
            f"eligibility mismatch: is_eligible={is_eligible}, keywords={keywords!r}"
        )


class TestConstantChainProperties:
    """Constant chains of any length behave uniformly."""

    @settings(deadline=None)
    @given(subject=_SUBJECTS, constants=st.lists(st.integers(), min_size=2, max_size=5))
    def test_constant_chain_always_fires(
        self, subject: str, constants: list[int]
    ) -> None:
        """Every all-constant chain of two or more branches is reported."""
        symbols = _walk_symbols(
            ConstantChainChecker, _constant_chain(subject, constants)
        )
        assert symbols == ["prefer-match-over-constant-chain"], (
            "an all-constant chain must fire exactly once"
        )

    @settings(deadline=None)
    @given(
        subject=_SUBJECTS,
        other=_OTHER_NAMES,
        constants=st.lists(st.integers(), min_size=2, max_size=4),
    )
    def test_variable_branch_poisons_chain(
        self, subject: str, other: str, constants: list[int]
    ) -> None:
        """Appending one variable comparison disqualifies any chain."""
        code = _constant_chain(subject, constants).replace(
            "    return -1\n",
            f"    elif {subject} == {other}:\n        return 99\n    return -1\n",
        )
        code = code.replace(
            f"def handle({subject}):", f"def handle({subject}, {other}):"
        )
        assert _walk_symbols(ConstantChainChecker, code) == [], (
            "a variable comparison must disqualify the chain"
        )


class TestGuardRunProperties:
    """Guard runs of any length report exactly once."""

    @settings(deadline=None)
    @given(subject=_SUBJECTS, run_length=st.integers(min_value=2, max_value=6))
    def test_guard_run_fires_exactly_once(self, subject: str, run_length: int) -> None:
        """A run of terminating isinstance guards yields one message."""
        guards = "".join(
            f"    if isinstance({subject}, T{index}):\n        return {index}\n"
            for index in range(run_length)
        )
        code = f"def dispatch({subject}):\n{guards}    return -1\n"
        symbols = _walk_symbols(MatchDispatchChecker, code)
        assert symbols == ["prefer-structural-pattern-matching"], (
            "a guard run must fire exactly once regardless of length"
        )


class TestSnapshotThresholdProperties:
    """The literal-size threshold depends only on leaf count."""

    @settings(deadline=None)
    @given(
        leaves=st.integers(min_value=1, max_value=20),
        split=st.integers(min_value=0, max_value=19),
    )
    def test_threshold_is_nesting_invariant(self, leaves: int, split: int) -> None:
        """Firing depends on leaf count, not on how leaves are nested."""
        inner = min(split, leaves - 1)
        flat = ", ".join("1" for _ in range(leaves - inner))
        nested = ", ".join("2" for _ in range(inner))
        literal = f"[{flat}, [{nested}]]" if inner else f"[{flat}]"
        code = f"def test_out(result):\n    assert result == {literal}\n"
        symbols = _walk_symbols(SnapshotAssertionChecker, code)
        expected = ["prefer-snapshot-assertion"] if leaves >= 8 else []
        assert symbols == expected, "firing must depend only on the total leaf count"


class TestPureKernelProperties:
    """The extracted selection kernels honour their contracts."""

    @settings(deadline=None)
    @given(subject_sets=st.lists(st.frozensets(_SUBJECTS, max_size=3), max_size=6))
    def test_repeated_subject_appears_twice(
        self, subject_sets: list[frozenset[str]]
    ) -> None:
        """Any returned subject occurs in at least two of the sets."""
        result = repeated_subject(tuple(subject_sets))
        if result is not None:
            occurrences = sum(result in subjects for subjects in subject_sets)
            assert occurrences >= 2, "a dispatch subject must repeat"

    @settings(deadline=None)
    @given(subject_sets=st.lists(st.frozensets(_SUBJECTS, max_size=3), max_size=6))
    def test_narrowing_prefix_is_common_to_prefix(
        self, subject_sets: list[frozenset[str]]
    ) -> None:
        """The returned subjects are common to every set in the prefix."""
        length, common = narrowing_prefix(tuple(subject_sets))
        assert length <= len(subject_sets), "prefix cannot exceed the input"
        if length:
            assert common, "a nonzero prefix must share a subject"
            assert all(common <= subjects for subjects in subject_sets[:length]), (
                "common subjects must appear in every prefix set"
            )

    @settings(deadline=None)
    @given(subject=_SUBJECTS, count=st.integers(min_value=2, max_value=6))
    def test_repeated_subject_returns_shared_subject(
        self, subject: str, count: int
    ) -> None:
        """A subject present in every set is the exact one returned."""
        subject_sets = tuple(frozenset({subject}) for _ in range(count))
        assert repeated_subject(subject_sets) == subject, (
            "a subject shared by every set must be the one returned"
        )

    @settings(deadline=None)
    @given(subjects=st.lists(_SUBJECTS, min_size=2, max_size=6, unique=True))
    def test_repeated_subject_none_when_all_distinct(self, subjects: list[str]) -> None:
        """Distinct singleton sets share no subject, so None is returned."""
        subject_sets = tuple(frozenset({subject}) for subject in subjects)
        assert repeated_subject(subject_sets) is None, (
            "singleton sets sharing no subject must return None"
        )

    @settings(deadline=None)
    @given(
        subject=_SUBJECTS,
        extras=st.lists(_OTHER_NAMES, min_size=1, max_size=6, unique=True),
        breaker=st.frozensets(_BREAKERS, min_size=1, max_size=3),
    )
    def test_narrowing_prefix_spans_shared_subject(
        self, subject: str, extras: list[str], breaker: frozenset[str]
    ) -> None:
        """A shared subject spans the prefix until a disjoint set breaks it."""
        prefix = tuple(frozenset({subject, extra}) for extra in extras)
        length, common = narrowing_prefix((*prefix, breaker))
        assert length == len(extras), (
            "the prefix must span exactly the sets sharing the subject"
        )
        assert subject in common, "the shared subject must remain in the common set"


class TestEntropyProperties:
    """Shannon entropy honours its algebraic invariants."""

    @settings(deadline=None)
    @given(text=st.text(min_size=1, max_size=64))
    def test_entropy_bounds(self, text: str) -> None:
        """Entropy sits between zero and log2 of the alphabet size."""
        entropy = shannon_entropy(text)
        assert entropy >= 0.0, "entropy is never negative"
        upper = math.log2(len(set(text))) if len(set(text)) > 1 else 0.0
        assert entropy <= upper + 1e-9, "entropy is bounded by the alphabet"

    @settings(deadline=None)
    @given(
        characters=st.sets(
            st.characters(min_codepoint=33, max_codepoint=126),
            min_size=2,
            max_size=16,
        )
    )
    def test_entropy_of_distinct_characters_is_log2(self, characters: set[str]) -> None:
        """Distinct characters, each once, give entropy of log2 of the count."""
        text = "".join(characters)
        assert abs(shannon_entropy(text) - math.log2(len(characters))) < 1e-9, (
            "a uniform distribution over n symbols has entropy log2(n)"
        )

    @settings(deadline=None)
    @given(
        text=st.text(min_size=1, max_size=32),
        repeats=st.integers(min_value=1, max_value=4),
    )
    def test_entropy_repetition_invariant(self, text: str, repeats: int) -> None:
        """Repeating a string does not change its entropy."""
        assert abs(shannon_entropy(text) - shannon_entropy(text * repeats)) < 1e-9, (
            "entropy must be invariant under repetition"
        )
