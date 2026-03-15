"""Deterministic RCA rules mapping symptom patterns to root cause hypotheses.

Each rule inspects a TriageResult and returns matching finding groups that
support a particular root cause hypothesis. Rules are evaluated in order
and all matching rules contribute hypotheses to the engine.

Rules are organized by domain:
  - resource_rules: OOM, CPU, taint, node, storage, quota
  - dependency_rules: connection refused, endpoints, DNS, TLS, network, config
  - deployment_rules: image errors, deployment-wide failures
"""

from bundle_analyzer.rca.rules.base import RCARule
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
]

__all__ = ["RCA_RULES", "RCARule"]
