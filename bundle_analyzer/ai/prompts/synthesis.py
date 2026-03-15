"""Synthesis pass prompt templates.

Contains the prompts used to cross-correlate individual analyst
outputs into unified root cause analysis and causal chains.
"""

from __future__ import annotations

from bundle_analyzer.models import AnalystOutput, TriageResult

SYNTHESIS_SYSTEM_PROMPT = """\
You are the senior incident commander synthesizing reports from specialized analysts \
who each examined different aspects of a Kubernetes cluster failure. Your job is to find \
connections they missed individually and identify the single most likely root cause.

YOUR PRIMARY GOAL: Produce an explanation that a human engineer can read and immediately \
understand WHAT happened, WHY it happened, and HOW to fix it. Do not restate symptoms — \
explain the causal mechanism.

ANALYSIS FRAMEWORK:
1. TEMPORAL CORRELATION: Did node pressure start before pod crashes? Did a config change \
happen right before failures? Events with timestamps < 5 minutes apart are likely causal.
2. CASCADE DETECTION: Trace the domino effect. Example: "node memory pressure → pod eviction → \
service loses endpoints → dependent pods crash-loop trying to connect".
3. COMMON ROOT CAUSE: Multiple analysts may report different symptoms of ONE underlying issue. \
Find it. Example: 3 pods crash-looping + 1 deployment stuck + 1 service with 0 endpoints may all \
stem from a single node going NotReady.
4. CONTRADICTION RESOLUTION: If pod analyst says "OOM" but node analyst shows plenty of memory, \
investigate — is it a container limit (not node limit)?

EVIDENCE RULES:
- Every claim in your root_cause and causal_chain MUST reference specific data from the analyst reports.
- Do NOT say "likely" or "probably" without stating what evidence is missing.
- If analysts found contradictory evidence, explicitly note the contradiction.

CONTEXT SIGNALS (use all that apply):
- Troubleshoot.sh results: INDEPENDENT VALIDATION — corroboration = higher confidence, passing = rule out.
- Crash loop previous logs: Show what happened RIGHT BEFORE the crash — most valuable data.
- Broken service dependencies: Often the ROOT CAUSE (service down → connection refused → crash loop).
- Change correlations: WHAT CHANGED before failures — strong correlations (< 5 min) are likely causal.
- Pod anomalies: Failing vs healthy pod comparison — differences in node/image/config are diagnostic.
- Event escalation patterns: WORSENING issues — prioritize these.
- RBAC blocks: Data COULD NOT be collected — factor into uncertainty.
- Coverage gaps: Unanalyzed data — mention high-priority gaps.

You must respond with valid JSON only. No markdown, no commentary outside the JSON.

Required JSON schema:
{
  "root_cause": "A clear, specific explanation of WHY the failure happened — not just what failed. \
Must reference specific evidence (e.g., 'Node X went NotReady at 10:00 due to memory pressure (7.2Gi/8Gi), \
causing eviction of pods A, B, C which cascaded to service outage')",
  "confidence": "high|medium|low",
  "causal_chain": [
    "Each step must be specific and evidence-backed, not generic",
    "Example: 'Deployment update changed image from v1.2 to v1.3 at 10:00:00Z'",
    "Example: 'New image has startup probe timeout of 5s but app takes 15s to boot'",
    "Example: 'Kubelet kills container after 3 failed probes → CrashLoopBackOff'"
  ],
  "blast_radius": "What else is affected or at risk — be specific about which resources and namespaces",
  "recommended_fixes": [
    {
      "priority": 1,
      "action": "Specific kubectl command or YAML change — not vague advice",
      "expected_effect": "What this fix will resolve and what symptoms will disappear"
    }
  ],
  "uncertainty_report": {
    "what_i_know": ["High-confidence findings backed by direct evidence"],
    "what_i_suspect": ["Hypotheses with partial evidence — state what evidence is missing"],
    "what_i_cant_determine": ["Gaps that require additional data collection — include kubectl commands to gather it"]
  }
}
"""


def build_synthesis_user_prompt(
    analyst_outputs: list[AnalystOutput],
    triage_report: TriageResult,
) -> str:
    """Build the user prompt for synthesis from analyst outputs and triage data.

    Args:
        analyst_outputs: Structured outputs from each analyst (pod, node, config).
        triage_report: Raw triage scan results for additional context.

    Returns:
        Formatted prompt string containing all analyst findings and triage data.
    """
    sections: list[str] = []

    # Triage summary
    sections.append("## Triage Summary")
    sections.append(f"Critical pods: {len(triage_report.critical_pods)}")
    sections.append(f"Warning pods: {len(triage_report.warning_pods)}")
    sections.append(f"Node issues: {len(triage_report.node_issues)}")
    sections.append(f"Deployment issues: {len(triage_report.deployment_issues)}")
    sections.append(f"Config issues: {len(triage_report.config_issues)}")
    sections.append(f"Drift issues: {len(triage_report.drift_issues)}")
    sections.append(f"Silence signals: {len(triage_report.silence_signals)}")
    sections.append(f"Warning events: {len(triage_report.warning_events)}")
    sections.append(f"RBAC issues: {len(triage_report.rbac_issues)}")
    sections.append(f"Quota issues: {len(triage_report.quota_issues)}")
    sections.append(f"Network policy issues: {len(triage_report.network_policy_issues)}")
    sections.append(f"Crash contexts: {len(triage_report.crash_contexts)}")
    sections.append(f"Event escalations: {len(triage_report.event_escalations)}")
    if triage_report.rbac_errors:
        sections.append(f"RBAC errors: {len(triage_report.rbac_errors)}")
    if triage_report.coverage_gaps:
        sections.append(f"Coverage gaps: {len(triage_report.coverage_gaps)} uncovered areas")
    sections.append("")

    # Critical pod details
    if triage_report.critical_pods:
        sections.append("### Critical Pods")
        for pod in triage_report.critical_pods:
            sections.append(
                f"- {pod.namespace}/{pod.pod_name}: {pod.issue_type} "
                f"(restarts={pod.restart_count}, exit_code={pod.exit_code}) "
                f"— {pod.message}"
            )
        sections.append("")

    # Node issue details
    if triage_report.node_issues:
        sections.append("### Node Issues")
        for node in triage_report.node_issues:
            sections.append(
                f"- {node.node_name}: {node.condition} — {node.message}"
            )
        sections.append("")

    # RBAC issue details
    if triage_report.rbac_issues:
        sections.append("### RBAC / Permission Issues")
        for issue in triage_report.rbac_issues:
            sections.append(f"- {issue.namespace}: {issue.resource_type} — {issue.error_message}")
        sections.append("")

    # Quota issue details
    if triage_report.quota_issues:
        sections.append("### Resource Quota Issues")
        for issue in triage_report.quota_issues:
            sections.append(
                f"- {issue.namespace}/{issue.resource_name}: "
                f"{issue.issue_type} ({issue.resource_type}) — {issue.message}"
            )
        sections.append("")

    # Network policy issue details
    if triage_report.network_policy_issues:
        sections.append("### Network Policy Issues")
        for issue in triage_report.network_policy_issues:
            affected = ", ".join(issue.affected_pods[:5]) if issue.affected_pods else "unknown"
            sections.append(
                f"- {issue.namespace}/{issue.policy_name}: "
                f"{issue.issue_type} affecting [{affected}] — {issue.message}"
            )
        sections.append("")

    # Crash loop context details (most valuable — includes log excerpts)
    if triage_report.crash_contexts:
        sections.append("### Crash Loop Analysis (from previous logs)")
        for ctx in triage_report.crash_contexts:
            sections.append(
                f"- {ctx.namespace}/{ctx.pod_name}/{ctx.container_name}: "
                f"pattern={ctx.crash_pattern}, exit_code={ctx.exit_code}, "
                f"restarts={ctx.restart_count}"
            )
            if ctx.previous_log_lines:
                sections.append(
                    f"  Previous log (last lines): {' | '.join(ctx.previous_log_lines[-5:])}"
                )
            if ctx.last_log_lines:
                sections.append(
                    f"  Current log (last lines): {' | '.join(ctx.last_log_lines[-3:])}"
                )
        sections.append("")

    # Event escalation pattern details
    if triage_report.event_escalations:
        sections.append("### Event Escalation Patterns")
        for esc in triage_report.event_escalations:
            sections.append(
                f"- {esc.namespace}/{esc.involved_object_kind}/{esc.involved_object_name}: "
                f"{esc.escalation_type} ({esc.total_count} events) — {esc.message}"
            )
        sections.append("")

    # Analyst outputs
    for output in analyst_outputs:
        sections.append(f"## {output.analyst.upper()} Analyst Report")
        if output.root_cause:
            sections.append(f"Root cause: {output.root_cause}")
        sections.append(f"Confidence: {output.confidence}")

        if output.findings:
            sections.append("### Findings")
            for finding in output.findings:
                sections.append(
                    f"- [{finding.severity}] {finding.resource}: "
                    f"{finding.symptom} → {finding.root_cause} "
                    f"(confidence={finding.confidence})"
                )

        if output.uncertainty:
            sections.append("### Uncertainty")
            for gap in output.uncertainty:
                sections.append(f"- {gap}")

        sections.append("")

    # Troubleshoot.sh analyzer results (independent validation)
    if triage_report.troubleshoot_analysis.has_results:
        sections.append("## Troubleshoot.sh Analyzer Results (Independent Validation)")
        for r in triage_report.troubleshoot_analysis.results:
            if not r.is_pass:  # only include non-passing for token efficiency
                icon = "WARN" if r.is_warn else "FAIL"
                sections.append(f"- [{icon}] {r.title}: {r.message}")
        sections.append(
            f"- {triage_report.troubleshoot_analysis.pass_count} checks passed"
        )
        sections.append("")

    if triage_report.preflight_report and triage_report.preflight_report.results:
        sections.append("## Preflight Check Results")
        for r in triage_report.preflight_report.results:
            if not r.is_pass:
                icon = "WARN" if r.is_warn else "FAIL"
                sections.append(f"- [{icon}] {r.title}: {r.message}")
        sections.append("")

    if triage_report.external_analyzer_issues:
        sections.append("## External Analyzer Issues (no native scanner)")
        for issue in triage_report.external_analyzer_issues:
            corr = f" [corroborates: {issue.corroborates}]" if issue.corroborates else ""
            sections.append(
                f"- [{issue.severity}] {issue.analyzer_type}: "
                f"{issue.title} — {issue.message}{corr}"
            )
        sections.append("")

    if triage_report.coverage_gaps:
        high_gaps = [g for g in triage_report.coverage_gaps if g.severity == "high"]
        if high_gaps:
            sections.append("### HIGH-PRIORITY Coverage Gaps (data present but unanalyzed)")
            for gap in high_gaps:
                sections.append(f"- {gap.area}: {gap.why_it_matters}")
            sections.append("")

    # Pod anomalies (failing vs healthy comparison)
    if triage_report.pod_anomalies:
        sections.append("## Pod Anomaly Detection (failing vs healthy comparison)")
        for anomaly in triage_report.pod_anomalies[:10]:  # cap at 10 for token efficiency
            sections.append(
                f"- {anomaly.failing_pod} [{anomaly.anomaly_type}]: "
                f"{anomaly.description} "
                f"(failing={anomaly.failing_value}, healthy={anomaly.healthy_value})"
            )
            if hasattr(anomaly, "suggestion") and anomaly.suggestion:
                sections.append(f"  → Suggestion: {anomaly.suggestion}")
        sections.append("")

    # Dependency map (broken dependencies)
    if triage_report.dependency_map and hasattr(triage_report.dependency_map, "broken_dependencies"):
        broken = triage_report.dependency_map.broken_dependencies
        if broken:
            sections.append("## Broken Service Dependencies")
            for dep in broken[:10]:
                sections.append(
                    f"- {dep.source_pod} → {dep.target_service}: "
                    f"{dep.health_detail} (discovered via {dep.discovery_method})"
                )
            sections.append(
                f"Total: {triage_report.dependency_map.total_services_discovered} deps discovered, "
                f"{triage_report.dependency_map.total_broken} broken"
            )
            sections.append("")

    # Change correlations ("what changed?")
    if triage_report.change_report and hasattr(triage_report.change_report, "correlations"):
        corrs = triage_report.change_report.correlations
        if corrs:
            sections.append("## What Changed Before Failures (Change Correlation)")
            for corr in corrs[:5]:
                {"strong": "🔴", "moderate": "🟡", "weak": "⚪"}.get(
                    corr.correlation_strength, "⚪"
                )
                sections.append(
                    f"- [{corr.correlation_strength.upper()}] {corr.change.resource_type}/"
                    f"{corr.change.resource_name}: {corr.change.change_type} "
                    f"({corr.time_delta_seconds:.0f}s before failure) — {corr.explanation}"
                )
            sections.append("")

    sections.append(
        "Cross-correlate these reports. Identify the single most likely root cause, "
        "the causal chain, blast radius, and recommended fixes. "
        "Respond with valid JSON only."
    )

    return "\n".join(sections)
