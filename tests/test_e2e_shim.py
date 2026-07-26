"""End-to-end tests running the plugin under the PyPy pylint shim.

The project's own lint gate runs pylint through
``leynos/pylint-pypy-shim``; these tests load the plugin into that same
runner (pinned to the ref the Makefile uses) and lint a fixture holding
one violation per checker, proving the plugin works under the shim
rather than only under the CPython test harness.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess  # ruff:ignore[suspicious-subprocess-import]  # fixed argv, no shell
import typing as typ

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

_EXPECTED_SYMBOLS = frozenset({
    "prefer-structural-pattern-matching",
    "assert-missing-message",
    "prefer-match-over-constant-chain",
    "trivial-attribute-wrapper",
    "reexport-by-assignment",
    "lint-suppression-without-explanation",
    "typecheck-suppression-without-explanation",
    "prefer-snapshot-assertion",
    "prefer-snapshot-substring",
    "trivial-alias-wrapper",
    "prefer-type-statement",
    "redundant-future-annotations",
})

_FIXTURE = '''\
"""Fixture holding one violation per df12 checker."""
from __future__ import annotations

import collections.abc as cabc
import os.path

join = os.path.join

Clock = cabc.Callable[[], float]


def walk(value):
    """Trigger prefer-structural-pattern-matching."""
    if isinstance(value, dict):
        return 1
    elif isinstance(value, list):
        return 2
    return 3


def classify(state):
    """Trigger prefer-match-over-constant-chain."""
    if state == "idle":
        return 1
    elif state == "stopping":
        return 2
    return 0


def get_name(user):
    """Trigger trivial-attribute-wrapper."""
    return user.profile.name


def helper(value):
    """Provide a target for trivial-alias-wrapper."""
    return value * 2


def alias(value):
    """Trigger trivial-alias-wrapper."""
    return helper(value)


def check(flag):
    """Trigger assert-missing-message."""
    assert flag


x = 1  # noqa: E501
y = 2  # type: ignore


def test_payload(result):
    """Trigger prefer-snapshot-assertion."""
    assert result == {
        "id": 1,
        "name": "alice",
        "roles": ["a", "b"],
        "active": True,
        "score": 2,
    }, "payload matches"


def test_report(output):
    """Trigger prefer-snapshot-substring."""
    assert "header" in output, "has header"
    assert "row" in output, "has row"
    assert "footer" in output, "has footer"
'''


def _shim_reference() -> str:
    """Read the pinned shim ref from the Makefile to avoid drift."""
    makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^PYLINT_PYPY_SHIM_REF \?= (\S+)$", makefile, re.MULTILINE)
    assert match is not None, "the Makefile must pin PYLINT_PYPY_SHIM_REF"
    return match.group(1)


def _run_shim_pylint(target: pathlib.Path) -> list[dict[str, typ.Any]]:
    """Lint *target* through the shim with the plugin loaded."""
    uv = shutil.which("uv") or str(pathlib.Path.home() / ".local/bin/uv")
    shim = f"git+https://github.com/leynos/pylint-pypy-shim.git@{_shim_reference()}"
    environment = os.environ | {
        "PYO3_USE_ABI3_FORWARD_COMPATIBILITY": "1",
        "UV_CACHE_DIR": ".uv-cache",
        "UV_TOOL_DIR": ".uv-tools",
        "PYTHONPATH": str(_REPO_ROOT),
    }
    command = [
        uv,
        "tool",
        "run",
        "--python",
        "pypy",
        "--from",
        shim,
        "pylint-pypy",
        "--load-plugins=df12_python_lints",
        "--disable=all",
        f"--enable={','.join(sorted(_EXPECTED_SYMBOLS))}",
        # py-version defaults to the running interpreter — PyPy, which
        # trails CPython — so pin the baseline the py-version-gated
        # checkers (prefer-type-statement, redundant-future-annotations)
        # are expected to fire on.
        "--py-version=3.14",
        "--output-format=json",
        str(target),
    ]
    result = subprocess.run(  # ruff:ignore[subprocess-without-shell-equals-true]  # fixed argv, no untrusted input
        command,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        env=environment,
        check=False,
        timeout=280,
    )
    assert result.stdout.strip(), (
        f"the shim produced no JSON output; stderr:\n{result.stderr}"
    )
    return json.loads(result.stdout)


@pytest.mark.timeout(300)
def test_all_checkers_fire_under_the_shim(tmp_path: pathlib.Path) -> None:
    """Every checker reports its fixture violation under the PyPy shim."""
    fixture = tmp_path / "fixture_violations.py"
    fixture.write_text(_FIXTURE, encoding="utf-8")
    messages = _run_shim_pylint(fixture)
    symbols = {message["symbol"] for message in messages}
    missing = _EXPECTED_SYMBOLS - symbols
    assert not missing, f"checkers silent under the shim: {sorted(missing)}"


@pytest.mark.timeout(300)
def test_clean_module_is_silent_under_the_shim(
    tmp_path: pathlib.Path,
) -> None:
    """A module with no violations produces no plugin messages."""
    fixture = tmp_path / "fixture_clean.py"
    fixture.write_text(
        '"""A module the df12 checkers have nothing to say about."""\n'
        "from os.path import join\n\n"
        '__all__ = ["join"]\n',
        encoding="utf-8",
    )
    messages = _run_shim_pylint(fixture)
    plugin_messages = [
        message for message in messages if message["symbol"] in _EXPECTED_SYMBOLS
    ]
    assert plugin_messages == [], "a clean module must stay clean"
