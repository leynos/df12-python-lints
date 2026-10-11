"""Dead-code gate over the pinned native Skylos release.

The public entry point is the ``df12-skylos`` console script
(:func:`df12_python_lints.skylos.cli.main`). Skylos stays the analysis and
gating authority; this package owns reliable invocation, configuration
validation and safe authoring of documented exceptions. It needs the
``skylos`` extra, is never imported by the Pylint plugin or ``ambrleaks``,
and imports Skylos itself only inside the scan subprocess.
"""
