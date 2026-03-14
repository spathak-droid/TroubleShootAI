"""Change correlation package -- answers 'What changed right before things broke?'

Correlates timestamps of resource modifications with failure onset to
identify recent changes that may have triggered cluster failures.
"""

from bundle_analyzer.triage.change_correlation.correlator import ChangeCorrelator
from bundle_analyzer.triage.change_correlation.models import (
    ChangeCorrelation,
    ChangeEvent,
    ChangeReport,
)

__all__ = [
    "ChangeCorrelator",
    "ChangeEvent",
    "ChangeCorrelation",
    "ChangeReport",
]
