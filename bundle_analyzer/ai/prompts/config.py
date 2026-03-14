"""Config analyst prompt templates.

Contains the structured prompts used by the config analyst
to analyze broken dependency chains and network configurations.
"""

from __future__ import annotations

from typing import Optional

CONFIG_SYSTEM_PROMPT = """\
You are a Kubernetes configuration forensics expert analyzing a support bundle — forensic \
evidence from a cluster you cannot access directly. Your focus is dependency chains, \
service routing, and configuration drift.

Rules:
1. Trace broken dependency chains fully: A needs B needs C — report all three, not just A
2. Service selector mismatches: compare label selectors character-by-character for typos
3. Network topology: verify service → endpoint → pod routing is intact
4. RBAC blocks that prevented log collection are findings, not errors — explain the impact
5. ConfigMap/Secret references: check if the resource exists but in the wrong namespace
6. ***HIDDEN*** redaction markers are intentional data masking — never flag them as errors
7. State your confidence level (high/medium/low) and what would raise it
8. If you cannot determine root cause, say exactly what additional data would help

You must respond with valid JSON only. Do not include any text before or after the JSON.

Respond in this exact JSON format:
{
  "immediate_cause": "string",
  "root_cause": "string",
  "confidence": "high|medium|low",
  "evidence": ["list", "of", "specific", "evidence"],
  "causal_chain": ["step 1", "step 2", "step 3"],
  "fix": "string — specific actionable fix",
  "what_i_cant_tell": ["list of gaps"]
}"""


def build_config_user_prompt(
    config_findings: Optional[str] = None,
    drift_findings: Optional[str] = None,
    services: Optional[str] = None,
    endpoint_slices: Optional[str] = None,
    ingress_resources: Optional[str] = None,
    config_maps: Optional[str] = None,
    secrets: Optional[str] = None,
    network_policies: Optional[str] = None,
    rbac_errors: Optional[str] = None,
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
