"""Contract tests for the Pylint lint tier.

The tier runs a pinned Pylint as a uv tool on managed PyPy 3.12. Two
properties of that tier are easy to lose without any test noticing: the
interpreter pin, which decides the grammar Pylint parses with, and the
`syntax-error` message, which decides whether a module that grammar cannot
parse fails the lint or is skipped without a word. Both regressed silently
before: a bare `pypy` moved to a newer PyPy with no commit here, and a
disabled `syntax-error` let unparsable modules go unlinted.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - the end-to-end test drives Make.
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE_PATH = _REPO_ROOT / "Makefile"
CONFIG_PATH = _REPO_ROOT / "pyproject.toml"

_PROBE_TARGET: str = "jm5-pylint-probe"


def _makefile_variable(name: str) -> str:
    """Return the value assigned to a Makefile variable.

    Parameters
    ----------
    name : str
        The variable name, assigned with ``=`` or ``?=``.

    Returns
    -------
    str
        The assigned value with surrounding whitespace removed.
    """
    # Join backslash continuations so a multi-line assignment reads whole.
    text = MAKEFILE_PATH.read_text(encoding="utf-8").replace("\\\n", " ")
    match = re.search(rf"^{re.escape(name)}\s*\??=\s*(.+)$", text, flags=re.MULTILINE)
    assert match is not None, f"{name} is not defined in the Makefile"
    return match.group(1).strip()


def test_pylint_tier_pins_the_interpreter() -> None:
    """The tier must name the interpreter whose grammar it parses with."""
    assert _makefile_variable("PYLINT_PYTHON") == "pypy@3.12", (
        "PYLINT_PYTHON must stay pypy@3.12: bare pypy follows uv's next release"
    )


def test_pylint_tier_runs_the_pinned_release_on_managed_python() -> None:
    """The tier must run the pinned Pylint on a uv-managed interpreter."""
    assert _makefile_variable("PYLINT_VERSION") == "4.0.9", (
        "PYLINT_VERSION must pin the reviewed Pylint release exactly"
    )
    command = _makefile_variable("PYLINT")
    for fragment in (
        "$(UV_GATE) tool --managed-python --python $(PYLINT_PYTHON)",
        "--from 'pylint==$(PYLINT_VERSION)' -- pylint",
    ):
        assert fragment in command, f"PYLINT must contain {fragment!r}: {command}"


def test_pylint_reports_unparsable_modules() -> None:
    """The Pylint policy must not disable `syntax-error`."""
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    disabled = config["tool"]["pylint"]["messages control"]["disable"]
    assert "syntax-error" not in disabled, (
        "pyproject.toml must not disable syntax-error: a module the interpreter "
        f"cannot parse would then be skipped silently; disable={disabled!r}"
    )


def _make_quoted(path: Path) -> str:
    """Quote a path for a shell word inside a Make recipe.

    Parameters
    ----------
    path : Path
        The path to quote.

    Returns
    -------
    str
        The shell-quoted path with each ``$`` doubled, so Make passes it to
        the shell as one literal word.
    """
    return shlex.quote(str(path)).replace("$", "$$")


def _run_configured_pylint(target: Path) -> subprocess.CompletedProcess[str]:
    """Run the Makefile's own `$(PYLINT)` command over one module.

    Parameters
    ----------
    target : Path
        The module to lint.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The finished Make process, with output captured.
    """
    make = shutil.which("make")
    assert make is not None, "make must be on PATH"
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argument list, no shell.
        [
            make,
            "--no-print-directory",
            "-s",
            "-C",
            str(_REPO_ROOT),
            "--eval",
            f"{_PROBE_TARGET}: ; $(PYLINT) {_make_quoted(target)}",
            _PROBE_TARGET,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


#: Variables the uv gate strips, so the warm-up reaches the same global cache.
_GATE_STRIPPED = ("UV_CACHE_DIR", "UV_TOOL_DIR", "UV_OFFLINE", "UV_NO_CACHE")

_WARM_RECIPE: str = (
    "jm5-pylint-warm: ; uv tool run --managed-python --python $(PYLINT_PYTHON) "
    "--from 'pylint==$(PYLINT_VERSION)' -- pylint --version"
)


def _warm_pylint() -> subprocess.CompletedProcess[str]:
    """Fetch the Makefile's pinned Pylint online into the gate's global cache.

    The gate runs offline and goes online only for the cache-miss wordings it
    recognises. A runner whose cache holds the registry metadata but not the
    wheel makes uv print a wording the gate does not recognise, so the probe
    would fail for a cold cache rather than for the property it tests. The
    pin and interpreter come from the Makefile, so the warm-up cannot drift
    from the command the probe runs.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The finished Make process, with output captured.
    """
    make = shutil.which("make")
    uv = shutil.which("uv")
    assert make is not None, "make must be on PATH"
    assert uv is not None, "uv must be on PATH"
    environment = {k: v for k, v in os.environ.items() if k not in _GATE_STRIPPED}
    # The gate asks uv for its cache with no configuration and exports the
    # answer, so a user-level `cache-dir` cannot send the warm-up elsewhere.
    cache = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argument list, no shell.
        [uv, "--no-config", "cache", "dir"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
        env=environment,
    )
    environment["UV_CACHE_DIR"] = cache.stdout.strip()
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argument list, no shell.
        [
            make,
            "--no-print-directory",
            "-s",
            "-C",
            str(_REPO_ROOT),
            "--eval",
            _WARM_RECIPE,
            "jm5-pylint-warm",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
        env=environment,
    )


def test_warm_up_fetches_the_pinned_release_online() -> None:
    """The warm-up must name the pinned release and never run offline."""
    assert "--offline" not in _WARM_RECIPE, (
        "the warm-up exists to fetch what the offline gate cannot find"
    )
    assert "--python $(PYLINT_PYTHON)" in _WARM_RECIPE, (
        "the warm-up must use the interpreter the tier pins"
    )
    assert "pylint==$(PYLINT_VERSION)" in _WARM_RECIPE, (
        "the warm-up must fetch the release the tier pins"
    )
    gate = (_REPO_ROOT / "scripts" / "uv_gate.py").read_text(encoding="utf-8")
    assert '[uv, "--no-config", "cache", "dir"]' in gate, (
        "the gate must still ask uv for its cache with no configuration, as the "
        "warm-up does"
    )
    assert all(f'"{name}"' in gate for name in _GATE_STRIPPED), (
        "the warm-up must strip variables the gate itself strips"
    )


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("make") is None,
    reason="the end-to-end check needs make and uv",
)
# Budget: the 60 s cache query, the 600 s warm-up and two 600 s probes, plus slack.
@pytest.mark.timeout(1900)
def test_configured_pylint_fails_on_an_unparsable_module(tmp_path: Path) -> None:
    """The configured tier must fail on a parse error and pass a clean module.

    This drives the real `$(PYLINT)` command, so it catches a disabled
    `syntax-error` wherever it is configured, not only in the file the
    contract above reads.
    """
    broken = tmp_path / "broken_module.py"
    broken.write_text("def broken(\n    return 1\n", encoding="utf-8")
    clean = tmp_path / "clean_module.py"
    clean.write_text('"""A clean module."""\n\nVALUE = 1\n', encoding="utf-8")

    warmed = _warm_pylint()
    assert warmed.returncode == 0, (
        f"the pinned Pylint must be fetchable: {warmed.stdout}{warmed.stderr}"
    )
    failed = _run_configured_pylint(broken)
    passed = _run_configured_pylint(clean)

    assert failed.returncode != 0, (
        f"a module Pylint cannot parse must fail the tier: {failed.stdout}"
    )
    assert "syntax-error" in failed.stdout, (
        f"the failure must be the parse error: {failed.stdout}{failed.stderr}"
    )
    assert passed.returncode == 0, (
        f"a clean module must pass the tier: {passed.stdout}{passed.stderr}"
    )
