"""Pydantic v2 data models for all Bundle Analyzer data types.

These are the core data contracts used across the entire application:
triage findings, AI analysis results, temporal archaeology, predictions,
simulation, and the final analysis output.

Every other module imports from here -- this is the shared contract.
"""

from bundle_analyzer.models.ai_output import (
    AnalystOutput,
    Evidence,
    Finding,
    Fix,
    HistoricalEvent,
    PredictedFailure,
    SimulationResult,
    UncertaintyGap,
)
from bundle_analyzer.models.analysis import AnalysisResult
from bundle_analyzer.models.bundle import BundleMetadata
from bundle_analyzer.models.causal import CausalChain, CausalStep, LogDiagnosis
from bundle_analyzer.models.evaluation import (
    CorrelatedSignal,
    DependencyLink,
    EvaluationResult,
    EvaluationVerdict,
    MissedFailurePoint,
)
from bundle_analyzer.models.log_intelligence import (
    ContainerTimeline,
    CrashLoopContext,
    CrossContainerCorrelation,
    ErrorRateBucket,
    LogIntelligence,
    LogWindow,
    PatternFrequency,
    PodLogIntelligence,
    StackTraceGroup,
    TimelineEntry,
)
from bundle_analyzer.models.triage import (
    ConfigIssue,
    DeploymentIssue,
    DNSIssue,
    DriftIssue,
    EventEscalation,
    IngressIssue,
    K8sEvent,
    NetworkPolicyIssue,
    NodeIssue,
    PodIssue,
    ProbeIssue,
    QuotaIssue,
    RBACIssue,
    ResourceIssue,
    SchedulingIssue,
    SilenceSignal,
    StorageIssue,
    TLSIssue,
)
from bundle_analyzer.models.troubleshoot import (
    CoverageGap,
    ExternalAnalyzerIssue,
    PreflightCheckResult,
    PreflightReport,
    TriageResult,
    TroubleshootAnalysis,
    TroubleshootAnalyzerResult,
)

__all__ = [
    # Bundle
    "BundleMetadata",
    # Triage
    "PodIssue",
    "NodeIssue",
    "DeploymentIssue",
    "ConfigIssue",
    "DriftIssue",
    "SilenceSignal",
    "K8sEvent",
    "ProbeIssue",
    "ResourceIssue",
    "IngressIssue",
    "StorageIssue",
    "RBACIssue",
    "QuotaIssue",
    "NetworkPolicyIssue",
    "DNSIssue",
    "TLSIssue",
    "SchedulingIssue",
    "EventEscalation",
    # Log intelligence
    "LogWindow",
    "PatternFrequency",
    "StackTraceGroup",
    "TimelineEntry",
    "ContainerTimeline",
    "CrossContainerCorrelation",
    "ErrorRateBucket",
    "LogIntelligence",
    "PodLogIntelligence",
    "CrashLoopContext",
    # Troubleshoot
    "TroubleshootAnalyzerResult",
    "TroubleshootAnalysis",
    "PreflightCheckResult",
    "PreflightReport",
    "ExternalAnalyzerIssue",
    "CoverageGap",
    "TriageResult",
    # AI output
    "Evidence",
    "Fix",
    "Finding",
    "HistoricalEvent",
    "PredictedFailure",
    "UncertaintyGap",
    "SimulationResult",
    "AnalystOutput",
    # Causal
    "CausalStep",
    "CausalChain",
    "LogDiagnosis",
    # Evaluation
    "DependencyLink",
    "CorrelatedSignal",
    "EvaluationVerdict",
    "MissedFailurePoint",
    "EvaluationResult",
    # Analysis
    "AnalysisResult",
]
