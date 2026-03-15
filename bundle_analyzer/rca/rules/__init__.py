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
from bundle_analyzer.rca.rules.deployment_rules import DEPLOYMENT_RULES
from bundle_analyzer.rca.rules.dependency_rules import DEPENDENCY_RULES
from bundle_analyzer.rca.rules.resource_rules import RESOURCE_RULES

# Exported rule list — evaluated in order by HypothesisEngine.
# Order: OOM → dependency → CPU → taint → image → registry → endpoints →
#         node → deployment-wide → DNS → TLS → storage → quota → network → config
RCA_RULES: list[RCARule] = [
    RESOURCE_RULES[0],      # oom_kill
    DEPENDENCY_RULES[0],    # dependency_connection_refused
    RESOURCE_RULES[1],      # insufficient_cpu
    RESOURCE_RULES[2],      # taint_not_tolerated
    DEPLOYMENT_RULES[0],    # image_not_found
    DEPLOYMENT_RULES[1],    # registry_auth_failure
    DEPENDENCY_RULES[1],    # empty_endpoints
    RESOURCE_RULES[3],      # node_issue
    DEPLOYMENT_RULES[2],    # deployment_wide_failure
    DEPENDENCY_RULES[2],    # dns_cascade
    DEPENDENCY_RULES[3],    # tls_blocking
    RESOURCE_RULES[4],      # storage_cascade
    RESOURCE_RULES[5],      # quota_scheduling
    DEPENDENCY_RULES[4],    # network_isolation
    DEPENDENCY_RULES[5],    # config_drift_restart
]

__all__ = ["RCA_RULES", "RCARule"]
