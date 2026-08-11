# Migrate to version 0.2.0

Version 0.2.0 adds a rule for closed standard-library dataclasses and
reassigns the message identifier previously allocated to
`prefer-type-statement`. Projects that configure pylint messages by identifier
must update that configuration when upgrading from version 0.1.0.

## Adopt the dataclass-slots rule

The new `prefer-slots-for-dataclass` rule uses R9111. It reports a
standard-library dataclass when the source provides neither a literal
`slots=True` argument nor a runtime `__slots__` assignment, unless the checker
finds concrete evidence that generated slots would be unsafe or ineffective.

Prefer an explicit closed layout for ordinary value objects:

```python
import dataclasses


@dataclasses.dataclass(slots=True)
class Coordinate:
    latitude: float
    longitude: float
```

Review each new R9111 diagnostic before changing the class. Generated slots
return a replacement class and can interact with inheritance, decorators,
class-cell closures, and dictionary-backed state. When compatibility requires
an unslotted class, retain it with a narrow, explained suppression:

```python
# Compatibility: consumers attach adapter state dynamically.
@dataclasses.dataclass  # pylint: disable=prefer-slots-for-dataclass
class LegacyRecord:
    value: str
```

## Update message identifiers

In version 0.1.0, R9111 identified `prefer-type-statement`. Version 0.2.0
assigns R9111 to `prefer-slots-for-dataclass` and moves
`prefer-type-statement` to R9112.

Replace R9111 with R9112 wherever a pylint `enable` or `disable` list intends
to select `prefer-type-statement`. For example:

```toml
[tool.pylint.messages_control]
enable = ["R9112"]
```

Configuration that uses the stable symbol `prefer-type-statement` needs no
change. Prefer symbols over numeric identifiers in new configuration so future
identifier changes remain explicit at the plugin boundary.

After updating the configuration, run pylint across the normal source and test
targets. Resolve any new `prefer-slots-for-dataclass` findings or add explained
local suppressions where a compatibility requirement cannot be inferred from
the source.
