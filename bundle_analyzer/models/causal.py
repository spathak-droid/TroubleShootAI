"""Causal chain models for symptom-to-root-cause tracing."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CausalStep(BaseModel):
    """One step in a causal chain from symptom to root cause.

    Each step represents a single observation along the reasoning path,
    grounded in a specific evidence file and excerpt from the bundle.
    """

    resource: str           # "Pod/default/my-pod"
    observation: str        # "Container exited with code 137"
    evidence_file: str      # "cluster-resources/pods/default.json"
    evidence_excerpt: str   # "exitCode: 137, reason: OOMKilled"


class CausalChain(BaseModel):
    """A traced path from symptom to root cause.

    Produced by the ChainWalker, which follows deterministic reasoning
    patterns through triage findings and raw bundle data to connect
    symptoms (e.g. CrashLoopBackOff) to their underlying causes.
    """

    id: str                          # unique identifier
    symptom: str                     # "Pod my-pod is in CrashLoopBackOff"
    symptom_resource: str            # "Pod/default/my-pod"
    steps: list[CausalStep]         # ordered chain of observations
    root_cause: str | None = None   # "Node memory pressure caused OOM" or None if ambiguous
    confidence: float = 0.0          # 0.0-1.0
    ambiguous: bool = False          # True if multiple possible root causes
    needs_ai: bool = False           # True if semantic log analysis needed
    related_resources: list[str] = Field(default_factory=list)  # other affected resources


class LogDiagnosis(BaseModel):
    """AI-generated diagnosis from reading container logs.

    Produced by the LogAnalyst for each crash-looping container.
    Contains a plain-English explanation of the failure, the root cause
    category, the key log line, and actionable fix information.
    """

    namespace: str
    pod_name: str
    container_name: str
    diagnosis: str  # plain English explanation
    root_cause_category: str  # oom, crash, config_error, etc.
    key_log_line: str = ""  # the most revealing log line
    why: str = ""  # underlying cause explanation
    fix_description: str = ""
    fix_commands: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    additional_context_needed: list[str] = Field(default_factory=list)
