"""Scaling regression tests for dataclass inherited-layout analysis."""

from __future__ import annotations

import types
import typing as typ

import df12_python_lints._dataclass_state as dataclass_state
from df12_python_lints._dataclass_analysis import LayoutAnalyzer
from df12_python_lints._dataclass_inference import inferred_class
from tests.dataclass_slots_support import module_classes, parse_module

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import pytest
    from astroid import nodes

    from df12_python_lints._dataclass_inference import Layout


def test_deep_layout_chain_is_classified_once_per_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memoized layouts keep a deep single-inheritance pass linear."""
    depth = 80
    declarations = ["@dataclasses.dataclass\nclass Node0:\n    value_0: int"]
    declarations.extend(
        f"@dataclasses.dataclass\nclass Node{index}(Node{index - 1}):"
        f"\n    value_{index}: int"
        for index in range(1, depth)
    )
    module = parse_module("import dataclasses\n\n" + "\n\n".join(declarations))
    classes = module_classes(module)
    local_layout_calls = 0
    original_local_layout = LayoutAnalyzer._local_layout

    def counting_local_layout(analyzer: LayoutAnalyzer, node: nodes.ClassDef) -> Layout:
        """Count uncached local-layout classifications."""
        nonlocal local_layout_calls
        local_layout_calls += 1
        return original_local_layout(analyzer, node)

    monkeypatch.setattr(LayoutAnalyzer, "_local_layout", counting_local_layout)
    analyzer = LayoutAnalyzer(module)

    assert all(analyzer.is_eligible(node) for node in reversed(classes))
    assert local_layout_calls <= depth - 1, (
        f"expected linear layout analysis, got {local_layout_calls} calls"
    )


def test_deep_layout_chain_resolves_state_once_per_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memoized state prevents repeated ancestor walks in deep lineages."""
    depth = 80
    declarations = ["@dataclasses.dataclass\nclass Node0:\n    value_0: int"]
    declarations.extend(
        f"@dataclasses.dataclass\nclass Node{index}(Node{index - 1}):"
        f"\n    value_{index}: int"
        for index in range(1, depth)
    )
    module = parse_module("import dataclasses\n\n" + "\n\n".join(declarations))
    local_state_calls = 0
    original_local_instance_state = dataclass_state._local_instance_state

    def counting_local_instance_state(
        node: nodes.ClassDef,
    ) -> cabc.Iterator[str]:
        """Count the local state work underlying inherited state analysis."""
        nonlocal local_state_calls
        local_state_calls += 1
        yield from original_local_instance_state(node)

    monkeypatch.setattr(
        dataclass_state, "_local_instance_state", counting_local_instance_state
    )
    analyzer = LayoutAnalyzer(module)

    assert all(analyzer.is_eligible(node) for node in reversed(module_classes(module)))
    assert local_state_calls <= depth + 1, (
        "expected linear state analysis including the shared object base, "
        f"got {local_state_calls} local walks"
    )


def test_ambiguous_inference_stops_after_two_candidates() -> None:
    """Ambiguity detection does not consume an unbounded inference stream."""
    yielded = 0

    def many_candidates() -> cabc.Iterator[nodes.NodeNG]:
        """Yield enough opaque candidates to expose eager materialization."""
        nonlocal yielded
        while True:
            yielded += 1
            yield typ.cast("nodes.NodeNG", object())

    base = typ.cast("nodes.NodeNG", types.SimpleNamespace(infer=many_candidates))

    assert inferred_class(base) is None
    assert yielded == 2, f"expected two inference candidates, consumed {yielded}"
