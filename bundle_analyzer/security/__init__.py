"""Security & data protection layer for Bundle Analyzer.

Provides multi-layer scrubbing of sensitive data before storage and LLM transmission.
Combines regex pattern detection, Kubernetes structural scrubbing, entropy-based
detection, and prompt injection defense.

Key exports:
    BundleScrubber: Main entry point — composes all detectors.
    SecurityPolicy: Configurable policy (standard/strict/allowlist).
    SanitizationReport: Summary of all redactions applied.
"""

from bundle_analyzer.security.models import (
    RedactionEntry,
    SanitizationReport,
    SecurityPolicy,
)
from bundle_analyzer.security.scrubber import BundleScrubber

__all__ = [
    "BundleScrubber",
    "RedactionEntry",
    "SanitizationReport",
    "SecurityPolicy",
]
