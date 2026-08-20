# Migrate to version 0.3.0

Version 0.3.0 expands suppression-comment checking to recognize the valid Ruff
and Flake8 forms accepted by the project. Suppression directives must record a
reason, while a Ruff range terminator remains neutral.

## Explain valid suppression directives

Review existing suppression comments after upgrading. The checker reports an
unexplained valid directive for `ruff: ignore[...]`, standalone
`ruff: file-ignore[...]`, standalone `ruff: disable[...]`, and standalone
`ruff: noqa` or `flake8: noqa`, in addition to the other lint and type-check
suppressions already covered by C9106 and C9107.

An explanation can be non-directive prose in the same comment segment, prose
after a second `#`, or a standalone prose comment immediately above the
directive:

```python
value = eval(text)  # ruff: ignore[S307]  # input is a vetted config literal

# Generated URLs cannot be wrapped.
# ruff: file-ignore [E501,]

# ruff: disable[F841,]  # generated fixture intentionally binds this name

# ruff: noqa: F401  # generated package exports imported names

# flake8: noqa: F401  # generated module exports imported names
```

A pragma on the preceding line is not an explanation. The prose comment above
must explain the following directive; another pragma, including a Ruff range
directive, does not.

## Preserve Ruff syntax constraints

Ruff keywords are case-sensitive. Bare `noqa` is the exception: it is
case-insensitive and may follow code on the same line. The file-level
`ruff: noqa` and `flake8: noqa` aliases are case-sensitive and must be
standalone comments. Among bracketed Ruff directives, only `ruff: ignore[...]`
may follow code; `ruff: file-ignore[...]`, `ruff: disable[...]`, and
`ruff: enable[...]` must be standalone comments.

Whitespace before the selector bracket is valid, as are spaces around comma
separators and a trailing comma. Selectors may be rule codes or preview rule
names. These forms are therefore equivalent for suppression detection:

```python
value = eval(text)  # ruff: ignore[S307,]
value = eval(text)  # ruff: ignore [S307,]

# ruff: file-ignore [F401, ARG001,]
# ruff: disable[E741, F841,]
```

## Keep `ruff: enable[...]` neutral

`ruff: enable[...]` ends a suppression range; it does not suppress a
diagnostic. It needs no explanation and cannot explain a later suppression:

```python
# ruff: enable [E501,]
value = 1  # ruff: ignore [F841]  # retained for generated fixture parity
```

The `enable` directive itself is not reported as C9106, and trailing prose on
that directive does not satisfy the explanation requirement for the next
suppression.

After updating existing comments, run the normal lint targets and resolve any
new C9106 or C9107 diagnostics. Keep explanations close to the directive so the
compatibility reason remains reviewable when the suppression is revisited.
