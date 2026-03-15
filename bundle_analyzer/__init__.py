"""Bundle Analyzer — AI-powered Kubernetes support bundle forensics engine."""

__version__ = "0.1.0"

from bundle_analyzer.bundle import BundleExtractor, BundleIndex
from bundle_analyzer.models import (
    AnalysisResult,
    AnalystOutput,
    BundleMetadata,
    ConfigIssue,
    DeploymentIssue,
    DriftIssue,
    Evidence,
    Finding,
    Fix,
    HistoricalEvent,
    K8sEvent,
    NodeIssue,
    PodIssue,
    PredictedFailure,
    SilenceSignal,
    SimulationResult,
    TriageResult,
    UncertaintyGap,
)
from bundle_analyzer.triage import TriageEngine

__all__ = [
    "__version__",
    # Models
    "AnalysisResult",
    "AnalystOutput",
    "BundleMetadata",
    "ConfigIssue",
    "DeploymentIssue",
    "DriftIssue",
    "Evidence",
    "Finding",
    "Fix",
    "HistoricalEvent",
    "K8sEvent",
    "NodeIssue",
    "PodIssue",
    "PredictedFailure",
    "SimulationResult",
    "SilenceSignal",
    "TriageResult",
    "UncertaintyGap",
    # Bundle
    "BundleExtractor",
    "BundleIndex",
    # Triage
    "TriageEngine",
]
