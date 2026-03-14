"""CLI package for Bundle Analyzer.

Re-exports the Typer ``app`` so that ``bundle_analyzer.cli:app`` continues
to work as the entry point defined in pyproject.toml.
"""

from bundle_analyzer.cli.app import app

__all__ = ["app"]
