"""Represent and resolve inherited layouts for dataclass slot analysis.

The dataclass analyzer uses the ordered :class:`Layout` severity and the
conservative Astroid candidate resolver when classifying every base lineage.
"""

from __future__ import annotations

import enum
import itertools

from astroid import bases, exceptions, nodes, util

VARIABLE_LENGTH_BUILTIN_QNAMES = frozenset({
    "builtins.bytearray",
    "builtins.bytes",
    "builtins.dict",
    "builtins.list",
    "builtins.set",
    "builtins.str",
    "builtins.tuple",
})


class Layout(enum.IntEnum):
    """Describe a base lineage with explicit severity ordering."""

    NEUTRAL = 0
    SLOTTED = 1
    UNSAFE = 2


def inferred_class(base: nodes.NodeNG | bases.Proxy) -> nodes.ClassDef | None:
    """Infer one unambiguous class for *base*, or return ``None``."""
    try:
        inferred = tuple(itertools.islice(base.infer(), 2))
    except exceptions.InferenceError:
        return None
    if len(inferred) != 1 or inferred[0] is util.Uninferable:
        return None
    candidate = inferred[0]
    if isinstance(candidate, bases.Instance):
        # Astroid exposes no public route from an inferred Instance to its
        # underlying ClassDef; keep this private unwrapping covered by the
        # supported Pylint range and a focused regression test.
        candidate = candidate._proxied
    return candidate if isinstance(candidate, nodes.ClassDef) else None
