"""Gate-neutral findings and validation of the consumed nose JSON report.

The consumed surface is deliberately small: the schema version, the
``summary`` counts, and each family's witness, value and locations. Anything
else in the report is ignored, so a detector that adds fields does not break
the gate, while a report that drops a consumed field fails closed.
"""

from __future__ import annotations

import dataclasses as dc
import pathlib

from df12_python_lints import _validate
from df12_python_lints._errors import ToolConfigError

# Report schema versions the pinned detector documents for `query --format json`.
SUPPORTED_SCHEMA_VERSIONS = frozenset({8, 9})


@dc.dataclass(frozen=True, slots=True)
class Location:
    """One duplicated region reported by nose.

    Attributes
    ----------
    file : str
        Repository-relative POSIX path of the region.
    start, end : int
        Inclusive first and last source line.
    name : str | None
        Unit name when nose matched a whole function, class or method;
        ``None`` for fragment-level matches such as import blocks.
    """

    file: str
    start: int
    end: int
    name: str | None

    @property
    def label(self) -> str:
        """The ``path:start-end`` span, followed by the unit name if any."""
        span = f"{self.file}:{self.start}-{self.end}"
        return span if self.name is None else f"{span} {self.name}"


@dc.dataclass(frozen=True, slots=True)
class Finding:
    """One duplication family in gate-neutral form.

    Attributes
    ----------
    witness : str
        nose evidence kind (``exact``, ``copy-paste``, ``similar``, ...).
    value : float
        nose refactoring value; reported and used for ordering.
    locations : tuple[Location, ...]
        Every duplicated region in the family, in report order.
    """

    witness: str
    value: float
    locations: tuple[Location, ...]

    @property
    def label(self) -> str:
        """The ``path:lines ~ path:lines`` summary of the family."""
        return " ~ ".join(location.label for location in self.locations)


@dc.dataclass(frozen=True, slots=True)
class DetectorReport:
    """A normalized detector report.

    Attributes
    ----------
    findings : tuple[Finding, ...]
        Families in descending value, then source order.
    total : int
        Families the detector found before applying its report budget.
    shown : int
        Families the detector actually returned.
    """

    findings: tuple[Finding, ...]
    total: int
    shown: int

    @property
    def is_saturated(self) -> bool:
        """Whether the report budget hid families from enforcement."""
        return self.shown < self.total


def normalize_report(report: object) -> DetectorReport:
    """Validate one decoded ``nose query --format json`` report.

    Raises
    ------
    ToolConfigError
        If the report does not match the consumed schema.
    """
    table = _validate.require_table(report, context="nose report")
    _require_schema_version(table.get("schema_version"))
    total, shown = _summary_counts(table.get("summary"))
    findings = _findings(table.get("families"), shown=shown)
    return DetectorReport(findings, total=total, shown=shown)


def _require_schema_version(version: object) -> None:
    """Fail closed on a report schema this gate was not written against."""
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        msg = f"nose report schema_version {version!r} is not supported"
        raise ToolConfigError(msg)


def _summary_counts(raw: object) -> tuple[int, int]:
    """Return ``(families found, families shown)`` from the report summary."""
    summary = _validate.require_table(raw, context="nose report summary")
    total = _validate.require_integer(
        summary.get("families"), context="nose report summary.families", minimum=0
    )
    shown = _validate.require_integer(
        summary.get("shown"), context="nose report summary.shown", minimum=0
    )
    return total, shown


def _findings(raw: object, *, shown: int) -> tuple[Finding, ...]:
    """Validate every family and order them by value, then location."""
    if not _validate.is_sequence(raw):
        msg = "nose report families must be an array"
        raise ToolConfigError(msg)
    findings = [
        _finding(family, context=f"nose report families[{index}]")
        for index, family in enumerate(raw)
    ]
    if len(findings) != shown:
        msg = f"nose report lists {len(findings)} families but summary.shown is {shown}"
        raise ToolConfigError(msg)
    findings.sort(key=lambda finding: (-finding.value, finding.label))
    return tuple(findings)


def _finding(raw: object, *, context: str) -> Finding:
    """Validate one nose family payload."""
    family = _validate.require_table(raw, context=context)
    value = family.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        msg = f"{context}.value must be a number"
        raise ToolConfigError(msg)
    return Finding(
        witness=_validate.require_string(
            family.get("witness"), context=f"{context}.witness"
        ),
        value=float(value),
        locations=_locations(family.get("locations"), context=context),
    )


def _locations(value: object, *, context: str) -> tuple[Location, ...]:
    """Validate a family's member locations, preserving report order."""
    if not _validate.is_sequence(value):
        msg = f"{context}.locations must be an array"
        raise ToolConfigError(msg)
    if not value:
        msg = f"{context}.locations must not be empty"
        raise ToolConfigError(msg)
    return tuple(
        _location(location, context=f"{context}.locations[{index}]")
        for index, location in enumerate(value)
    )


def _location(raw: object, *, context: str) -> Location:
    """Validate one nose location payload."""
    location = _validate.require_table(raw, context=context)
    start = _validate.require_integer(
        location.get("start"), context=f"{context}.start", minimum=1
    )
    end = location.get("end")
    if not _validate.is_integer(end) or end < start:
        msg = f"{context}.end must not precede start"
        raise ToolConfigError(msg)
    raw_name = location.get("name")
    if raw_name is not None and not _validate.is_non_empty_string(raw_name):
        msg = f"{context}.name must be a non-empty string or null"
        raise ToolConfigError(msg)
    path = _validate.require_string(location.get("file"), context=f"{context}.file")
    return Location(
        file=pathlib.PurePath(path).as_posix(), start=start, end=end, name=raw_name
    )
