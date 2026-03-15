"""Pod analyst system and user prompt templates.

Contains the structured prompts used by the pod analyst
to analyze pod failures, exit codes, and container logs.
"""

from __future__ import annotations

from typing import Optional

POD_SYSTEM_PROMPT = """\
You are a Kubernetes forensics expert analyzing a support bundle — forensic evidence \
from a cluster you cannot access directly. Your job is to determine the root cause \
of pod failures with the precision of a detective, not just describe symptoms.

CRITICAL RULES:
1. DISTINGUISH immediate cause from root cause. "CrashLoopBackOff" is NEVER a root cause — \
it is a symptom. The root cause is WHY the container crashes (OOM, bad config, dependency down, code bug).
2. EVIDENCE MUST BE SPECIFIC. Do NOT say "the pod is crashing". Instead cite the exact log line, \
exit code, event message, or status field that proves your claim. Each evidence item must quote \
actual data from the bundle sections provided above.
3. If you see previous logs, they show what happened BEFORE the crash — this is the most valuable data. \
Look for: connection refused errors, missing env vars, failed health checks, stack traces.
4. OOM kills (exit code 137) leave no application logs — reason backwards from memory limits vs requests.
5. A missing ConfigMap/Secret is NEVER the root cause — ask WHY it's missing (deleted? wrong namespace? typo?).
6. CAUSAL CHAIN must be a logical sequence from root cause → intermediate effects → observed symptom. \
Each step must be supported by evidence from the data.
7. For the "fix" field: provide specific kubectl commands or YAML changes, not vague advice.
8. State confidence as "high" ONLY if you have direct evidence (log lines, exit codes). \
Use "medium" if reasoning from indirect evidence. Use "low" if speculating.

You must respond with valid JSON only. Do not include any text before or after the JSON.

Respond in this exact JSON format:
{
  "immediate_cause": "The directly observed failure (e.g., 'container exited with code 1 after OOM kill')",
  "root_cause": "The underlying WHY (e.g., 'Java heap set to 512Mi but container limit is 256Mi')",
  "confidence": "high|medium|low",
  "evidence": [
    "QUOTE exact data with source file path: '[source: cluster-resources/pods/default/web-1.json] exitCode: 137 in containerStatuses[0].lastState.terminated'",
    "QUOTE exact data with source file path: '[source: cluster-resources/pods/default/web-1.json] memory limit 256Mi but -Xmx512m in container args'",
    "QUOTE exact log line with source file path: '[source: default/web-1/app/app.log] 2024-01-15T10:23:45Z java.lang.OutOfMemoryError: Java heap space'"
  ],
  "causal_chain": [
    "Root: Java heap configured to 512Mi exceeds container memory limit of 256Mi",
    "Effect: JVM allocates beyond cgroup limit, kernel OOM-kills the process (exit code 137)",
    "Effect: Kubelet restarts container, which immediately OOMs again",
    "Symptom: CrashLoopBackOff with increasing backoff delay"
  ],
  "fix": "Increase memory limit to 768Mi: kubectl patch deployment X -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"app\",\"resources\":{\"limits\":{\"memory\":\"768Mi\"}}}]}}}}'",
  "what_i_cant_tell": ["Whether the heap size was recently changed (no git history in bundle)"]
}"""


def build_pod_user_prompt(
    pod_json: str,
    current_logs: Optional[str] = None,
    previous_logs: Optional[str] = None,
    exit_codes: Optional[str] = None,
    events: Optional[str] = None,
    node_conditions: Optional[str] = None,
    *,
    pod_json_path: str = "",
    log_paths: Optional[list[str]] = None,
    events_path: str = "",
    node_json_path: str = "",
) -> str:
    """Build a structured context block for the pod analyst.

    Args:
        pod_json: Serialised pod spec + status JSON.
        current_logs: Last 200 lines of current container logs.
        previous_logs: Last 100 lines of previous container logs (pre-crash).
        exit_codes: Summary of container exit codes and restart counts.
        events: Warning events related to this pod.
        node_conditions: Conditions of the node this pod is scheduled on.
        pod_json_path: Actual bundle-relative path to the pod JSON file.
        log_paths: Actual bundle-relative paths to container log files.
        events_path: Actual bundle-relative path to the events file.
        node_json_path: Actual bundle-relative path to the node JSON file.

    Returns:
        Formatted user prompt string with all available context sections.
    """
    sections: list[str] = []

    pod_header = "## Pod Spec & Status"
    if pod_json_path:
        pod_header += f" [source: {pod_json_path}]"
    sections.append(pod_header + "\n```json\n" + pod_json + "\n```")

    if current_logs:
        log_header = "## Current Container Logs (last 200 lines)"
        if log_paths:
            log_header += " [source: " + ", ".join(log_paths) + "]"
        sections.append(log_header + "\n```\n" + current_logs + "\n```")
    else:
        sections.append("## Current Container Logs\n*No logs available.*")

    if previous_logs:
        prev_header = "## Previous Container Logs (last 100 lines, pre-crash)"
        if log_paths:
            prev_paths = [p.replace(".log", "-previous.log") for p in log_paths]
            prev_header += " [source: " + ", ".join(prev_paths) + "]"
        sections.append(prev_header + "\n```\n" + previous_logs + "\n```")

    if exit_codes:
        exit_header = "## Exit Codes & Restart Counts"
        if pod_json_path:
            exit_header += f" [source: {pod_json_path}]"
        sections.append(exit_header + "\n" + exit_codes)

    if events:
        events_header = "## Warning Events for this Pod"
        if events_path:
            events_header += f" [source: {events_path}]"
        sections.append(events_header + "\n```\n" + events + "\n```")
    else:
        sections.append("## Warning Events\n*No warning events found for this pod.*")

    if node_conditions:
        node_header = "## Node Conditions (node this pod is scheduled on)"
        if node_json_path:
            node_header += f" [source: {node_json_path}]"
        sections.append(node_header + "\n```\n" + node_conditions + "\n```")

    sections.append(
        "---\n\nAnalyze the above evidence and respond with the JSON format specified. "
        "When quoting evidence, include the [source: <path>] tag from the section header "
        "where you found the data."
    )

    return "\n\n".join(sections)
