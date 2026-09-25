"""Contract-test that both coverage lanes measure on the same interpreter.

The shared ``generate-coverage`` action creates its ``.venv-coverage`` with a
bare ``uv venv``, which takes whatever interpreter uv discovers first. When uv
0.12.19 began picking 3.14, pull requests measured on 3.14 against a baseline
main had measured on 3.13, and the ratchet failed on changes that touched no
code. Each coverage step therefore pins ``UV_PYTHON`` to the version its job's
``setup-python`` step installs, and the two lanes pin the same version.
"""

from __future__ import annotations

import pathlib
import typing as typ

import pytest
import yaml

type Mapping = dict[str, object]

WORKFLOWS = pathlib.Path(__file__).resolve().parents[1] / ".github/workflows"
#: Each coverage lane, by workflow file and job.
LANES = (("ci.yml", "lint-test"), ("coverage-main.yml", "coverage-upload"))


def _steps(workflow: str, job: str) -> list[Mapping]:
    """Return the mapping-shaped steps of ``job`` in ``workflow``."""
    match yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8")):
        case {"jobs": {**jobs}} if job in jobs:
            match jobs[job]:
                case {"steps": [*steps]}:
                    return [step for step in steps if _is_mapping(step)]
                case _:
                    pass
        case _:
            pass
    pytest.fail(f"{workflow} must declare {job} with a steps list")


def _is_mapping(value: object) -> typ.TypeGuard[Mapping]:
    """Report whether a parsed YAML value is a mapping."""
    match value:
        case dict():
            return True
        case _:
            return False


def _one(steps: list[Mapping], action: str) -> Mapping:
    """Return the one step that calls ``action``."""
    found = [step for step in steps if f"{action}@" in str(step.get("uses", ""))]
    assert len(found) == 1, f"expected one {action} step, found {len(found)}"
    return found[0]


def _entry(step: Mapping, block: str, key: str) -> str:
    """Return ``step[block][key]`` as text, or an empty string when absent."""
    match step.get(block):
        case {**entries} if key in entries:
            return str(entries[key])
        case _:
            return ""


def _pinned_interpreter(workflow: str, job: str) -> tuple[str, str]:
    """Return the coverage step's ``UV_PYTHON`` and the job's Python version."""
    steps = _steps(workflow, job)
    coverage = _one(steps, "leynos/shared-actions/.github/actions/generate-coverage")
    setup = _one(steps, "actions/setup-python")
    return _entry(coverage, "env", "UV_PYTHON"), _entry(setup, "with", "python-version")


@pytest.mark.parametrize(("workflow", "job"), LANES)
def test_the_coverage_step_pins_the_installed_interpreter(
    workflow: str, job: str
) -> None:
    """Each coverage step measures on the interpreter its job installs."""
    pinned, installed = _pinned_interpreter(workflow, job)
    assert installed, f"{workflow} must install a named Python version"
    assert pinned == installed, (
        f"{workflow}'s coverage step must set UV_PYTHON to {installed!r}, got "
        f"{pinned!r}; otherwise uv picks the newest interpreter it finds"
    )


def test_both_lanes_measure_on_one_interpreter() -> None:
    """The pull-request ratchet compares against a baseline on its own Python."""
    versions = {_pinned_interpreter(workflow, job)[0] for workflow, job in LANES}
    assert len(versions) == 1, f"the coverage lanes pin different Pythons: {versions}"
