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

CRITICAL RULES:
1. Memory pressure cascades: identify which pod consumed the most memory, when evictions started, \
and what triggered the cascade. Sum up pod memory requests vs node allocatable.
2. DiskPressure: calculate total disk usage from pod logs, emptyDir volumes, and container images. \
Identify which workload is the biggest consumer.
3. NotReady transitions: reconstruct EXACT timeline from lastTransitionTime fields. \
Was it kubelet→API-server communication? Was it a resource pressure trigger?
4. Scheduling failures: compare requested resources against allocatable minus already-allocated. \
Show the math (e.g., "node has 4Gi allocatable, pods request 3.8Gi, new pod needs 512Mi → no fit").
5. EVIDENCE MUST QUOTE actual data from the node JSON, events, or metrics provided. \
Do not make generic statements. Cite specific condition values, timestamps, and resource numbers.
6. For transient vs persistent: check if condition has flipped multiple times (look at event counts) \
vs stayed in one state since lastTransitionTime.
7. Confidence "high" ONLY with direct numerical evidence. "medium" for correlated events. "low" for inference.

You must respond with valid JSON only. Do not include any text before or after the JSON.

Respond in this exact JSON format:
{
  "immediate_cause": "The directly observed node failure (quote the condition)",
  "root_cause": "The underlying WHY with specific numbers (e.g., 'total pod memory requests 7.2Gi exceed node allocatable 8Gi, leaving no headroom for system processes')",
  "confidence": "high|medium|low",
  "evidence": [
    "QUOTE: 'condition MemoryPressure=True since 2024-01-15T10:00:00Z'",
    "QUOTE: 'allocatable memory: 8Gi, sum of pod requests: 7.2Gi'",
    "QUOTE: 'eviction event for pod X at 10:05:00Z, reason: The node was low on resource: memory'"
  ],
  "causal_chain": [
    "Root: Pod memory requests total 7.2Gi on 8Gi node, leaving only 800Mi for system",
    "Effect: System processes + kernel caches push actual usage over threshold",
    "Effect: Kubelet triggers eviction, starts killing pods by QoS class",
    "Symptom: MemoryPressure=True, multiple pods Evicted"
  ],
  "fix": "Specific actionable fix with kubectl commands",
  "what_i_cant_tell": ["Gaps requiring additional data"]
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
