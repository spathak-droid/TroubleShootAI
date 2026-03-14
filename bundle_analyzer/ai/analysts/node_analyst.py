"""Node analyst — analyzes node conditions and scheduling failures.

Examines node-level issues like resource pressure, taints,
and correlates them with pod scheduling failures.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.ai.prompts.node import NODE_SYSTEM_PROMPT, build_node_user_prompt
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.security.scrubber import BundleScrubber
from bundle_analyzer.models import (
    AnalystOutput,
    Evidence,
    Finding,
    Fix,
)


class NodeAnalyst:
    """Analyzes node-level issues using Claude for root-cause determination.

    Gathers node JSON, scheduled pods, metrics, warning events, and
    eviction events, then asks Claude to determine the root cause.
    """

    MAX_RETRIES: int = 3
    _scrubber: BundleScrubber = BundleScrubber()

    async def analyze(
        self,
        client: BundleAnalyzerClient,
        node_data: dict[str, Any],
        index: BundleIndex,
    ) -> AnalystOutput:
        """Run AI analysis on a single node.

        Args:
            client: The AI client to use for completions.
            node_data: Parsed node JSON (spec + status).
            index: Bundle index for reading related data.

        Returns:
            AnalystOutput with findings, root cause, evidence, and fixes.
        """
        start = time.monotonic()
        node_name = node_data.get("metadata", {}).get("name", "unknown")

        logger.debug("NodeAnalyst: analyzing node {}", node_name)

        # Scrub node JSON before building prompt
        scrubbed_node, _ = self._scrubber.scrub_node_json(node_data)
        node_json_str = json.dumps(scrubbed_node, indent=2, default=str)
        scheduled_pods = self._get_scheduled_pods(node_name, index)
        node_metrics = self._get_node_metrics(node_name, index)
        warning_events = self._get_warning_events(node_name, index)
        eviction_events = self._get_eviction_events(node_name, index)

        user_prompt = build_node_user_prompt(
            node_json=node_json_str,
            scheduled_pods=scheduled_pods,
            node_metrics=node_metrics,
            warning_events=warning_events,
            eviction_events=eviction_events,
        )

        for attempt in range(self.MAX_RETRIES):
            try:
                raw_response = await client.complete(
                    system=NODE_SYSTEM_PROMPT,
                    user=user_prompt,
                )
                result = self._parse_response(raw_response, node_name)
                elapsed = time.monotonic() - start
                logger.debug(
                    "NodeAnalyst: node {} completed in {:.2f}s",
                    node_name, elapsed,
                )
                return result

            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning(
                    "NodeAnalyst: parse error on attempt {}/{} for node {}: {}",
                    attempt + 1, self.MAX_RETRIES, node_name, exc,
                )
                if attempt == self.MAX_RETRIES - 1:
                    return self._fallback_output(node_name, str(exc))

        return self._fallback_output(node_name, "all retries exhausted")

    def _get_scheduled_pods(
        self, node_name: str, index: BundleIndex
    ) -> str | None:
        """Get pods scheduled on this node with their resource requests."""
        lines: list[str] = []
        for pod in index.get_all_pods():
            spec = pod.get("spec", {})
            if spec.get("nodeName") != node_name:
                continue

            ns = pod.get("metadata", {}).get("namespace", "?")
            name = pod.get("metadata", {}).get("name", "?")
            phase = pod.get("status", {}).get("phase", "?")

            cpu_req = "0"
            mem_req = "0"
            for container in spec.get("containers", []):
                resources = container.get("resources", {}).get("requests", {})
                if resources.get("cpu"):
                    cpu_req = resources["cpu"]
                if resources.get("memory"):
                    mem_req = resources["memory"]

            lines.append(
                f"  {ns}/{name} phase={phase} cpu_req={cpu_req} mem_req={mem_req}"
            )

        return "\n".join(lines) if lines else None

    def _get_node_metrics(
        self, node_name: str, index: BundleIndex
    ) -> str | None:
        """Get node metrics if available."""
        if not index.has("node_metrics"):
            return None

        metrics = index.read_json(f"node-metrics/{node_name}.json")
        if metrics is None:
            return None

        return json.dumps(metrics, indent=2, default=str)

    def _get_warning_events(
        self, node_name: str, index: BundleIndex
    ) -> str | None:
        """Get warning events related to this node."""
        all_events = index.get_events()
        node_events: list[str] = []

        for ev in all_events:
            obj = ev.get("involvedObject", {})
            if (
                obj.get("kind") == "Node"
                and obj.get("name") == node_name
                and ev.get("type") == "Warning"
            ):
                ts = ev.get("lastTimestamp", ev.get("metadata", {}).get("creationTimestamp", "?"))
                reason = ev.get("reason", "?")
                msg = ev.get("message", "")
                count = ev.get("count", 1)
                node_events.append(f"[{ts}] {reason} (x{count}): {msg}")

        return "\n".join(node_events) if node_events else None

    def _get_eviction_events(
        self, node_name: str, index: BundleIndex
    ) -> str | None:
        """Get eviction events on this node."""
        all_events = index.get_events()
        eviction_events: list[str] = []

        for ev in all_events:
            reason = ev.get("reason", "")
            obj = ev.get("involvedObject", {})
            msg = ev.get("message", "")

            if reason in ("Evicted", "Eviction", "EvictionThresholdMet"):
                # Check if this eviction is related to our node
                if node_name in msg or obj.get("name", "") == node_name:
                    ts = ev.get("lastTimestamp", "?")
                    count = ev.get("count", 1)
                    eviction_events.append(f"[{ts}] {reason} (x{count}): {msg}")

        return "\n".join(eviction_events) if eviction_events else None

    def _parse_response(self, raw: str, node_name: str) -> AnalystOutput:
        """Parse Claude's JSON response into an AnalystOutput.

        Args:
            raw: Raw text response from Claude (should be JSON).
            node_name: Node name for building resource identifiers.

        Returns:
            Structured AnalystOutput.

        Raises:
            json.JSONDecodeError: If response is not valid JSON.
        """
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        data = json.loads(cleaned)

        resource = f"node/{node_name}"
        confidence_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
        confidence = confidence_map.get(data.get("confidence", "low"), 0.3)

        finding = Finding(
            id=f"node-{uuid.uuid4().hex[:8]}",
            severity="critical" if confidence >= 0.6 else "warning",
            type="node-issue",
            resource=resource,
            symptom=data.get("immediate_cause", "Unknown symptom"),
            root_cause=data.get("root_cause", "Could not determine root cause"),
            evidence=[
                Evidence(file=resource, excerpt=e)
                for e in data.get("evidence", [])
            ],
            fix=Fix(
                description=data.get("fix", "No fix suggested"),
                commands=[],
            ) if data.get("fix") else None,
            confidence=confidence,
        )

        return AnalystOutput(
            analyst="node",
            findings=[finding],
            root_cause=data.get("root_cause"),
            confidence=confidence,
            evidence=[
                Evidence(file=resource, excerpt=e)
                for e in data.get("evidence", [])
            ],
            remediation=[
                Fix(description=data.get("fix", "No fix suggested"), commands=[])
            ] if data.get("fix") else [],
            uncertainty=data.get("what_i_cant_tell", []),
        )

    @staticmethod
    def _fallback_output(node_name: str, error: str) -> AnalystOutput:
        """Return a low-confidence output when parsing fails.

        Args:
            node_name: Node name.
            error: Error description.

        Returns:
            AnalystOutput with low confidence and error note.
        """
        resource = f"node/{node_name}"
        return AnalystOutput(
            analyst="node",
            findings=[
                Finding(
                    id=f"node-fallback-{uuid.uuid4().hex[:8]}",
                    severity="warning",
                    type="node-issue",
                    resource=resource,
                    symptom="AI analysis could not parse response",
                    root_cause=f"Analysis error: {error}",
                    evidence=[],
                    confidence=0.1,
                )
            ],
            root_cause=None,
            confidence=0.1,
            evidence=[],
            remediation=[],
            uncertainty=[f"AI response parsing failed: {error}"],
        )
