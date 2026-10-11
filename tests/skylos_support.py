"""Builders and doubles for the Skylos command tests.

Every repository is a disposable ``tmp_path`` tree. The backend is replaced by
a recording runner and an injected probe unless a test is explicitly a native
one.
"""

from __future__ import annotations

import dataclasses as dc
import typing as typ

from df12_python_lints._runtime import CommandResult
from df12_python_lints.skylos.backend import BackendProbe
from df12_python_lints.skylos.context import SkylosContext

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

PIN = "4.33.2"
POLICY = """\
[tool.skylos.gate]
strict = true

[tool.df12_skylos]
roots = ["pkg"]
python = "3.12"
"""


def make_repository(
    root: pathlib.Path,
    *,
    policy: str = POLICY,
    files: cabc.Mapping[str, str] | None = None,
) -> pathlib.Path:
    """Create a disposable repository holding ``policy`` and a ``pkg`` root."""
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    for name, text in (files or {}).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    body = f'[project]\nname = "demo"\nversion = "0"\n\n{policy}'
    (root / "pyproject.toml").write_text(body, encoding="utf-8")
    return root


def probe(
    *,
    interpreter: tuple[int, int] = (3, 14),
    installed: str | None = PIN,
    pinned: str = PIN,
    executable: str = "python-under-test",
) -> BackendProbe:
    """Build a backend probe with scripted facts."""
    return BackendProbe(
        executable=executable,
        interpreter=interpreter,
        pinned=lambda: pinned,
        installed=lambda: installed,
    )


@dc.dataclass
class FakeRunner:
    """A recording stand-in for the scan subprocess."""

    stdout: str = ""
    stderr: str = ""
    status: int = 0
    calls: list[tuple[list[str], pathlib.Path]] = dc.field(default_factory=list)

    def __call__(
        self,
        command: cabc.Sequence[str],
        cwd: pathlib.Path,
        environment: cabc.Mapping[str, str],
        timeout: int,
    ) -> CommandResult:
        """Record the call and answer like the scan would."""
        del environment, timeout
        self.calls.append((list(command), cwd))
        return CommandResult(self.status, self.stdout, self.stderr)


def context_for(
    repo: pathlib.Path,
    runner: FakeRunner | None = None,
    *,
    backend_probe: BackendProbe | None = None,
) -> SkylosContext:
    """Build a context for ``repo`` with a scripted probe and runner."""
    return SkylosContext(
        repository=repo.resolve(),
        environment={},
        probe=backend_probe or probe(),
        runner=runner or FakeRunner(),
    )
