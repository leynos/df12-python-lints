"""Exact, reviewable output contracts for the stable CLI messages.

Each case compares a command's full output with a golden file under
``tests/data/cli_output``. Regenerate them deliberately with
``DF12_UPDATE_GOLDEN=1 pytest tests/test_duplication_output.py`` and review the
diff; a changed message is a contract change.
"""

from __future__ import annotations

import os
import pathlib

import pytest
from duplication_support import (
    Script,
    family,
    location,
    make_repository,
    report,
    write_fake_nose,
)

from df12_python_lints.duplication import cli

_GOLDEN = pathlib.Path(__file__).parent / "data" / "cli_output"
_A = location("src/a.py", 1, 20, "parse")
_B = location("src/b.py", 1, 20, "parse")
_ALLOW = (
    "[[tool.duplication_gate.allow]]\n"
    'members = ["src/a.py::parse", "src/b.py::parse"]\nreason = "r"\n'
)
_STALE = '[[tool.duplication_gate.allow]]\nunit = "src/z.py"\nreason = "old"\n'


def _compare(name: str, actual: str) -> None:
    """Compare ``actual`` with the golden file, or rewrite it on request."""
    path = _GOLDEN / f"{name}.txt"
    if os.environ.get("DF12_UPDATE_GOLDEN"):
        path.write_text(actual, encoding="utf-8")
    assert actual == path.read_text(encoding="utf-8"), f"{name} output changed"


_CASES = {
    "clean": (report(), ""),
    "blocking": (report(family(_A, _B)), ""),
    "unmatched": (report(), _STALE),
    "saturated_blocking": (report(family(_A, _B), total=40), ""),
    "saturated_all_allowed": (report(family(_A, _B), total=40), _ALLOW),
}


@pytest.mark.parametrize("name", sorted(_CASES))
def test_check_output_matches_the_golden_file(
    name: str, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stdout, stderr and the exit status of each stable verdict are fixed."""
    stdout, extra = _CASES[name]
    repo = make_repository(tmp_path / "repo", extra=extra)
    write_fake_nose(repo / "n", Script(stdout=stdout))
    code = cli.main(["check", "--repository", str(repo), "--binary", "n"])
    captured = capsys.readouterr()
    _compare(
        name, f"exit: {code}\n--- stdout\n{captured.out}--- stderr\n{captured.err}"
    )
