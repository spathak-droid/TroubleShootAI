"""Deterministic RCA rules mapping symptom patterns to root cause hypotheses.

Each rule inspects a TriageResult and returns matching finding groups that
support a particular root cause hypothesis. Rules are evaluated in order
and all matching rules contribute hypotheses to the engine.

Rules are organized by domain:
  - resource_rules: OOM, CPU, taint, node, storage, quota
  - dependency_rules: connection refused, endpoints, DNS, TLS, network, config
  - deployment_rules: image errors, deployment-wide failures
  - admission_rules: webhook, PDB, finalizer
  - probe_event_rules: readiness flapping, crash patterns, escalations, silence
  - connection_rules: connection pool, broken deps, change correlation, overcommit, DNS+netpol
"""

from bundle_analyzer.rca.rules.admission_rules import (
    FINALIZER_STUCK_RULE,
    PDB_DEADLOCK_RULE,
    WEBHOOK_ADMISSION_FAILURE_RULE,
)
from bundle_analyzer.rca.rules.base import RCARule
from bundle_analyzer.rca.rules.connection_rules import (
    BROKEN_DEPENDENCY_RULE,
    CHANGE_CORRELATED_FAILURE_RULE,
    CONNECTION_POOL_EXHAUSTION_RULE,
    DNS_NETPOL_LOCKOUT_RULE,
    RESOURCE_OVERCOMMIT_RULE,
)
from bundle_analyzer.rca.rules.deployment_rules import (
    DEPLOYMENT_WIDE_RULE,
    IMAGE_NOT_FOUND_RULE,
    REGISTRY_AUTH_RULE,
)
from bundle_analyzer.rca.rules.dependency_rules import (
    CONFIG_DRIFT_RULE,
    DEPENDENCY_REFUSED_RULE,
    DNS_CASCADE_RULE,
    EMPTY_ENDPOINTS_RULE,
    NETWORK_ISOLATION_RULE,
    TLS_BLOCKING_RULE,
)
from bundle_analyzer.rca.rules.probe_event_rules import (
    CRASH_PATTERN_RULE,
    EVENT_ESCALATION_RULE,
    READINESS_PROBE_FLAPPING_RULE,
    SILENCE_SIGNAL_RULE,
)
from bundle_analyzer.rca.rules.resource_rules import (
    INSUFFICIENT_CPU_RULE,
    NODE_ISSUE_RULE,
    OOM_KILL_RULE,
    QUOTA_SCHEDULING_RULE,
    STORAGE_CASCADE_RULE,
    TAINT_RULE,
)

# Exported rule list — evaluated in order by HypothesisEngine.
RCA_RULES: list[RCARule] = [
    # Original 15 rules
    OOM_KILL_RULE,
    DEPENDENCY_REFUSED_RULE,
    INSUFFICIENT_CPU_RULE,
    TAINT_RULE,
    IMAGE_NOT_FOUND_RULE,
    REGISTRY_AUTH_RULE,
    EMPTY_ENDPOINTS_RULE,
    NODE_ISSUE_RULE,
    DEPLOYMENT_WIDE_RULE,
    DNS_CASCADE_RULE,
    TLS_BLOCKING_RULE,
    STORAGE_CASCADE_RULE,
    QUOTA_SCHEDULING_RULE,
    NETWORK_ISOLATION_RULE,
    CONFIG_DRIFT_RULE,
    # New rules — most specific/highest-confidence first
    WEBHOOK_ADMISSION_FAILURE_RULE,
    PDB_DEADLOCK_RULE,
    DNS_NETPOL_LOCKOUT_RULE,
    READINESS_PROBE_FLAPPING_RULE,
    CONNECTION_POOL_EXHAUSTION_RULE,
    FINALIZER_STUCK_RULE,
    CRASH_PATTERN_RULE,
    BROKEN_DEPENDENCY_RULE,
    CHANGE_CORRELATED_FAILURE_RULE,
    RESOURCE_OVERCOMMIT_RULE,
    EVENT_ESCALATION_RULE,
    SILENCE_SIGNAL_RULE,
]

__all__ = ["RCA_RULES", "RCARule"]
