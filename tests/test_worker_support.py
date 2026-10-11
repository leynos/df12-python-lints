"""The concurrency helper reaps every child before it reports a failure."""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import] - spawns throwaway test children.
import sys

import worker_support


def _spawn(code: str) -> subprocess.Popen[str]:
    """Start a throwaway Python child running ``code``."""
    return subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argument vector.
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_a_timed_out_child_is_killed_and_reaped_before_reporting() -> None:
    """A hung child cannot outlive the helper, and a healthy one is still waited for."""
    hung = _spawn("import time; time.sleep(60)")
    fine = _spawn("pass")
    failures = worker_support._collect([hung, fine], timeout=1)
    assert failures == ["a worker timed out after 1 seconds"], failures
    assert hung.returncode is not None, "the hung child must have been reaped"
    assert fine.returncode == 0, "the healthy child must have been waited for"
