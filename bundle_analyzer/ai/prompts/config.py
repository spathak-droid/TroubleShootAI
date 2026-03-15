"""Config analyst prompt templates.

Contains the structured prompts used by the config analyst
to analyze broken dependency chains and network configurations.
"""

from __future__ import annotations

CONFIG_SYSTEM_PROMPT = """\
You are a Kubernetes configuration forensics expert analyzing a support bundle — forensic \
evidence from a cluster you cannot access directly. Your focus is dependency chains, \
service routing, and configuration drift.

CRITICAL RULES:
1. TRACE FULL DEPENDENCY CHAINS: If Pod A can't reach Service B because Service B has no endpoints \
because Deployment C has a selector mismatch — report the ENTIRE chain A→B→C, not just "Pod A can't connect".
2. SERVICE SELECTOR MISMATCHES: Compare label selectors character-by-character against actual pod labels. \
Quote both the selector and the pod labels to show the mismatch.
3. NETWORK TOPOLOGY: Verify the full path: Service → Endpoints (ready count) → Pod (running + passing readiness). \
A service with 0 ready endpoints is a smoking gun.
4. RBAC blocks that prevented log collection are findings — explain what data is MISSING and how it affects diagnosis.
5. ConfigMap/Secret references: When missing, check if the resource exists in a DIFFERENT namespace. \
Quote the referencing pod's namespace and the available ConfigMaps/Secrets.
6. ***HIDDEN*** redaction markers are intentional data masking — NEVER flag them as errors.
7. EVIDENCE MUST BE SPECIFIC: Quote the exact scanner finding, service selector, endpoint count, \
or ConfigMap name that supports your claim.
8. Confidence "high" ONLY when you can point to specific mismatches. "medium" for likely issues. "low" for inference.

You must respond with valid JSON only. Do not include any text before or after the JSON.

Respond in this exact JSON format:
{
  "immediate_cause": "The directly observed config failure (quote the specific finding)",
  "root_cause": "The underlying WHY (e.g., 'Service selector app=myapp-v2 does not match any pod labels — pods have app=myapp')",
  "confidence": "high|medium|low",
  "evidence": [
    "QUOTE: 'Service default/myapp-svc selector={app: myapp-v2} has 0 ready endpoints'",
    "QUOTE: 'Pod default/myapp-abc has labels {app: myapp, version: v1} — no match for v2'",
    "QUOTE: 'ConfigScanner: [missing_configmap] ConfigMap/app-config in default, referenced by deployment/myapp'"
  ],
  "causal_chain": [
    "Root: Service selector 'app=myapp-v2' was updated but pod labels still say 'app=myapp'",
    "Effect: Service has 0 endpoints — no traffic can be routed",
    "Effect: Other pods connecting to this service get 'connection refused'",
    "Symptom: Dependent pods crash-loop with connection errors"
  ],
  "fix": "Fix the selector mismatch: kubectl patch service myapp-svc -p '{\"spec\":{\"selector\":{\"app\":\"myapp\"}}}'",
  "what_i_cant_tell": ["Whether the selector or the labels were changed most recently"]
}"""


def build_config_user_prompt(
    config_findings: str | None = None,
    drift_findings: str | None = None,
    services: str | None = None,
    endpoint_slices: str | None = None,
    ingress_resources: str | None = None,
    config_maps: str | None = None,
    secrets: str | None = None,
    network_policies: str | None = None,
    rbac_errors: str | None = None,
) -> str:
    """Build a structured context block for the config analyst.

    Args:
        config_findings: Serialised ConfigScanner findings.
        drift_findings: Serialised DriftScanner findings.
        services: Services and their selectors.
        endpoint_slices: EndpointSlice data.
        ingress_resources: Ingress resources and their backends.
        config_maps: ConfigMap names (not values) by namespace.
        secrets: Secret names (not values) by namespace.
        network_policies: NetworkPolicy resources if present.
        rbac_errors: RBAC errors encountered during bundle collection.

    Returns:
        Formatted user prompt string with all available context sections.
    """
    sections: list[str] = []

    if config_findings:
        sections.append(
            "## ConfigScanner Findings\n```\n" + config_findings + "\n```"
        )
    else:
        sections.append("## ConfigScanner Findings\n*No configuration issues detected.*")

    if drift_findings:
        sections.append(
            "## DriftScanner Findings\n```\n" + drift_findings + "\n```"
        )

    if services:
        sections.append("## Services\n```\n" + services + "\n```")

    if endpoint_slices:
        sections.append("## Endpoint Slices\n```\n" + endpoint_slices + "\n```")

    if ingress_resources:
        sections.append("## Ingress Resources\n```\n" + ingress_resources + "\n```")

    if config_maps:
        sections.append(
            "## ConfigMaps (names only)\n```\n" + config_maps + "\n```"
        )

    if secrets:
        sections.append("## Secrets (names only)\n```\n" + secrets + "\n```")

    if network_policies:
        sections.append(
            "## NetworkPolicies\n```\n" + network_policies + "\n```"
        )

    if rbac_errors:
        sections.append(
            "## RBAC Errors (from bundle collection)\n"
            "Note: These are findings — they indicate what data could NOT be collected.\n"
            "```\n" + rbac_errors + "\n```"
        )

    if not sections:
        sections.append("*No configuration data available for analysis.*")

    sections.append(
        "---\n\nAnalyze the above evidence and respond with the JSON format specified."
    )

    return "\n\n".join(sections)
