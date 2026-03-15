"""Root Cause Analysis hypothesis engine for Kubernetes support bundle forensics.

This module generates, scores, and ranks candidate root cause hypotheses
from deterministic triage findings. It clusters related symptoms, applies
pattern-matching rules, and produces a ranked list of hypotheses with
supporting evidence and suggested fixes.
"""
