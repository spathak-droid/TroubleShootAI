"""Interview mode prompt templates.

Contains the prompts used for the forensic Q&A interview mode,
ensuring answers are grounded in bundle evidence.
"""

from __future__ import annotations

from bundle_analyzer.models import AnalysisResult

INTERVIEW_SYSTEM_PROMPT = """\
You are a forensic investigator answering questions about a Kubernetes support bundle.
You have access to the complete analysis results and raw bundle data.

STRICT RULES:
1. Every factual claim must cite specific evidence: pod name, log line, event timestamp
2. If asked something the bundle cannot answer, say so explicitly
3. Format citations as [SOURCE: pods/default/frontend.json line 42]
4. Never confabulate — if you don't see it in the evidence, say you don't see it
5. When asked for a command to fix something, provide the exact kubectl command
6. If the user asks about something not in the analysis, say "I don't have evidence for that in this bundle"
7. Distinguish between what the bundle SHOWS and what you INFER — label inferences clearly
"""


def build_interview_context(analysis_result: AnalysisResult) -> str:
    """Build a context summary of all findings for the interview session.

    Args:
        analysis_result: The complete analysis result to summarize.

    Returns:
        Formatted string with all key findings, timeline, predictions,
        and uncertainty gaps for use as conversation context.
    """
    sections: list[str] = []

    sections.append("## Cluster Summary")
    sections.append(analysis_result.cluster_summary)
    sections.append("")

    # Root cause
    if analysis_result.root_cause:
        sections.append(f"## Root Cause (confidence={analysis_result.confidence})")
        sections.append(analysis_result.root_cause)
        sections.append("")

    # Findings
    if analysis_result.findings:
        sections.append("## Findings")
        for f in analysis_result.findings:
            sections.append(
                f"- [{f.severity}] {f.resource}: {f.symptom} → {f.root_cause} "
                f"(confidence={f.confidence})"
            )
            for ev in f.evidence:
                sections.append(f"  [SOURCE: {ev.file}] {ev.excerpt}")
        sections.append("")

    # Triage critical pods
    if analysis_result.triage.critical_pods:
        sections.append("## Critical Pods (from triage)")
        for pod in analysis_result.triage.critical_pods:
            sections.append(
                f"- {pod.namespace}/{pod.pod_name}: {pod.issue_type} "
                f"(restarts={pod.restart_count}, exit={pod.exit_code}) {pod.message}"
            )
        sections.append("")

    # Node issues
    if analysis_result.triage.node_issues:
        sections.append("## Node Issues (from triage)")
        for node in analysis_result.triage.node_issues:
            sections.append(f"- {node.node_name}: {node.condition} — {node.message}")
        sections.append("")

    # Timeline
    if analysis_result.timeline:
        sections.append("## Timeline (most recent 20 events)")
        for event in analysis_result.timeline[-20:]:
            sections.append(
                f"- {event.timestamp.isoformat()}: [{event.event_type}] "
                f"{event.resource_name} — {event.description}"
            )
        sections.append("")

    # Predictions
    if analysis_result.predictions:
        sections.append("## Predictions")
        for p in analysis_result.predictions:
            sections.append(
                f"- {p.resource}: {p.failure_type} ETA={p.estimated_eta_seconds}s "
                f"(confidence={p.confidence}) — {p.prevention}"
            )
        sections.append("")

    # Uncertainty gaps
    if analysis_result.uncertainty:
        sections.append("## Uncertainty Gaps")
        for gap in analysis_result.uncertainty:
            sections.append(
                f"- [{gap.impact}] {gap.question}: {gap.reason}"
            )
            if gap.collect_command:
                sections.append(f"  Collect: {gap.collect_command}")
        sections.append("")

    return "\n".join(sections)
