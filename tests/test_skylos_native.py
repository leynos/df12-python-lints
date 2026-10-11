"""Bounded integration tests against the real pinned Skylos.

They run only where Skylos at the pinned version is installed in the running
interpreter (``pip install '.[skylos]'``; CI installs the extra). Each scenario
is a small disposable repository; the scan runs in a child interpreter exactly
as ``df12-skylos check`` runs it.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import typing as typ

import pytest
from skylos_support import PIN

from df12_python_lints._runtime import CommandResult, Streams, run_command
from df12_python_lints.skylos import backend, commands
from df12_python_lints.skylos.context import SkylosContext

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

pytestmark = pytest.mark.skipif(
    backend.installed_version() != PIN,
    reason=f"needs skylos {PIN} (install the skylos extra)",
)

_CORE = """\
def used():
    return 1


def never_called():
    return 2


def main():
    return used()
"""
_CALLBACK = """\
class Framework:
    def on_event(self):
        return 1

    def unrelated_dead(self):
        return 2


def run():
    return Framework()
"""
_USED = "def f():\n    return 1\n\n\ndef main():\n    return f()\n"
_TEST_ONLY = (
    "from pkg.core import never_called\n\n\n"
    "def test_it():\n    assert never_called() == 2\n"
)
_CROSS_ROOT_USER = "from a.lib import helper\n\n\ndef main():\n    return helper()\n"
_STRICT = "[tool.skylos.gate]\nstrict = true\n"


def _repo(
    tmp_path: pathlib.Path,
    files: cabc.Mapping[str, str],
    extra: str = "",
    roots: str = '["pkg"]',
) -> pathlib.Path:
    """Create a repository with ``files`` and the wrapper and native policy."""
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    policy = f'[project]\nname = "demo"\nversion = "0"\n\n{_STRICT}{extra}\n'
    policy += f'[tool.df12_skylos]\nroots = {roots}\npython = "3.12"\n'
    (tmp_path / "pyproject.toml").write_text(policy, encoding="utf-8")
    return tmp_path


def _check(
    repo: pathlib.Path, runner: cabc.Callable[..., CommandResult] = run_command
) -> tuple[int, str, str]:
    """Run ``check`` through the real backend; return status and streams."""
    context = SkylosContext(
        repository=repo.resolve(),
        environment=dict(os.environ),
        probe=backend.BackendProbe.detect(),
        runner=runner,
        timeout_seconds=300,
    )
    out, err = io.StringIO(), io.StringIO()
    code = commands.run_check(context, Streams(out, err))
    return code, out.getvalue(), err.getvalue()


class TestVerdicts:
    """Clean, planted, test-only and runtime-callback scenarios."""

    def test_clean_production_code_passes(self, tmp_path: pathlib.Path) -> None:
        """Code that uses everything it defines passes."""
        repo = _repo(
            tmp_path,
            {
                "pkg/__init__.py": "",
                "pkg/core.py": _USED,
            },
        )
        code, out, _ = _check(repo)
        assert code == 0, out
        assert "skylos gate passed" in out

    def test_planted_unused_function_blocks(self, tmp_path: pathlib.Path) -> None:
        """An unused production function is a blocking finding."""
        repo = _repo(tmp_path, {"pkg/__init__.py": "", "pkg/core.py": _CORE})
        code, out, _ = _check(repo)
        assert code == 1
        assert "never_called" in out

    def test_a_test_only_reference_does_not_rescue_production_code(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Tests live outside the production roots, so they cannot save dead code."""
        files = {
            "pkg/__init__.py": "",
            "pkg/core.py": _CORE,
            "tests/test_core.py": _TEST_ONLY,
        }
        code, out, _ = _check(_repo(tmp_path, files))
        assert code == 1, "the test reference must not rescue the unused function"
        assert "never_called" in out

    def test_documented_whitelist_excuses_only_the_named_symbol(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A documented exception passes that symbol and still fails its neighbours."""
        extra = (
            "[tool.skylos.whitelist.documented]\n"
            'never_called = "Called by the framework."\n'
        )
        files = {
            "pkg/__init__.py": "",
            "pkg/core.py": _CORE + "\n\ndef other_dead():\n    return 3\n",
        }
        code, out, _ = _check(_repo(tmp_path, files, extra))
        assert code == 1
        assert "other_dead" in out
        assert "never_called" not in out

    def test_runtime_entry_point_is_narrow(self, tmp_path: pathlib.Path) -> None:
        """A callback exemption spares the callback but not an unused neighbour."""
        extra = (
            '[[tool.skylos.dead_code.entrypoints]]\ntype = "method"\n'
            'full_name = ["pkg.core.Framework.on_event"]\n'
            'reason = "The framework dispatches it."\n'
        )
        files = {"pkg/__init__.py": "", "pkg/core.py": _CALLBACK}
        code, out, _ = _check(_repo(tmp_path, files, extra))
        assert code == 1
        assert "unrelated_dead" in out
        assert "on_event" not in out

    def test_roots_are_scanned_together_so_cross_root_references_count(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A symbol used only from another root is not reported."""
        files = {
            "a/__init__.py": "",
            "a/lib.py": "def helper():\n    return 1\n",
            "b/__init__.py": "",
            "b/app.py": _CROSS_ROOT_USER,
        }
        code, out, _ = _check(_repo(tmp_path, files, roots='["a", "b"]'))
        assert code == 0, out


class TestFailuresNeverPass:
    """Missing, empty and unreadable-source scans cannot be clean."""

    def test_empty_root_is_not_a_clean_scan(self, tmp_path: pathlib.Path) -> None:
        """Skylos logs and exits zero; the command must still fail."""
        (tmp_path / "pkg").mkdir()
        code, _, err = _check(_repo(tmp_path, {}))
        assert code == 2, err
        assert "no Python files" in err

    def test_parse_failure_is_a_failed_analysis(self, tmp_path: pathlib.Path) -> None:
        """Source that cannot be parsed is never reported as clean."""
        repo = _repo(tmp_path, {"pkg/__init__.py": "", "pkg/bad.py": "def f(:\n"})
        code, out, err = _check(repo)
        assert code == 2, out + err
        assert "ANALYSIS-INCOMPLETE" in out

    def test_missing_root_is_rejected_before_the_scan(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A root that does not exist is a configuration error."""
        code, _, err = _check(
            _repo(tmp_path, {"pkg/__init__.py": ""}, roots='["nope"]')
        )
        assert code == 2
        assert "does not exist" in err

    def test_lax_gate_is_rejected_even_though_skylos_would_exit_zero(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Without ``strict = true`` native Skylos passes findings; this refuses."""
        repo = _repo(tmp_path, {"pkg/__init__.py": "", "pkg/core.py": _CORE})
        text = (
            (repo / "pyproject.toml")
            .read_text(encoding="utf-8")
            .replace("strict = true", "strict = false")
        )
        (repo / "pyproject.toml").write_text(text, encoding="utf-8")
        code, _, err = _check(repo)
        assert code == 2
        assert "strict must be true" in err

    def test_timeout_is_reported(self, tmp_path: pathlib.Path) -> None:
        """A scan that exceeds its bound is an error, not a pass."""
        repo = _repo(tmp_path, {"pkg/__init__.py": "", "pkg/core.py": _CORE})
        context = SkylosContext(
            repository=repo.resolve(),
            environment={},
            probe=backend.BackendProbe.detect(),
            timeout_seconds=0,
        )
        err = io.StringIO()
        code = commands.run_check(context, Streams(io.StringIO(), err))
        assert code == 2
        assert "timed out" in err.getvalue() or "cannot run" in err.getvalue()


@pytest.mark.skipif(
    shutil.which("unshare") is None, reason="needs unshare to drop the network"
)
def test_the_scan_needs_no_network(tmp_path: pathlib.Path) -> None:
    """The same verdict is reached in a network namespace with no interfaces."""
    repo = _repo(tmp_path, {"pkg/__init__.py": "", "pkg/core.py": _CORE})

    def offline(
        command: cabc.Sequence[str],
        cwd: pathlib.Path,
        environment: cabc.Mapping[str, str],
        timeout: int,
    ) -> CommandResult:
        """Run the scan inside an empty network namespace."""
        return run_command(["unshare", "-rn", *command], cwd, environment, timeout)

    code, out, err = _check(repo, offline)
    if "unshare:" in err and "Operation not permitted" in err:
        pytest.skip("user namespaces are not permitted here")
    assert code == 1, out + err
    assert "never_called" in out


def test_the_running_interpreter_is_the_scan_interpreter() -> None:
    """The child runs under ``sys.executable``, so the interpreter check is honest."""
    command = backend.build_command(
        sys.executable,
        __import__("pathlib").Path("/p"),
        __import__(
            "df12_python_lints.skylos.settings", fromlist=["ScanSettings"]
        ).ScanSettings(("a",), (3, 12)),
    )
    assert command[0] == sys.executable
