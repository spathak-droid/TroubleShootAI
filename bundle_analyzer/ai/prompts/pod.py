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

Rules:
1. Always distinguish between the immediate cause and the root cause
2. If you see previous logs, they show what happened BEFORE the crash — mine them for clues
3. OOM kills leave no application logs — reason backwards from the exit code and memory stats
4. A missing ConfigMap is never the root cause — ask why it's missing
5. State your confidence level (high/medium/low) and what would raise it
6. If you cannot determine root cause, say exactly what additional data would help

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


def build_pod_user_prompt(
    pod_json: str,
    current_logs: Optional[str] = None,
    previous_logs: Optional[str] = None,
    exit_codes: Optional[str] = None,
    events: Optional[str] = None,
    node_conditions: Optional[str] = None,
) -> str:
    """Build a structured context block for the pod analyst.

    Args:
        pod_json: Serialised pod spec + status JSON.
        current_logs: Last 200 lines of current container logs.
        previous_logs: Last 100 lines of previous container logs (pre-crash).
        exit_codes: Summary of container exit codes and restart counts.
        events: Warning events related to this pod.
        node_conditions: Conditions of the node this pod is scheduled on.

    Returns:
        Formatted user prompt string with all available context sections.
    """
    sections: list[str] = []

    sections.append("## Pod Spec & Status\n```json\n" + pod_json + "\n```")

    if current_logs:
        sections.append(
            "## Current Container Logs (last 200 lines)\n```\n"
            + current_logs
            + "\n```"
        )
    else:
        sections.append("## Current Container Logs\n*No logs available.*")

    if previous_logs:
        sections.append(
            "## Previous Container Logs (last 100 lines, pre-crash)\n```\n"
            + previous_logs
            + "\n```"
        )

    if exit_codes:
        sections.append("## Exit Codes & Restart Counts\n" + exit_codes)

    if events:
        sections.append("## Warning Events for this Pod\n```\n" + events + "\n```")
    else:
        sections.append("## Warning Events\n*No warning events found for this pod.*")

    if node_conditions:
        sections.append(
            "## Node Conditions (node this pod is scheduled on)\n```\n"
            + node_conditions
            + "\n```"
        )

    sections.append(
        "---\n\nAnalyze the above evidence and respond with the JSON format specified."
    )

    return "\n\n".join(sections)
