"""Detection rules for the ambrleaks snapshot scanner.

Each rule pairs a regular expression with an optional Shannon-entropy
floor and an allowlist of value patterns, following the model used by
secret scanners such as gitleaks: a strict pattern, a noise gate, and an
escape hatch for known-benign values.

Examples
--------
Iterate the shipped rules::

    for rule in DEFAULT_RULES:
        print(rule.rule_id)
"""

from __future__ import annotations

import re
import typing as typ


class Rule(typ.NamedTuple):
    """A single detection rule for snapshot values.

    Examples
    --------
    ``Rule(rule_id="snapshot-hex", description="...", pattern=...)``
    with the remaining fields defaulted.
    """

    rule_id: str
    description: str
    pattern: re.Pattern[str]
    min_entropy: float = 0.0
    enabled_by_default: bool = True
    allow: tuple[re.Pattern[str], ...] = ()


_EMAIL_ALLOW = (
    re.compile(r"@(?:[\w.-]+\.)?example\.(?:com|org|net)\b"),
    re.compile(r"@(?:[\w.-]+\.)?(?:test|invalid|localhost)\b"),
)

_URL_ALLOW = (
    re.compile(r"^https?://(?:www\.)?example\.(?:com|org|net)(?:[/:]|$)"),
    re.compile(r"^https?://(?:localhost|127\.0\.0\.1)(?:[/:]|$)"),
    re.compile(r"^https?://(?:www\.)?w3\.org/"),
    re.compile(r"^https?://json-schema\.org/"),
)

_PATH_ALLOW = (
    # Syrupy's documented redaction placeholder for temporary paths.
    re.compile(r"<tmp-file-path>"),
)

DEFAULT_RULES: typ.Final[tuple[Rule, ...]] = (
    Rule(
        rule_id="snapshot-hex",
        description="Long hex string (id or hash); redact before snapshotting",
        pattern=re.compile(r"\b[0-9a-fA-F]{32,}\b"),
        min_entropy=3.0,
    ),
    Rule(
        rule_id="snapshot-uuid",
        description="UUID literal; redact before snapshotting",
        pattern=re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
            r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        ),
    ),
    Rule(
        rule_id="snapshot-email",
        description="Email address; redact before snapshotting",
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        allow=_EMAIL_ALLOW,
    ),
    Rule(
        rule_id="snapshot-phone",
        description="E.164 telephone number; redact before snapshotting",
        pattern=re.compile(r"\+[1-9]\d{7,14}\b"),
        enabled_by_default=False,
    ),
    Rule(
        rule_id="snapshot-url",
        description="URL; redact before snapshotting",
        pattern=re.compile(r"\bhttps?://[^\s\"'<>\)\]]+"),
        allow=_URL_ALLOW,
    ),
    Rule(
        rule_id="snapshot-posix-path",
        description="Absolute POSIX path; redact before snapshotting",
        pattern=re.compile(
            r"(?<![\w/])/(?:home|Users|tmp|var|opt|mnt|private|etc|usr|srv"
            r"|root|run|bin|sbin|lib|lib64|dev|proc|sys|boot|media)"
            r"/[^\s\"',\)\]]+"
        ),
        allow=_PATH_ALLOW,
    ),
    Rule(
        rule_id="snapshot-windows-path",
        description="Absolute Windows path; redact before snapshotting",
        pattern=re.compile(
            r"\b[A-Za-z]:\\[^\s\"']+"
            r"|\\\\[\w.$-]+\\[^\s\"']+"
        ),
    ),
)
