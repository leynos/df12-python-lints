"""Exact, normalized contracts for the structured log records.

The records are compared with golden files under ``tests/data/log_records``
after replacing elapsed times. Their fields are bounded names and categories:
no repository name, no path, no free-form message. Regenerate deliberately with
``DF12_UPDATE_GOLDEN=1 pytest tests/test_log_records.py``.
"""

from __future__ import annotations

import logging
import os
import pathlib
import re

import pytest
from duplication_support import (
    Script,
    family,
    location,
    make_repository,
    report,
    write_fake_nose,
)
from skylos_support import make_repository as make_skylos_repository

from df12_python_lints import _log
from df12_python_lints.duplication import cli as duplication_cli
from df12_python_lints.skylos import cli as skylos_cli

_GOLDEN = pathlib.Path(__file__).parent / "data" / "log_records"
_PAIR = (location("src/a.py", 1, 20, "parse"), location("src/b.py", 1, 20, "parse"))


def _records(caplog: pytest.LogCaptureFixture) -> str:
    """Render the captured records with variable timings normalized."""
    lines = [
        re.sub(r"elapsed_seconds=[0-9.]+", "elapsed_seconds=<t>", record.getMessage())
        for record in caplog.records
    ]
    return "".join(f"{line}\n" for line in lines)


def _compare(name: str, actual: str) -> None:
    """Compare ``actual`` with the golden file, or rewrite it on request."""
    path = _GOLDEN / f"{name}.txt"
    if os.environ.get("DF12_UPDATE_GOLDEN"):
        path.write_text(actual, encoding="utf-8")
    assert actual == path.read_text(encoding="utf-8"), f"{name} records changed"


@pytest.fixture
def captured(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> pytest.LogCaptureFixture:
    """Capture every ``df12_python_lints`` record at debug level."""
    monkeypatch.setattr(_log.logger, "handlers", list(_log.logger.handlers))
    monkeypatch.setattr(_log.logger, "level", logging.NOTSET)
    caplog.set_level(logging.DEBUG, logger="df12_python_lints")
    return caplog


def test_duplication_check_records(
    tmp_path: pathlib.Path, captured: pytest.LogCaptureFixture
) -> None:
    """A blocking check logs the subprocess calls, the counts and the operation."""
    repo = make_repository(tmp_path / "repo")
    write_fake_nose(repo / "n", Script(stdout=report(family(*_PAIR))))
    duplication_cli.main([
        "--verbose",
        "check",
        "--repository",
        str(repo),
        "--binary",
        "n",
    ])
    _compare("duplication_check_blocking", _records(captured))


def test_duplication_failure_records(
    tmp_path: pathlib.Path, captured: pytest.LogCaptureFixture
) -> None:
    """A wrong detector version logs the failure by category only."""
    repo = make_repository(tmp_path / "repo")
    write_fake_nose(repo / "n", Script(stdout=report(), version="nose 9.9.9"))
    duplication_cli.main([
        "--verbose",
        "check",
        "--repository",
        str(repo),
        "--binary",
        "n",
    ])
    _compare("duplication_check_failure", _records(captured))


def test_skylos_validate_config_records(
    tmp_path: pathlib.Path, captured: pytest.LogCaptureFixture
) -> None:
    """A validation logs one operation record."""
    repo = make_skylos_repository(tmp_path / "repo")
    skylos_cli.main(["--verbose", "validate-config", "--repository", str(repo)])
    _compare("skylos_validate_config", _records(captured))
