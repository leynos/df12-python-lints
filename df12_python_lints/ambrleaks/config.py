"""Configuration model and parsing for the ambrleaks scanner.

The configuration is a pure data structure (:class:`Config`) with a pure
parser (:func:`parse_config`) behind a thin filesystem boundary
(:func:`read_config`), so parsing can be exercised against literal TOML
without touching the filesystem.
"""

from __future__ import annotations

import tomllib
import typing as typ

from .rules import DEFAULT_RULES, Rule

if typ.TYPE_CHECKING:
    import pathlib


class ConfigError(ValueError):
    """Raised when a configuration file is structurally invalid."""


class Config(typ.NamedTuple):
    """Loaded configuration for a scan run.

    Examples
    --------
    ``default_config()`` gives the defaults: shipped rule states and
    empty allowlists.
    """

    rule_states: tuple[tuple[str, bool], ...]
    allow_values: tuple[str, ...]
    allow_tests: tuple[str, ...]
    allow_paths: tuple[str, ...]


def default_config() -> Config:
    """Return the configuration used when no file is present.

    Examples
    --------
    ``default_config().allow_values`` is empty.
    """
    return Config(rule_states=(), allow_values=(), allow_tests=(), allow_paths=())


def _validate_rules(rules: object) -> None:
    """Ensure ``[rules]`` is a table of tables with boolean ``enabled``."""
    if not isinstance(rules, dict):
        message = "[rules] must be a table"
        raise ConfigError(message)
    for rule_id, entry in rules.items():
        if not isinstance(entry, dict):
            message = f"[rules.{rule_id}] must be a table"
            raise ConfigError(message)
        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            message = f"[rules.{rule_id}] enabled must be a boolean"
            raise ConfigError(message)


def _validate_string_list(value: object, field: str) -> None:
    """Ensure *value* is a list containing only strings."""
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return
    message = f"[allowlist] {field} must be a list of strings"
    raise ConfigError(message)


def _validate_allowlist(allowlist: object) -> None:
    """Ensure ``[allowlist]`` is a table of recognised string lists."""
    if not isinstance(allowlist, dict):
        message = "[allowlist] must be a table"
        raise ConfigError(message)
    for field in ("values", "tests", "paths"):
        _validate_string_list(allowlist.get(field, []), field)


def parse_config(text: str) -> Config:
    r"""Parse *text* as an ``ambrleaks`` TOML configuration.

    This is the pure configuration core: it decodes and structurally
    validates *text* without any filesystem access, so callers can test
    it against literal TOML. :func:`read_config` is the filesystem
    boundary that supplies *text* from a file.

    Raises
    ------
    ConfigError
        If the configuration is structurally invalid.
    tomllib.TOMLDecodeError
        If *text* is not valid TOML.

    Examples
    --------
    ``parse_config("[rules.snapshot-phone]\\nenabled = true\\n")``
    switches the phone rule on.
    """
    data = tomllib.loads(text)
    rules = data.get("rules", {})
    allowlist = data.get("allowlist", {})
    _validate_rules(rules)
    _validate_allowlist(allowlist)
    return Config(
        rule_states=tuple(
            (rule_id, bool(entry.get("enabled", True)))
            for rule_id, entry in rules.items()
        ),
        allow_values=tuple(allowlist.get("values", ())),
        allow_tests=tuple(allowlist.get("tests", ())),
        allow_paths=tuple(allowlist.get("paths", ())),
    )


def read_config(path: pathlib.Path | None) -> Config:
    """Read *path* as TOML configuration, or defaults when ``None``.

    Thin filesystem boundary over :func:`parse_config`: it reads *path*
    as UTF-8 and delegates decoding and validation. Read and decode
    failures propagate to the caller; the CLI reports them at its
    boundary.

    Raises
    ------
    ConfigError
        If the configuration is structurally invalid.
    OSError
        If the file cannot be read.
    UnicodeDecodeError
        If the file is not valid UTF-8.
    tomllib.TOMLDecodeError
        If the file is not valid TOML.

    Examples
    --------
    Given an ``ambrleaks.toml`` containing ``[rules.snapshot-phone]``
    with ``enabled = true``, ``read_config(path)`` switches the phone
    rule on.
    """
    if path is None:
        return default_config()
    return parse_config(path.read_text(encoding="utf-8"))


def select_rules(config: Config) -> tuple[Rule, ...]:
    """Return the shipped rules filtered by *config* overrides.

    Examples
    --------
    With no overrides, every rule enabled by default is returned and
    the opt-in phone rule is not.
    """
    states = dict(config.rule_states)
    return tuple(
        rule
        for rule in DEFAULT_RULES
        if states.get(rule.rule_id, rule.enabled_by_default)
    )
