"""Run manifest-editing workers as real, concurrent operating-system processes.

The workers are plain ``python -c`` children rather than ``multiprocessing``
processes, so they behave the same under a coverage tool that swaps the module
loader (slipcover's loader breaks ``spawn`` imports). Each worker applies a
list of operations to one manifest path through the shared transaction.
"""

from __future__ import annotations

import contextlib
import json
import subprocess  # ruff: ignore[suspicious-subprocess-import] - spawns the test workers.
import sys
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

_WORKER = """
import json, pathlib, sys
from df12_python_lints import _manifest
from df12_python_lints.duplication.allowlist import record_allow_entry

path = pathlib.Path(sys.argv[1])


def setter(key):
    def edit(document):
        import tomlkit
        tool = document.setdefault("tool", tomlkit.table(is_super_table=True))
        tool.setdefault("probe", tomlkit.table())[key] = True
        return True
    return edit


for operation, argument in json.loads(sys.argv[2]):
    if operation == "set":
        _manifest.edit_manifest(path, setter(argument), extra="duplication")
    elif operation == "noop":
        _manifest.edit_manifest(path, lambda document: False, extra="duplication")
    elif operation == "allow":
        record_allow_entry(path, members=[argument, argument + "-b"], reason="r")
    else:
        raise SystemExit(f"unknown operation {operation!r}")
"""

type Operation = tuple[str, str]


def run_workers(
    jobs: cabc.Sequence[tuple[pathlib.Path, cabc.Sequence[Operation]]],
    *,
    timeout: int = 180,
) -> None:
    """Start one child per job at once, wait for all, and require clean exits.

    Parameters
    ----------
    jobs : collections.abc.Sequence
        Pairs of manifest spelling and operations. ``("set", key)``
        sets ``[tool.probe].key``, ``("noop", "")`` makes an edit that changes
        nothing, and ``("allow", member)`` records a duplication exception.
    timeout : int
        Seconds to wait for each child.
    """
    with contextlib.ExitStack() as stack:
        children = [
            stack.enter_context(
                subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argument vector.
                    [sys.executable, "-c", _WORKER, str(path), json.dumps(list(ops))],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
            for path, ops in jobs
        ]
        for child in children:
            _, stderr = child.communicate(timeout=timeout)
            if child.returncode != 0:
                pytest.fail(f"a worker failed ({child.returncode}): {stderr}")
