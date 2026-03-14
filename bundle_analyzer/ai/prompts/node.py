"""Node analyst prompt templates.

Contains the structured prompts used by the node analyst
to analyze node conditions, resource pressure, and scheduling.
"""

from __future__ import annotations

from typing import Optional

NODE_SYSTEM_PROMPT = """\
You are a Kubernetes node forensics expert analyzing a support bundle — forensic evidence \
from a cluster you cannot access directly. Your focus is node-level failures: resource \
pressure cascades, scheduling breakdowns, and infrastructure issues.

Rules:
1. Memory pressure cascades: determine which pod was evicted first and what triggered it
2. DiskPressure: identify which workload is filling disk (logs, emptyDir, persistent volumes)
3. NotReady transitions: reconstruct the timeline of when and why the node went NotReady
4. Scheduling failures: distinguish between resource fragmentation and true capacity limits
5. Always check if node conditions are transient or persistent
6. State your confidence level (high/medium/low) and what would raise it
7. If you cannot determine root cause, say exactly what additional data would help

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


def build_node_user_prompt(
    node_json: str,
    scheduled_pods: Optional[str] = None,
    node_metrics: Optional[str] = None,
    warning_events: Optional[str] = None,
    eviction_events: Optional[str] = None,
) -> str:
    """Build a structured context block for the node analyst.

    Args:
        node_json: Serialised node JSON (conditions, capacity, allocatable).
        scheduled_pods: Pods scheduled on this node with resource requests.
        node_metrics: Node metrics if available.
        warning_events: Warning events for this node.
        eviction_events: Eviction events on this node.

    Returns:
        Formatted user prompt string with all available context sections.
    """
    sections: list[str] = []

    sections.append("## Node Spec & Status\n```json\n" + node_json + "\n```")

    if scheduled_pods:
        sections.append(
            "## Pods Scheduled on This Node (with resource requests)\n```\n"
            + scheduled_pods
            + "\n```"
        )
    else:
        sections.append("## Pods Scheduled on This Node\n*No pod data available.*")

    if node_metrics:
        sections.append("## Node Metrics\n```\n" + node_metrics + "\n```")

    if warning_events:
        sections.append(
            "## Warning Events for This Node\n```\n" + warning_events + "\n```"
        )
    else:
        sections.append("## Warning Events\n*No warning events found for this node.*")

    if eviction_events:
        sections.append("## Eviction Events\n```\n" + eviction_events + "\n```")

    sections.append(
        "---\n\nAnalyze the above evidence and respond with the JSON format specified."
    )

    return "\n\n".join(sections)
