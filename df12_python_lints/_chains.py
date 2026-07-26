"""Shared helpers for walking ``if``/``elif`` chains.

The dispatch-oriented checkers in this package all reason about a head
``if`` statement and the tests along its ``elif`` chain. These helpers keep
that traversal logic in one place. The pure selection kernels —
:func:`repeated_subject` and :func:`narrowing_prefix` — carry PEP 316
contracts so CrossHair can model-check them symbolically.

Examples
--------
Collect the branch tests of a chain rooted at ``node``::

    tests = elif_chain_tests(node)
"""

from __future__ import annotations

import collections

from astroid import nodes

MIN_DISPATCH_BRANCHES = 2


def repeated_subject(subject_sets: tuple[frozenset[str], ...]) -> str | None:
    """Return the subject shared by at least two of *subject_sets*.

    Ties break towards the most frequent, then lexically smallest,
    subject, so the result is deterministic.

    Parameters
    ----------
    subject_sets : tuple[frozenset[str], ...]
        The subjects named by each branch test, in source order.

    Returns
    -------
    str | None
        The dispatched-on subject, or ``None`` when no subject appears
        in at least two sets.

    The ``pre`` clauses bound CrossHair's symbolic domain to short chains
    drawn from a two-symbol alphabet so it can *confirm* the ``post``
    clause over every path rather than merely exhaust its budget. They
    scope the proof, not the runtime input: production callers pass
    arbitrary subject names, and Hypothesis exercises that unbounded
    domain (see :mod:`tests.test_properties`). The two symbols still
    span the behaviour that matters here — shared versus disjoint
    subjects, and frequency ties broken lexically.

    pre: len(subject_sets) <= 2
    pre: all(s <= {"a", "b"} for s in subject_sets)
    post: __return__ is None or sum(__return__ in s for s in subject_sets) >= 2

    Examples
    --------
    ``[{"v"}, {"v", "n"}]`` returns ``"v"``; disjoint sets return
    ``None``.
    """
    counts: collections.Counter[str] = collections.Counter()
    for subjects in subject_sets:
        counts.update(subjects)
    candidates = [s for s, n in counts.items() if n >= MIN_DISPATCH_BRANCHES]
    if not candidates:
        return None
    return min(candidates, key=lambda subject: (-counts[subject], subject))


def narrowing_prefix(
    subject_sets: tuple[frozenset[str], ...],
) -> tuple[int, frozenset[str]]:
    """Return the maximal narrowing prefix of *subject_sets*.

    The prefix extends while every set still shares at least one
    subject with all sets before it; the returned pair holds the prefix
    length and the subjects common to the whole prefix.

    Parameters
    ----------
    subject_sets : tuple[frozenset[str], ...]
        The subjects named by each consecutive guard, in source order.

    Returns
    -------
    tuple[int, frozenset[str]]
        The prefix length and the subjects common to the whole prefix;
        ``(0, frozenset())`` when the input is empty or starts with an
        empty set.

    As with :func:`repeated_subject`, the ``pre`` clauses bound
    CrossHair's symbolic domain to short chains over a two-symbol
    alphabet so it can confirm every ``post`` clause over all paths;
    they scope the proof, not the runtime input.

    pre: len(subject_sets) <= 2
    pre: all(s <= {"a", "b"} for s in subject_sets)
    post: __return__[0] <= len(subject_sets)
    post: all(__return__[1] <= s for s in subject_sets[: __return__[0]])
    post: __return__[0] == 0 or len(__return__[1]) > 0

    Examples
    --------
    ``[{"a", "b"}, {"a"}, {"c"}]`` returns ``(2, frozenset({"a"}))``.
    """
    # len() comparisons rather than truthiness: symbolic execution can
    # model integer comparisons where __bool__ coercion fails.
    if len(subject_sets) == 0 or len(subject_sets[0]) == 0:
        return (0, frozenset())
    common = subject_sets[0]
    length = 1
    for subjects in subject_sets[1:]:
        shared = common & subjects
        if not shared:
            break
        common = shared
        length += 1
    return (length, common)


def elif_chain_tests(node: nodes.If) -> list[nodes.NodeNG]:
    """Collect the test expressions of *node* and its ``elif`` chain.

    Parameters
    ----------
    node : nodes.If
        The head ``if`` statement of the chain.

    Returns
    -------
    list[nodes.NodeNG]
        The test expression of every branch, in source order.

    Examples
    --------
    For ``if a: ... elif b: ... else: ...`` the result holds the test
    nodes for ``a`` and ``b`` in source order.
    """
    tests = [node.test]
    current = node
    while True:
        match current.orelse:
            case [nodes.If() as nested]:
                current = nested
                tests.append(current.test)
            case _:
                break
    return tests


def is_elif_branch(node: nodes.If) -> bool:
    """Return whether *node* is the ``elif`` arm of an enclosing ``if``.

    Examples
    --------
    The ``elif`` in ``if a: ... elif b: ...`` reports ``True``; the head
    ``if`` reports ``False``.
    """
    match node.parent:
        case nodes.If() as parent if node in parent.orelse:
            return True
        case _:
            return False
