"""Backward-compatibility shim — imports from the new validation package.

The DeterministicValidator class has been refactored into
``bundle_analyzer.ai.validation``. This module re-exports it so that
existing ``from bundle_analyzer.ai.deterministic_validator import
DeterministicValidator`` continues to work.
"""

from bundle_analyzer.ai.validation import DeterministicValidator

__all__ = ["DeterministicValidator"]
