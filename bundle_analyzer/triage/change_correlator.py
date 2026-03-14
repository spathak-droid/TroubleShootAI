"""Backward-compatible shim for change_correlator.

This module re-exports all public names from the
``bundle_analyzer.triage.change_correlation`` package so that existing
imports like ``from bundle_analyzer.triage.change_correlator import ChangeCorrelator``
continue to work.
"""

from bundle_analyzer.triage.change_correlation import (  # noqa: F401
    ChangeCorrelation,
    ChangeCorrelator,
    ChangeEvent,
    ChangeReport,
)

__all__ = [
    "ChangeCorrelator",
    "ChangeEvent",
    "ChangeCorrelation",
    "ChangeReport",
]
