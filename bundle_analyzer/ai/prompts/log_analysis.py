"""Prompts for the AI log analyst — deep container log forensics.

Provides the system prompt for Kubernetes log analysis and a builder
function that assembles a structured user prompt from crash context data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bundle_analyzer.models import LogIntelligence

LOG_ANALYSIS_SYSTEM_PROMPT = """\
You are a Kubernetes log forensics expert. You are given container logs from a crash-looping \
or failing pod. Your job is to read the logs carefully and explain:

1. What happened — the specific error or failure
2. Why it happened — the root cause (config error? missing dependency? code bug? resource limit?)
3. How to fix it — specific kubectl commands, YAML changes, or code fixes

Important:
- Read the PREVIOUS logs (pre-crash) — they show what happened RIGHT BEFORE the crash
- Look for error patterns: stack traces, connection errors, permission issues, config parse failures
- ***HIDDEN*** markers indicate redacted sensitive data — this is intentional, not an error
- Be specific: cite the exact log line that reveals the problem
- If logs are empty or insufficient, say so clearly

You must respond with valid JSON only. No markdown, no commentary outside the JSON.

Required JSON schema:
{
  "diagnosis": "Plain English explanation of what went wrong",
  "root_cause_category": "one of: oom|crash|config_error|dependency_failure|permission_error|resource_limit|code_bug|unknown",
  "key_log_line": "The single most important log line that reveals the problem",
  "why": "Why this happened — the underlying cause",
  "fix": {
    "description": "What to do to fix it",
    "commands": ["kubectl command 1", "kubectl command 2"],
    "yaml_changes": "description of YAML changes needed, if any"
  },
  "confidence": "high|medium|low",
  "additional_context_needed": ["list of things that would help diagnose further"]
}
"""


def build_log_analysis_prompt(
    pod_name: str,
    namespace: str,
    container_name: str,
    crash_pattern: str,
    exit_code: int | None,
    termination_reason: str,
    restart_count: int,
    current_logs: list[str],
    previous_logs: list[str],
    related_events: str | None = None,
) -> str:
    """Build the user prompt for log analysis from crash context data.

    Assembles all available crash context — metadata, current logs,
    previous (pre-crash) logs, and related Kubernetes events — into
    a structured prompt that the AI can analyze.

    Args:
        pod_name: Name of the crashing pod.
        namespace: Kubernetes namespace of the pod.
        container_name: Name of the container within the pod.
        crash_pattern: Classified crash pattern (e.g. "oom", "panic", "config_error").
        exit_code: Container exit code, if available.
        termination_reason: Kubernetes termination reason string.
        restart_count: Number of container restarts observed.
        current_logs: Recent log lines from the current container instance.
        previous_logs: Log lines from the previous (pre-crash) container instance.
        related_events: Formatted string of warning events for this pod, or None.

    Returns:
        A formatted user prompt string for the AI log analyst.
    """
    sections: list[str] = []

    # Header
    sections.append(f"## Pod: {namespace}/{pod_name}")
    sections.append(f"Container: {container_name}")
    sections.append(f"Restart count: {restart_count}")
    sections.append(f"Crash pattern (regex-classified): {crash_pattern}")

    if exit_code is not None:
        sections.append(f"Exit code: {exit_code}")
    if termination_reason:
        sections.append(f"Termination reason: {termination_reason}")

    sections.append("")

    # Previous logs (pre-crash) — most valuable
    sections.append("## Previous Container Logs (pre-crash)")
    if previous_logs:
        sections.append("These logs are from the container instance that crashed:")
        sections.append("```")
        sections.append("\n".join(previous_logs))
        sections.append("```")
    else:
        sections.append("(no previous logs available)")

    sections.append("")

    # Current logs
    sections.append("## Current Container Logs")
    if current_logs:
        sections.append("These logs are from the current (restarted) container instance:")
        sections.append("```")
        sections.append("\n".join(current_logs))
        sections.append("```")
    else:
        sections.append("(no current logs available)")

    sections.append("")

    # Related events
    sections.append("## Related Kubernetes Events")
    if related_events:
        sections.append(related_events)
    else:
        sections.append("(no warning events found for this pod)")

    sections.append("")
    sections.append(
        "Analyze these logs and provide your diagnosis as JSON. "
        "Focus on the PREVIOUS logs — they show what happened right before the crash."
    )

    return "\n".join(sections)


def build_intelligent_log_prompt(
    pod_name: str,
    namespace: str,
    container_name: str,
    crash_pattern: str,
    exit_code: int | None,
    termination_reason: str,
    restart_count: int,
    intelligence: LogIntelligence,
    related_events: str | None = None,
) -> str:
    """Build an AI prompt using pre-digested LogIntelligence instead of raw logs.

    This produces a much richer prompt with error frequencies, stack trace
    groups, interesting windows, and rate analysis — giving the AI better
    context in fewer tokens than dumping raw log lines.

    Args:
        pod_name: Name of the crashing pod.
        namespace: Kubernetes namespace.
        container_name: Container name.
        crash_pattern: Classified crash pattern from regex triage.
        exit_code: Container exit code, if available.
        termination_reason: Kubernetes termination reason.
        restart_count: Number of container restarts.
        intelligence: Pre-digested LogIntelligence from the engine.
        related_events: Formatted warning events string, or None.

    Returns:
        A formatted prompt with structured log intelligence.
    """
    sections: list[str] = []

    # Header
    sections.append(f"## Pod: {namespace}/{pod_name}")
    sections.append(f"Container: {container_name}")
    sections.append(f"Restart count: {restart_count}")
    sections.append(f"Crash pattern (regex-classified): {crash_pattern}")
    if exit_code is not None:
        sections.append(f"Exit code: {exit_code}")
    if termination_reason:
        sections.append(f"Termination reason: {termination_reason}")
    sections.append("")

    # Log intelligence summary
    sections.append("## Log Intelligence Summary")
    sections.append(f"- Total lines scanned: {intelligence.total_lines_scanned:,}")
    if intelligence.time_span[0] and intelligence.time_span[1]:
        sections.append(
            f"- Time span: {intelligence.time_span[0].isoformat()} to "
            f"{intelligence.time_span[1].isoformat()}"
        )
    if intelligence.level_counts:
        levels_str = ", ".join(
            f"{k}={v}" for k, v in sorted(
                intelligence.level_counts.items(),
                key=lambda x: -x[1],
            )
        )
        sections.append(f"- Log levels: {levels_str}")
    sections.append("")

    # Boolean signals
    signals: list[str] = []
    if intelligence.has_oom_indicators:
        signals.append("OOM/memory exhaustion detected")
    if intelligence.has_connection_errors:
        signals.append("Connection errors detected")
    if intelligence.has_dns_failures:
        signals.append("DNS failures detected")
    if intelligence.has_cert_errors:
        signals.append("Certificate/TLS errors detected")
    if intelligence.has_permission_errors:
        signals.append("Permission/auth errors detected")
    if intelligence.has_rate_limiting:
        signals.append("Rate limiting detected")
    if signals:
        sections.append("## Key Signals")
        for s in signals:
            sections.append(f"- {s}")
        sections.append("")

    # Top error patterns
    if intelligence.top_patterns:
        sections.append("## Top Error Patterns (by frequency)")
        for i, pf in enumerate(intelligence.top_patterns[:10], 1):
            spike_marker = " **SPIKE**" if pf.is_spike else ""
            rate_str = f", {pf.rate_per_minute}/min" if pf.rate_per_minute > 0 else ""
            sections.append(f"{i}. \"{pf.pattern}\" — {pf.count} occurrences{rate_str}{spike_marker}")
            sections.append(f"   Sample: `{pf.sample_line[:200]}`")
        sections.append("")

    # Stack traces (deduplicated)
    if intelligence.stack_traces:
        sections.append(f"## Unique Stack Traces ({len(intelligence.stack_traces)} groups)")
        for i, st in enumerate(intelligence.stack_traces[:5], 1):
            sections.append(
                f"{i}. [{st.language}] {st.exception_type}: {st.exception_message[:150]} "
                f"(x{st.count})"
            )
            sections.append("```")
            sections.append(st.sample_full_trace[:800])
            sections.append("```")
        sections.append("")

    # Interesting log windows
    if intelligence.interesting_windows:
        sections.append("## Key Log Windows")
        for i, w in enumerate(intelligence.interesting_windows[:5], 1):
            ts_str = ""
            if w.timestamp_range[0]:
                ts_str = f" at {w.timestamp_range[0].isoformat()}"
            sections.append(f"### Window {i}: {w.trigger}{ts_str} (lines {w.start_line}-{w.end_line})")
            sections.append("```")
            sections.append("\n".join(w.lines[:_WINDOW_DISPLAY_LINES]))
            sections.append("```")
        sections.append("")

    # Error rate timeline (show only buckets with errors)
    error_buckets = [b for b in intelligence.error_rate_timeline if b.error_count > 0]
    if error_buckets:
        sections.append("## Error Rate Timeline")
        for b in error_buckets[:20]:
            sections.append(
                f"  {b.timestamp.strftime('%H:%M')} | "
                f"{'█' * min(b.error_count, 50)} {b.error_count} errors, {b.warn_count} warns"
            )
        sections.append("")

    # Related events
    sections.append("## Related Kubernetes Events")
    if related_events:
        sections.append(related_events)
    else:
        sections.append("(no warning events found for this pod)")

    sections.append("")
    sections.append(
        "Analyze the above log intelligence and provide your diagnosis as JSON. "
        "The log data has been pre-processed — focus on the patterns, frequencies, "
        "stack traces, and windows to determine root cause."
    )

    return "\n".join(sections)


# Max lines to show per window in the prompt
_WINDOW_DISPLAY_LINES = 25
