"""Triage finding models for all scanner types."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PodIssue(BaseModel):
    """A detected issue with a specific pod or container.

    Covers crash loops, OOM kills, image pull failures, pending pods,
    and other container-level problems discovered by the pod scanner.
    """

    namespace: str
    pod_name: str
    container_name: str | None = None
    issue_type: Literal[
        "CrashLoopBackOff",
        "OOMKilled",
        "ImagePullBackOff",
        "Pending",
        "Evicted",
        "Terminating",
        "FailedMount",
        "CreateContainerConfigError",
        "InitContainerFailed",
    ]
    restart_count: int = 0
    exit_code: int | None = None
    message: str = ""
    log_path: str | None = None
    previous_log_path: str | None = None
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class NodeIssue(BaseModel):
    """A detected issue with a cluster node.

    Represents node conditions like memory pressure, disk pressure,
    or the node being not ready, along with optional resource usage metrics.
    """

    node_name: str
    condition: Literal[
        "MemoryPressure",
        "DiskPressure",
        "PIDPressure",
        "NotReady",
        "Unschedulable",
    ]
    memory_usage_pct: float | None = None
    cpu_usage_pct: float | None = None
    message: str = ""
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class DeploymentIssue(BaseModel):
    """A detected issue with a deployment's replica availability.

    Flags deployments where ready replicas do not match desired replicas,
    or where a rollout appears stuck with multiple ReplicaSets.
    """

    namespace: str
    name: str
    desired_replicas: int
    ready_replicas: int
    issue: str  # e.g. "0/3 replicas ready"
    stuck_rollout: bool = False
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class ConfigIssue(BaseModel):
    """A detected configuration reference issue.

    Covers missing ConfigMaps, Secrets, or specific keys that pods
    reference but that do not exist in the bundle.
    """

    namespace: str
    resource_type: str  # "ConfigMap" | "Secret"
    resource_name: str
    referenced_by: str  # pod/deployment name
    issue: Literal["missing", "missing_key", "wrong_namespace"]
    missing_key: str | None = None
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class DriftIssue(BaseModel):
    """A detected spec-vs-status drift in a Kubernetes resource.

    Indicates that the declared spec and the observed status have diverged,
    such as replica count mismatches or selector mismatches.
    """

    resource_type: str
    namespace: str
    name: str
    field: str
    spec_value: Any
    status_value: Any
    description: str
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class SilenceSignal(BaseModel):
    """A signal indicating missing or suspiciously absent data.

    Represents cases where expected log files or data are missing,
    which itself is a diagnostic signal (the silence tells a story).
    """

    namespace: str
    pod_name: str
    container_name: str | None = None
    signal_type: Literal[
        "LOG_FILE_MISSING",
        "EMPTY_LOG_RUNNING_POD",
        "PREVIOUS_LOG_MISSING",
        "RBAC_BLOCKED",
    ]
    severity: Literal["critical", "warning", "info"] = "warning"
    possible_causes: list[str] = Field(default_factory=list)
    note: str = ""
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class K8sEvent(BaseModel):
    """A Kubernetes event extracted from the support bundle.

    Captures both Normal and Warning events with their timestamps,
    involved objects, and occurrence counts.
    """

    namespace: str
    name: str
    reason: str
    message: str
    type: Literal["Normal", "Warning"]
    involved_object_kind: str
    involved_object_name: str
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    count: int = 1


class ProbeIssue(BaseModel):
    """A detected issue with pod health probes."""

    namespace: str
    pod_name: str
    container_name: str
    probe_type: Literal["liveness", "readiness", "startup"]
    issue: str  # "bad_path", "no_readiness_probe", "same_endpoint", "missing_startup"
    message: str
    severity: Literal["critical", "warning", "info"] = "warning"
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class ResourceIssue(BaseModel):
    """A detected resource request/limit issue."""

    namespace: str
    pod_name: str
    container_name: str
    issue: str  # "no_limits", "no_requests", "exceeds_node", "overcommitted_node"
    message: str
    resource_type: str  # "cpu", "memory"
    severity: Literal["critical", "warning", "info"] = "warning"
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class IngressIssue(BaseModel):
    """A detected ingress misconfiguration."""

    namespace: str
    ingress_name: str
    issue: str  # "missing_service", "port_mismatch", "missing_tls_secret"
    message: str
    severity: Literal["critical", "warning", "info"] = "warning"
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class StorageIssue(BaseModel):
    """A detected storage/PVC issue."""

    namespace: str
    resource_name: str
    resource_type: str  # "PVC", "PV", "StorageClass"
    issue: str  # "pending", "missing_storage_class", "released", "failed"
    message: str
    severity: Literal["critical", "warning", "info"] = "warning"
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class RBACIssue(BaseModel):
    """A detected RBAC/permissions issue."""

    namespace: str
    resource_type: str  # what couldn't be collected
    error_message: str
    severity: Literal["critical", "warning", "info"] = "warning"
    suggested_permission: str = ""  # e.g. "get pods"
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class QuotaIssue(BaseModel):
    """A detected resource quota or limit range issue."""

    namespace: str
    resource_name: str
    issue_type: Literal["quota_exceeded", "quota_near_limit", "limit_range_conflict", "no_quota"]
    resource_type: str  # "cpu", "memory", "pods", "services"
    current_usage: str = ""
    limit: str = ""
    message: str
    severity: Literal["critical", "warning", "info"] = "warning"
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class NetworkPolicyIssue(BaseModel):
    """A detected network policy misconfiguration."""

    namespace: str
    policy_name: str
    issue_type: Literal["deny_all_ingress", "deny_all_egress", "no_policies", "orphaned_policy"]
    affected_pods: list[str] = Field(default_factory=list)
    message: str
    severity: Literal["critical", "warning", "info"] = "warning"
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class EventEscalation(BaseModel):
    """A pattern of escalating events indicating an ongoing or worsening issue."""

    namespace: str
    involved_object_kind: str
    involved_object_name: str
    event_reasons: list[str]  # ordered list of event reasons
    total_count: int  # sum of all event counts
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    escalation_type: Literal["repeated", "cascading", "sustained"]
    message: str
    severity: Literal["critical", "warning", "info"] = "warning"
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class DNSIssue(BaseModel):
    """A detected DNS or CoreDNS issue."""

    namespace: str
    resource_name: str
    issue_type: Literal[
        "coredns_pod_failure",
        "dns_resolution_error",
        "missing_endpoints",
        "coredns_config_error",
    ]
    message: str
    severity: Literal["critical", "warning", "info"] = "warning"
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class TLSIssue(BaseModel):
    """A detected TLS or certificate issue."""

    namespace: str
    resource_name: str
    issue_type: Literal[
        "cert_expired",
        "bad_certificate",
        "unknown_authority",
        "missing_tls_secret",
    ]
    message: str
    severity: Literal["critical", "warning", "info"] = "warning"
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0


class SchedulingIssue(BaseModel):
    """A detected pod scheduling issue (FailedScheduling, taints, affinity)."""

    namespace: str
    pod_name: str
    issue_type: Literal[
        "insufficient_cpu",
        "insufficient_memory",
        "taint_not_tolerated",
        "node_affinity_mismatch",
        "pod_affinity_conflict",
        "node_selector_mismatch",
        "unschedulable_node",
    ]
    message: str
    severity: Literal["critical", "warning", "info"] = "warning"
    source_file: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = 1.0
