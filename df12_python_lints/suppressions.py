"""Checkers requiring an explanation on lint and type-check suppressions.

A suppression pragma silences a diagnostic; without a recorded reason the
next reader cannot tell whether it is still needed or safe to remove. An
explanation may sit in the same comment after a second ``#``, as trailing
prose in the pragma segment, or as a standalone comment on the line above.

Examples
--------
Flagged::

    value = eval(text)  # noqa: S307

Preferred::

    value = eval(text)  # noqa: S307  # input is a vetted config literal
"""

from __future__ import annotations

import re
import tokenize
import typing as typ

from pylint import checkers

if typ.TYPE_CHECKING:
    from pylint.typing import MessageDefinitionTuple

_MSGS: typ.Final[dict[str, MessageDefinitionTuple]] = {
    "C9106": (
        "Lint suppression lacks an explanation",
        "lint-suppression-without-explanation",
        (
            "Emitted when a lint suppression pragma (noqa, ruff, or "
            "pylint disable) carries no reason. Add prose after the "
            "pragma or a standalone comment on the line above so the "
            "next reader knows why the diagnostic is silenced."
        ),
    ),
    "C9107": (
        "Type-check suppression lacks an explanation",
        "typecheck-suppression-without-explanation",
        (
            "Emitted when a type-check suppression pragma (type: ignore, "
            "pyright, ty, or mypy) carries no reason. Add prose after "
            "the pragma or a standalone comment on the line above so the "
            "next reader knows why the diagnostic is silenced."
        ),
    ),
}

_LINT_DIRECTIVE: typ.Final = re.compile(
    r"\bnoqa\b|\bpylint\s*:\s*disable",
    re.IGNORECASE,
)
_RUFF_INLINE_DIRECTIVE: typ.Final = re.compile(r"\bruff\s*:\s*ignore\s*\[")
_RUFF_STANDALONE_DIRECTIVE: typ.Final = re.compile(
    r"\bruff\s*:\s*(?:file-ignore|disable)\s*\["
)
_RUFF_ENABLE_DIRECTIVE: typ.Final = re.compile(r"^\s*#\s*ruff\s*:\s*enable\s*\[")

_TYPE_DIRECTIVE: typ.Final = re.compile(
    r"\btype\s*:\s*ignore\b|\b(?:pyright|ty)\s*:\s*ignore\b|\bmypy\s*:",
    re.IGNORECASE,
)

# Inline `noqa` directives accept comma- or whitespace-separated rule codes.
# Restricting each item to Ruff's letter-plus-digit shape leaves trailing prose
# distinguishable.
_NOQA_CODE_LIST: typ.Final = (
    r"[A-Za-z]+[0-9]+"
    r"(?:(?:\s*,\s*|\s+)[A-Za-z]+[0-9]+)*"
    r"\s*,?"
)
_RUFF_RULE_LIST: typ.Final = r"[\w\-]+(?:\s*,\s*[\w\-]+)*\s*,?"
_NAME_LIST: typ.Final = r"[\w\-]+(?:\s*,\s*[\w\-]+)*"

_DIRECTIVE_ONLY_SEGMENT: typ.Final = re.compile(
    rf"""^\s*(?:
        (?:(?:ruff|flake8)\s*:\s*)? noqa
            (?:\s*:\s*{_NOQA_CODE_LIST})?
        | (?-i:ruff\s*:\s*(?:ignore|file-ignore|disable|enable)
            \s*\[\s*{_RUFF_RULE_LIST}\s*\])
        | pylint\s*:\s*disable(?:-next|-line)?\s*=\s*{_NAME_LIST}
        | type\s*:\s*ignore (?:\[[\w\s,\-]*\])?
        | (?:pyright|ty)\s*:\s*ignore (?:\[[\w\s,\-]*\])?
        | mypy\s*:\s*[\w\-]+ (?:\s*=\s*"[^"]*")?
    )\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


class _Comment(typ.NamedTuple):
    """A comment token with its position context."""

    text: str
    is_standalone: bool


def _directive_symbols(comment: _Comment) -> tuple[str, ...]:
    """Return the message symbols for pragmas present in *comment*.

    Examples
    --------
    ``"# ruff: ignore[S101]"`` maps to the lint suppression symbol; a
    plain comment maps to an empty tuple.
    """
    symbols: list[str] = []
    has_lint_directive = (
        _LINT_DIRECTIVE.search(comment.text)
        or _RUFF_INLINE_DIRECTIVE.search(comment.text)
        or (comment.is_standalone and _RUFF_STANDALONE_DIRECTIVE.search(comment.text))
    )
    if has_lint_directive:
        symbols.append("lint-suppression-without-explanation")
    if _TYPE_DIRECTIVE.search(comment.text):
        symbols.append("typecheck-suppression-without-explanation")
    return tuple(symbols)


def _has_inline_explanation(comment_text: str) -> bool:
    """Return whether *comment_text* carries prose beyond its pragmas.

    Each ``#``-separated segment is checked: a segment that is not purely
    a pragma with its codes counts as an explanation.

    Examples
    --------
    ``"# noqa: S307  # vetted input"`` has an explanation;
    ``"# noqa: S307"`` does not.
    """
    segments = comment_text.lstrip("#").split("#")
    return any(
        segment.strip() and not _DIRECTIVE_ONLY_SEGMENT.fullmatch(segment)
        for segment in segments
    )


class SuppressionCommentChecker(checkers.BaseTokenChecker):
    """Report suppression pragmas that record no reason.

    Attributes
    ----------
    name : str
        The checker identifier, ``df12-suppression-comments``.
    msgs : dict[str, MessageDefinitionTuple]
        The C9106 lint and C9107 type-check suppression messages.

    Examples
    --------
    Enable alongside the plugin and run pylint as usual::

        pylint --load-plugins=df12_python_lints my_module.py
    """

    name = "df12-suppression-comments"
    msgs = _MSGS

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        """Scan comment tokens for unexplained suppression pragmas.

        Examples
        --------
        Invoked by pylint with the token stream of each module.
        """
        comments = _collect_comments(tokens)
        for row, comment in sorted(comments.items()):
            symbols = _directive_symbols(comment)
            if not symbols or _has_inline_explanation(comment.text):
                continue
            if _has_preceding_explanation(comments, row):
                continue
            for symbol in symbols:
                self.add_message(symbol, line=row)


def _collect_comments(
    tokens: list[tokenize.TokenInfo],
) -> dict[int, _Comment]:
    """Map each comment token to its row with standalone context.

    A comment is standalone when nothing but whitespace precedes it on
    its line.

    Examples
    --------
    ``x = 1  # note`` yields a non-standalone entry for its row.
    """
    comments: dict[int, _Comment] = {}
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        is_standalone = not token.line[: token.start[1]].strip()
        comments[token.start[0]] = _Comment(token.string, is_standalone)
    return comments


def _has_preceding_explanation(comments: dict[int, _Comment], row: int) -> bool:
    """Return whether the line above *row* holds an explanatory comment.

    Only a standalone comment containing prose beyond any directives counts.

    Examples
    --------
    A pragma on line 5 preceded by ``# upstream stub is wrong`` on line 4
    is explained.
    """
    preceding = comments.get(row - 1)
    if preceding is None or not preceding.is_standalone:
        return False
    if _RUFF_ENABLE_DIRECTIVE.match(preceding.text):
        return False
    return _has_inline_explanation(preceding.text)
