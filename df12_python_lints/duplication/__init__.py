"""Blocking code-duplication gate over the pinned ``nose`` detector.

The public entry point is the ``df12-duplication`` console script
(:func:`df12_python_lints.duplication.cli.main`). The package needs the
``duplication`` extra (``tomlkit``, plus ``typing_extensions`` on Python
3.12) and is never imported by the Pylint plugin or ``ambrleaks``.
"""
