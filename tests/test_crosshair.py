"""CrossHair model checks for the pure selection kernels.

The kernels in ``df12_python_lints._chains`` carry PEP 316 contracts;
CrossHair explores their bounded input space symbolically (the ``pre:``
clauses cap the sequence length at six) and reports any assignment that
violates a ``post:`` clause.

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
    # "Confirmed over all paths." when the search completes, or "Not
    # confirmed." when the budget runs out without a counterexample.
    # These kernels currently exhaust the budget, so requiring full
    # confirmation would be permanently red; requiring a verdict per
    # contract still rules out a quiet vacuous pass.
    verdicts = [
        line
        for line in result.stdout.splitlines()
        if "_chains.py:" in line
        and ("Confirmed over all paths" in line or "Not confirmed" in line)
    ]
    minimum_contract_verdicts = 4
    assert len(verdicts) >= minimum_contract_verdicts, (
        f"each postcondition must produce an analysis verdict; got:\n{result.stdout}"
    )
