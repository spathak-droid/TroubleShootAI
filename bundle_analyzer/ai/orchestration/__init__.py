"""Orchestration package — coordinates AI analysts for bundle analysis.

Public API:
    AnalysisOrchestrator: The main facade for running the full AI pipeline.
"""

from bundle_analyzer.ai.orchestration.orchestrator import AnalysisOrchestrator

__all__ = ["AnalysisOrchestrator"]
