"""ambrleaks: scan syrupy ``.ambr`` snapshots for unredacted values.

The scanner detects hex strings, UUIDs, email addresses, E.164 phone
numbers, URLs, and absolute file paths that should have been redacted
with a syrupy matcher before the snapshot was recorded. It is exposed as
the ``ambrleaks`` console script.

Examples
--------
Install and run as a standalone tool::

    uv tool install df12-python-lints
    ambrleaks tests
"""

from __future__ import annotations

from .cli import main
from .rules import DEFAULT_RULES, Rule
from .scanner import Finding, scan_file, scan_text, shannon_entropy

__all__ = [
    "DEFAULT_RULES",
    "Finding",
    "Rule",
    "main",
    "scan_file",
    "scan_text",
    "shannon_entropy",
]
