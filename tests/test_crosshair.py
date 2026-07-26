"""CrossHair model checks for the pure selection kernels.

The kernels in ``df12_python_lints._chains`` carry PEP 316 contracts;
CrossHair explores their bounded input space symbolically (the ``pre:``
clauses cap the chain length and draw subjects from a two-symbol
alphabet) and reports any assignment that violates a ``post:`` clause.
The bounds are deliberately tight so the search can *confirm* every
postcondition over all paths rather than merely exhaust its budget.

The check runs a Z3-backed search, so it is gated behind
``RUN_CROSSHAIR=1`` (use ``make crosshair``) rather than running on
every push, per the project verification tiering.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess  # ruff:ignore[suspicious-subprocess-import]  # fixed argv, no shell

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    os.environ.get("RUN_CROSSHAIR") != "1",
    reason="symbolic checking is opt-in; run via make crosshair",
)
@pytest.mark.timeout(300)
def test_chain_kernels_satisfy_contracts() -> None:
    """CrossHair finds no counterexample to the kernel contracts."""
    uv = shutil.which("uv")
    assert uv is not None, "uv is required to run CrossHair"
    result = subprocess.run(  # ruff:ignore[subprocess-without-shell-equals-true]  # fixed argv, no untrusted input
        [
            uv,
            "run",
            "crosshair",
            "check",
            "--report_all",
            "--analysis_kind=PEP316",
            # Give the search a real time budget per postcondition: the
            # default five-iteration cap stops before it can exhaust the
            # bounded paths, so confirmation would be unreachable. The
            # kernels confirm well inside this cap; it only bounds the
            # pathological case, keeping the run under the timeout below.
            "--per_condition_timeout=60",
            "df12_python_lints._chains",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
        timeout=280,
    )
    assert result.returncode == 0, (
        f"CrossHair reported a contract violation:\n{result.stdout}{result.stderr}"
    )
    assert "no checkable functions" not in result.stderr.lower(), (
        "the kernels must remain visible to CrossHair; a vacuous pass "
        "means the contracts or annotations stopped resolving"
    )
    # With --report_all every postcondition yields a per-line verdict:
    # "Confirmed over all paths." when the search exhausts every path, or
    # "Not confirmed." when the budget runs out first. The bounded
    # preconditions in _chains.py make full confirmation reachable, so we
    # demand it: one post: clause in repeated_subject() plus three in
    # narrowing_prefix() give four postconditions that must each confirm.
    # A "Not confirmed" verdict is a failure, not a pass.
    confirmations = [
        line
        for line in result.stdout.splitlines()
        if "_chains.py:" in line and "Confirmed over all paths" in line
    ]
    expected_confirmations = 4
    assert len(confirmations) >= expected_confirmations, (
        "every PEP 316 postcondition must be confirmed over all paths "
        f"(expected {expected_confirmations}, got {len(confirmations)}):\n"
        f"{result.stdout}"
    )
