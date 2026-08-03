"""Scaling regression tests for dataclass inherited-layout analysis."""

from __future__ import annotations

import typing as typ

from df12_python_lints._dataclass_analysis import LayoutAnalyzer
from tests.dataclass_slots_support import module_classes, parse_module

if typ.TYPE_CHECKING:
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
