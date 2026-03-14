"""Backward-compatibility shim — re-exports from the orchestration package.

All logic has moved to ``bundle_analyzer.ai.orchestration``.
Import from here continues to work for existing consumers.
"""

from bundle_analyzer.ai.orchestration import AnalysisOrchestrator

__all__ = ["AnalysisOrchestrator"]
