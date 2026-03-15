"""Pod analyst — analyzes pod issues using logs, exit codes, and events.

Receives pod-related triage findings and performs deep analysis
using Claude to identify root causes and recommend fixes.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.ai.prompts.pod import POD_SYSTEM_PROMPT, build_pod_user_prompt
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.security.scrubber import BundleScrubber
from bundle_analyzer.models import (
    AnalystOutput,
    Evidence,
    Finding,
    Fix,
)


class PodAnalyst:
    """Analyzes pod failures using Claude for root-cause determination.

    Gathers pod JSON, container logs (current and previous), exit codes,
    warning events, and node conditions, then asks Claude to determine
    the root cause with supporting evidence.
    """

    MAX_RETRIES: int = 3
    _scrubber: BundleScrubber = BundleScrubber()

    async def analyze(
        self,
        client: BundleAnalyzerClient,
        pod_data: dict[str, Any],
        index: BundleIndex,
        context_injector: Any | None = None,
    ) -> AnalystOutput:
        """Run AI analysis on a single pod.

        Args:
            client: The AI client to use for completions.
            pod_data: Parsed pod JSON (spec + status).
            index: Bundle index for reading logs and related data.
            context_injector: Optional ISV context injector.

        Returns:
            AnalystOutput with findings, root cause, evidence, and fixes.
        """
        start = time.monotonic()
        metadata = pod_data.get("metadata", {})
        pod_name = metadata.get("name", "unknown")
        namespace = metadata.get("namespace", "default")
        node_name = pod_data.get("spec", {}).get("nodeName")

        logger.debug("PodAnalyst: analyzing {}/{}", namespace, pod_name)

        # Gather context — scrub pod spec before building prompt
        scrubbed_pod, _ = self._scrubber.scrub_pod_json(pod_data)
        pod_json_str = json.dumps(scrubbed_pod, indent=2, default=str)

        # Container logs
        current_logs = self._get_current_logs(pod_data, index)
        previous_logs = self._get_previous_logs(pod_data, index)

        # Exit codes and restart counts
        exit_codes = self._get_exit_codes(pod_data)

        # Warning events for this pod
        events = self._get_pod_events(namespace, pod_name, index)

        # Node conditions
        node_conditions = self._get_node_conditions(node_name, index)

        user_prompt = build_pod_user_prompt(
            pod_json=pod_json_str,
            current_logs=current_logs,
            previous_logs=previous_logs,
            exit_codes=exit_codes,
            events=events,
            node_conditions=node_conditions,
        )

        # Call Claude with retries
        for attempt in range(self.MAX_RETRIES):
            try:
                system_prompt = POD_SYSTEM_PROMPT
                if context_injector is not None:
                    system_prompt = context_injector.inject(system_prompt)
                raw_response = await client.complete(
                    system=system_prompt,
                    user=user_prompt,
                )
                result = self._parse_response(raw_response, namespace, pod_name)
                elapsed = time.monotonic() - start
                logger.debug(
                    "PodAnalyst: {}/{} completed in {:.2f}s",
                    namespace, pod_name, elapsed,
                )
                return result

            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning(
                    "PodAnalyst: parse error on attempt {}/{} for {}/{}: {}",
                    attempt + 1, self.MAX_RETRIES, namespace, pod_name, exc,
                )
                if attempt == self.MAX_RETRIES - 1:
                    return self._fallback_output(namespace, pod_name, str(exc))

        # Should not reach here, but satisfy type checker
        return self._fallback_output(namespace, pod_name, "all retries exhausted")

    def _get_current_logs(
        self, pod_data: dict[str, Any], index: BundleIndex
    ) -> str | None:
        """Retrieve last 200 lines of current container logs."""
        containers = self._get_container_names(pod_data)
        namespace = pod_data.get("metadata", {}).get("namespace", "default")
        pod_name = pod_data.get("metadata", {}).get("name", "unknown")

        all_logs: list[str] = []
        for container in containers:
            lines = list(
                index.stream_log(namespace, pod_name, container, previous=False, last_n_lines=200)
            )
            if lines:
                all_logs.append(f"--- Container: {container} ---")
                all_logs.extend(lines)

        return "\n".join(all_logs) if all_logs else None

    def _get_previous_logs(
        self, pod_data: dict[str, Any], index: BundleIndex
    ) -> str | None:
        """Retrieve last 100 lines of previous container logs (pre-crash)."""
        containers = self._get_container_names(pod_data)
        namespace = pod_data.get("metadata", {}).get("namespace", "default")
        pod_name = pod_data.get("metadata", {}).get("name", "unknown")

        all_logs: list[str] = []
        for container in containers:
            lines = list(
                index.stream_log(
                    namespace, pod_name, container,
                    previous=True, last_n_lines=100,
                )
            )
            if lines:
                all_logs.append(f"--- Container (previous): {container} ---")
                all_logs.extend(lines)

        return "\n".join(all_logs) if all_logs else None

    def _get_exit_codes(self, pod_data: dict[str, Any]) -> str | None:
        """Extract exit codes and restart counts from container statuses."""
        statuses = pod_data.get("status", {}).get("containerStatuses", [])
        init_statuses = pod_data.get("status", {}).get("initContainerStatuses", [])

        lines: list[str] = []
        for cs in statuses + init_statuses:
            name = cs.get("name", "?")
            restarts = cs.get("restartCount", 0)
            state = cs.get("state", {})
            last_state = cs.get("lastState", {})

            exit_code = None
            reason = None
            for s in (state, last_state):
                terminated = s.get("terminated", {})
                if terminated:
                    exit_code = terminated.get("exitCode")
                    reason = terminated.get("reason")
                    break

            line = f"  {name}: restarts={restarts}"
            if exit_code is not None:
                line += f", exitCode={exit_code}"
            if reason:
                line += f", reason={reason}"
            lines.append(line)

        return "\n".join(lines) if lines else None

    def _get_pod_events(
        self, namespace: str, pod_name: str, index: BundleIndex
    ) -> str | None:
        """Get warning events related to this pod."""
        events = index.get_events(namespace=namespace)
        pod_events: list[str] = []
        for ev in events:
            obj = ev.get("involvedObject", {})
            if (
                obj.get("kind") == "Pod"
                and obj.get("name") == pod_name
                and ev.get("type") == "Warning"
            ):
                ts = ev.get("lastTimestamp", ev.get("metadata", {}).get("creationTimestamp", "?"))
                reason = ev.get("reason", "?")
                msg = ev.get("message", "")
                count = ev.get("count", 1)
                pod_events.append(f"[{ts}] {reason} (x{count}): {msg}")

        return "\n".join(pod_events) if pod_events else None

    def _get_node_conditions(
        self, node_name: str | None, index: BundleIndex
    ) -> str | None:
        """Get conditions of the node this pod is scheduled on."""
        if not node_name or not index.has("nodes"):
            return None

        node_data = index.read_json(f"cluster-resources/nodes/{node_name}.json")
        if node_data is None:
            return None

        conditions = node_data.get("status", {}).get("conditions", [])  # type: ignore[union-attr]
        if not conditions:
            return None

        lines: list[str] = []
        for cond in conditions:
            lines.append(
                f"  {cond.get('type')}: {cond.get('status')} "
                f"(reason={cond.get('reason', '?')}, "
                f"transition={cond.get('lastTransitionTime', '?')})"
            )
        return "\n".join(lines)

    @staticmethod
    def _get_container_names(pod_data: dict[str, Any]) -> list[str]:
        """Extract all container names from a pod spec."""
        names: list[str] = []
        for c in pod_data.get("spec", {}).get("initContainers", []):
            names.append(c.get("name", "init"))
        for c in pod_data.get("spec", {}).get("containers", []):
            names.append(c.get("name", "main"))
        return names

    def _parse_response(
        self, raw: str, namespace: str, pod_name: str
    ) -> AnalystOutput:
        """Parse Claude's JSON response into an AnalystOutput.

        Args:
            raw: Raw text response from Claude (should be JSON).
            namespace: Pod namespace for building resource identifiers.
            pod_name: Pod name for building resource identifiers.

        Returns:
            Structured AnalystOutput.

        Raises:
            json.JSONDecodeError: If response is not valid JSON.
            KeyError: If required fields are missing.
        """
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]  # remove opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        data = json.loads(cleaned)

        resource = f"pod/{namespace}/{pod_name}"
        confidence_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
        confidence = confidence_map.get(data.get("confidence", "low"), 0.3)

        finding = Finding(
            id=f"pod-{uuid.uuid4().hex[:8]}",
            severity="critical" if confidence >= 0.6 else "warning",
            type="pod-failure",
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
            analyst="pod",
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
    def _fallback_output(namespace: str, pod_name: str, error: str) -> AnalystOutput:
        """Return a low-confidence output when parsing fails.

        Args:
            namespace: Pod namespace.
            pod_name: Pod name.
            error: Error description.

        Returns:
            AnalystOutput with low confidence and error note.
        """
        resource = f"pod/{namespace}/{pod_name}"
        return AnalystOutput(
            analyst="pod",
            findings=[
                Finding(
                    id=f"pod-fallback-{uuid.uuid4().hex[:8]}",
                    severity="warning",
                    type="pod-failure",
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
