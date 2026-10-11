"""Builders and doubles shared by the duplication command tests.

Nothing here touches the developer's real manifest or environment: every
repository is a disposable ``tmp_path`` tree and the detector is replaced by
a recording :class:`FakeRunner` unless a test says otherwise.
"""

from __future__ import annotations

import dataclasses as dc
import json
import pathlib
import textwrap
import typing as typ

from df12_python_lints.duplication.context import CommandResult

if typ.TYPE_CHECKING:
    import collections.abc as cabc

PINNED = "0.20.0"
NOSE_TABLE = f"""\
[tool.nose]
version = "{PINNED}"
roots = ["src"]
mode = "syntax,semantic,near"
min-size = 24
surface = "all"
top = 30
"""


def nose_table(
    *,
    roots: str = '["src"]',
    mode: str = "syntax",
    extra: str = "",
    version: str = PINNED,
) -> str:
    """Render a ``[tool.nose]`` table with the given roots, mode and extra keys."""
    return (
        f'[tool.nose]\nversion = "{version}"\nroots = {roots}\nmode = "{mode}"\n'
        f"min-size = 24\n{extra}"
    )


def make_repository(
    root: pathlib.Path, *, extra: str = "", nose_table: str = NOSE_TABLE
) -> pathlib.Path:
    """Create a disposable repository with a ``pyproject.toml`` and a root.

    Returns
    -------
    pathlib.Path
        The repository directory.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    body = f'[project]\nname = "demo"\nversion = "0"\n\n{nose_table}\n{extra}'
    (root / "pyproject.toml").write_text(body, encoding="utf-8")
    return root


def location(
    file: str, start: int = 1, end: int = 20, name: str | None = None
) -> dict[str, object]:
    """Build one location payload as nose emits it."""
    return {"file": file, "start": start, "end": end, "name": name}


def family(
    *locations: dict[str, object], witness: str = "copy-paste", value: float = 22.1
) -> dict[str, object]:
    """Build one family payload."""
    return {"witness": witness, "value": value, "locations": list(locations)}


def report(
    *families: dict[str, object], total: int | None = None, schema: int = 9
) -> str:
    """Render a ``nose query --format json`` report."""
    shown = len(families)
    summary = {"families": shown if total is None else total, "shown": shown}
    return json.dumps({
        "schema_version": schema,
        "summary": summary,
        "families": list(families),
    })


@dc.dataclass
class FakeRunner:
    """A recording stand-in for the subprocess boundary.

    Attributes
    ----------
    query_stdout, query_stderr : str
        Output of the ``query`` invocation.
    query_status : int
        Exit status of the ``query`` invocation.
    version : str
        What ``--version`` prints.
    calls : list[tuple[list[str], pathlib.Path]]
        Every argument vector and working directory seen.
    """

    query_stdout: str = ""
    query_stderr: str = ""
    query_status: int = 0
    version: str = f"nose {PINNED}"
    version_status: int = 0
    calls: list[tuple[list[str], pathlib.Path]] = dc.field(default_factory=list)
    neutral_files: list[tuple[str, str]] = dc.field(default_factory=list)

    def __call__(
        self,
        command: cabc.Sequence[str],
        cwd: pathlib.Path,
        environment: cabc.Mapping[str, str],
        timeout: int,
    ) -> CommandResult:
        """Record the call and answer like the detector would."""
        del environment, timeout
        argv = list(command)
        self.calls.append((argv, cwd))
        if argv[1:] == ["--version"]:
            return CommandResult(self.version_status, f"{self.version}\n", "")
        self._capture_neutral_files(argv)
        return CommandResult(self.query_status, self.query_stdout, self.query_stderr)

    def _capture_neutral_files(self, argv: list[str]) -> None:
        """Remember the contents of the native-config files while they exist."""
        for flag in ("--config", "--ignore-file"):
            if flag in argv:
                path = pathlib.Path(argv[argv.index(flag) + 1])
                self.neutral_files.append((flag, path.read_text(encoding="utf-8")))

    @property
    def query_argv(self) -> list[str]:
        """The argument vector of the ``query`` call."""
        return next(argv for argv, _ in self.calls if "query" in argv)


def dedent(text: str) -> str:
    """Dedent a TOML snippet and ensure a final newline."""
    return textwrap.dedent(text).lstrip("\n")


@dc.dataclass(frozen=True, slots=True)
class Script:
    """What a scripted detector prints and how it exits.

    Attributes
    ----------
    stdout, stderr : str
        Output of any non-``--version`` invocation.
    status : int
        Exit status of that invocation.
    version : str
        What ``--version`` prints.
    """

    stdout: str
    stderr: str = ""
    status: int = 0
    version: str = f"nose {PINNED}"


def write_fake_nose(path: pathlib.Path, script: Script) -> pathlib.Path:
    """Write an executable stand-in for the detector binary.

    ``--version`` prints ``script.version``; any other invocation prints the
    scripted output and exits with the scripted status.
    """
    body = textwrap.dedent(
        f"""\
        #!/bin/sh
        if [ "$1" = "--version" ]; then printf '%s\\n' '{script.version}'; exit 0; fi
        cat <<'__NOSE_STDERR__' >&2
        {script.stderr}
        __NOSE_STDERR__
        cat <<'__NOSE_STDOUT__'
        {script.stdout}
        __NOSE_STDOUT__
        exit {script.status}
        """
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path
