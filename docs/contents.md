# Documentation contents

[Documentation contents](contents.md) is the index for df12-python-lints's
documentation set.

## Project guides

- [User guide](users-guide.md) explains how to use the generated project and
  its public build and test commands.
- [Developer guide](developers-guide.md) explains the plugin architecture and
  contributor workflow, and points maintainers to script automation standards.
- [Documentation style guide](documentation-style-guide.md) defines the
  spelling, structure, Markdown, Architecture Decision Record (ADR), Request
  for Comments (RFC), and roadmap conventions used by this documentation set.
- [Version 0.2.0 migration guide](migration-0.2.0.md) explains the new
  dataclass-slots rule, the reassigned message identifiers, and the required
  pylint configuration changes.
- [Version 0.4.0 migration guide](migration-0.4.0.md) lists the two new console
  commands, the optional extras and the behaviour to know about.
- [Version 0.3.0 migration guide](migration-0.3.0.md) explains the expanded
  Ruff suppression grammar, explanation requirements, and neutral range
  terminators.
- [Duplication gate migration guide](duplication-gate-migration.md) explains
  how to move a vendored nose gate onto the installed `df12-duplication`
  command, with the command mapping and a deletion checklist.
- [ADR 002](adrs/adr-0002-df12-duplication-command.md) records the boundaries,
  shared primitives, locking, installer verification and Python 3.12 decisions
  of the `df12-duplication` command.
- [ADR 003](adrs/adr-0003-df12-skylos-command.md) records the adapter,
  isolation, configuration split, pin and authoring decisions of the
  `df12-skylos` command.
- [Skylos gate migration guide](skylos-gate-migration.md) explains how to move
  a Skylos Makefile target and its copied contract suites onto the installed
  `df12-skylos` command, with a deletion checklist.
- [ADR 001](adrs/adr-0001-conservative-dataclass-layout-analysis.md) records the
  conservative, cached layout analysis and supported Pylint range for R9111.

## Proposed refactoring lints

- [Shared refactoring lint contract](refactoring-lint-contract.md) defines
  evidence, diagnostic ownership, opt-in activation, and verification for the
  Python 3.12 refactoring proposals.
- [RFC 0003: Local intent simplifications](rfcs/rfc-0003-local-intent-simplifications.md)
  proposes direct min/max defaults, sequence indexing, string tests, length
  reductions, and single-entry dictionary updates.
- [RFC 0004: Small structural cleanups](rfcs/rfc-0004-small-structural-cleanups.md)
  proposes compatible try flattening, identical handlers, empty-branch cleanup,
  and fresh collection initialization.
- [RFC 0005: Residual idiom refactorings](rfcs/rfc-0005-residual-idiom-refactorings.md)
  covers generator, search, joining, length-test, and fallback forms beyond
  existing upstream matchers.
- [RFC 0006: Branch factoring](rfcs/rfc-0006-branch-factoring.md) proposes
  common branch statements, stable repeated conditions, and terminal guards.
- [RFC 0007: Paragraph-guided method extraction](rfcs/rfc-0007-paragraph-guided-method-extraction.md)
  adapts Whitaker's paragraph model to conservative Python extraction advice.
- [RFC 0008: Dictionary construction and filtering](rfcs/rfc-0008-dictionary-construction-and-filtering.md)
  proposes dictionary unions and isolated filtered reconstruction with alias
  and exception checks.
- [RFC 0009: Variable placement](rfcs/rfc-0009-variable-placement.md) proposes
  assignment movement, inlining, value reuse, and repeated-read while
  conditions, while delegating assignment-before-if to upstream Pylint.
- [RFC 0010: Numeric and logical transformations](rfcs/rfc-0010-numeric-and-logical-transformations.md)
  proposes restricted integer and any/all transformations with explicit
  numerical and exception semantics.
- [RFC 0011: De Morgan transformations](rfcs/rfc-0011-de-morgan-transformations.md)
  proposes Boolean-negation normalization that preserves evaluation order and
  truth-test behaviour.

## Engineering practice

- [Complexity antipatterns and refactoring strategies](complexity-antipatterns-and-refactoring-strategies.md)
  explains cognitive complexity, the bumpy-road antipattern, and refactoring
  approaches for maintainable code.
- [Local validation of GitHub Actions with act and pytest](local-validation-of-github-actions-with-act-and-pytest.md)
  explains how to validate workflow behaviour locally before relying on remote
  Continuous Integration (CI) runs.
- [Detector benchmarks](developers-guide.md#detector-benchmarks) describes the
  development-only corpora and retained evidence behind the Skylos and nose
  choices, moved here from the Episodic repository.
- [Scripting standards](scripting-standards.md) explains the preferred Python
  scripting stack, command execution patterns, and test expectations for helper
  scripts.
