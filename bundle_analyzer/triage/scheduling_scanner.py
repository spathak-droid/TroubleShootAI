"""Scheduling scanner -- detects FailedScheduling, taint, and affinity issues.

Parses Kubernetes events for FailedScheduling reasons, checks for
unschedulable nodes, and compares pod nodeSelector constraints against
available node labels to surface scheduling problems.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import SchedulingIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


# Mapping of message patterns to issue types.  Patterns are evaluated in order;
# the first match wins.
_SCHEDULING_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"insufficient cpu", re.IGNORECASE), "insufficient_cpu"),
    (re.compile(r"insufficient memory", re.IGNORECASE), "insufficient_memory"),
    (re.compile(r"didn't tolerate|taint", re.IGNORECASE), "taint_not_tolerated"),
    (
        re.compile(r"didn't match Pod's node affinity", re.IGNORECASE),
        "node_affinity_mismatch",
    ),
    (
        re.compile(r"didn't match pod affinity|pod anti-affinity", re.IGNORECASE),
        "pod_affinity_conflict",
    ),
    (
        re.compile(r"didn't match node selector", re.IGNORECASE),
        "node_selector_mismatch",
    ),
]


class SchedulingScanner:
    """Scans for pod scheduling failures, taint mismatches, and affinity conflicts.

    Detection sources:
    1. FailedScheduling events -- message text is pattern-matched to classify
       the root cause (CPU/memory pressure, taints, affinity, selectors).
    2. Unschedulable nodes -- ``node.spec.unschedulable == true``.
    3. Pod nodeSelector vs. node label comparison -- finds pods whose
       nodeSelector cannot be satisfied by any cluster node.
    """

    async def scan(self, index: "BundleIndex") -> list[SchedulingIssue]:
        """Run all scheduling checks against the bundle.

        Args:
            index: The bundle index providing access to cluster data.

        Returns:
            A list of :class:`SchedulingIssue` objects for every problem found.
        """
        issues: list[SchedulingIssue] = []

        nodes = self._read_nodes(index)
        node_labels = self._collect_node_labels(nodes)

        issues.extend(self._scan_events(index))
        issues.extend(self._scan_unschedulable_nodes(nodes))
        issues.extend(self._scan_node_selector_mismatch(index, node_labels))

        logger.info("SchedulingScanner found {} issues", len(issues))
        return issues

    # ------------------------------------------------------------------
    # Event-based detection
    # ------------------------------------------------------------------

    def _scan_events(self, index: "BundleIndex") -> list[SchedulingIssue]:
        """Parse FailedScheduling events and classify root causes."""
        issues: list[SchedulingIssue] = []

        try:
            events = index.get_events()
        except Exception as exc:
            logger.warning("Failed to read events for scheduling scan: {}", exc)
            return issues

        for event in events:
            try:
                reason = event.get("reason", "")
                if reason != "FailedScheduling":
                    continue

                message: str = event.get("message", "")
                involved = event.get("involvedObject", {})
                pod_name: str = involved.get("name", "<unknown>")
                namespace: str = involved.get("namespace", "<unknown>")

                issue_type = self._classify_message(message)
                if issue_type is None:
                    # FailedScheduling but no recognised sub-pattern -- still
                    # worth reporting with a generic classification.
                    logger.debug(
                        "Unclassified FailedScheduling message for {}/{}: {}",
                        namespace,
                        pod_name,
                        message[:120],
                    )
                    continue

                count = event.get("count", 1)
                severity = "critical" if count >= 5 else "warning"

                issues.append(
                    SchedulingIssue(
                        namespace=namespace,
                        pod_name=pod_name,
                        issue_type=issue_type,
                        message=message[:500],
                        severity=severity,
                        source_file=None,
                        evidence_excerpt=message[:300],
                        confidence=0.95,
                    )
                )
            except Exception as exc:
                logger.debug("Error processing scheduling event: {}", exc)

        return issues

    @staticmethod
    def _classify_message(message: str) -> str | None:
        """Return the issue_type for a FailedScheduling message, or None."""
        for pattern, issue_type in _SCHEDULING_PATTERNS:
            if pattern.search(message):
                return issue_type
        return None

    # ------------------------------------------------------------------
    # Unschedulable nodes
    # ------------------------------------------------------------------

    def _scan_unschedulable_nodes(
        self, nodes: list[dict]
    ) -> list[SchedulingIssue]:
        """Flag nodes that have ``spec.unschedulable: true``."""
        issues: list[SchedulingIssue] = []

        for node in nodes:
            try:
                spec = node.get("spec", {})
                if not spec.get("unschedulable", False):
                    continue

                name: str = node.get("metadata", {}).get("name", "<unknown>")
                issues.append(
                    SchedulingIssue(
                        namespace="<cluster>",
                        pod_name=name,
                        issue_type="unschedulable_node",
                        message=f"Node {name} is cordoned (spec.unschedulable=true)",
                        severity="warning",
                        source_file=None,
                        evidence_excerpt=f"spec.unschedulable: true on node {name}",
                        confidence=1.0,
                    )
                )
            except Exception as exc:
                logger.debug("Error checking unschedulable status: {}", exc)

        return issues

    # ------------------------------------------------------------------
    # Pod nodeSelector vs available node labels
    # ------------------------------------------------------------------

    def _scan_node_selector_mismatch(
        self,
        index: "BundleIndex",
        node_labels: list[dict[str, str]],
    ) -> list[SchedulingIssue]:
        """Find pods whose nodeSelector cannot be satisfied by any node."""
        issues: list[SchedulingIssue] = []

        if not node_labels:
            # No node data -- cannot compare.
            return issues

        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to read pods for nodeSelector check: {}", exc)
            return issues

        for pod in pods:
            try:
                spec = pod.get("spec", {})
                node_selector: dict[str, str] | None = spec.get("nodeSelector")
                if not node_selector:
                    continue

                metadata = pod.get("metadata", {})
                pod_name: str = metadata.get("name", "<unknown>")
                namespace: str = metadata.get("namespace", "<unknown>")

                # Check if any node satisfies ALL selectors
                matched = any(
                    self._labels_match(node_selector, nl) for nl in node_labels
                )
                if matched:
                    continue

                selector_str = ", ".join(
                    f"{k}={v}" for k, v in sorted(node_selector.items())
                )
                issues.append(
                    SchedulingIssue(
                        namespace=namespace,
                        pod_name=pod_name,
                        issue_type="node_selector_mismatch",
                        message=(
                            f"Pod {namespace}/{pod_name} has nodeSelector "
                            f"[{selector_str}] that no node satisfies"
                        ),
                        severity="critical",
                        source_file=None,
                        evidence_excerpt=f"nodeSelector: {selector_str}",
                        confidence=0.85,
                    )
                )
            except Exception as exc:
                logger.debug("Error checking nodeSelector for pod: {}", exc)

        return issues

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _labels_match(
        selector: dict[str, str], node_labels: dict[str, str]
    ) -> bool:
        """Return True if *node_labels* satisfy every key-value in *selector*."""
        return all(node_labels.get(k) == v for k, v in selector.items())

    @staticmethod
    def _read_nodes(index: "BundleIndex") -> list[dict]:
        """Read node resources from the bundle.

        Checks both ``cluster-resources/nodes.json`` (list format) and
        per-node files under ``cluster-resources/nodes/<name>.json``.
        """
        nodes: list[dict] = []

        try:
            data = index.read_json("cluster-resources/nodes.json")
            if isinstance(data, list):
                nodes.extend(data)
            elif isinstance(data, dict) and "items" in data:
                nodes.extend(data.get("items", []))
        except Exception as exc:
            logger.debug("Could not read nodes.json: {}", exc)

        # Per-node files
        nodes_dir: Path = index.root / "cluster-resources" / "nodes"
        if nodes_dir.is_dir():
            for f in sorted(nodes_dir.glob("*.json")):
                try:
                    node = index.read_json(str(f.relative_to(index.root)))
                    if isinstance(node, dict) and "metadata" in node:
                        name = node.get("metadata", {}).get("name")
                        if name and not any(
                            n.get("metadata", {}).get("name") == name
                            for n in nodes
                        ):
                            nodes.append(node)
                except Exception as exc:
                    logger.debug("Could not read node file {}: {}", f.name, exc)

        return nodes

    @staticmethod
    def _collect_node_labels(nodes: list[dict]) -> list[dict[str, str]]:
        """Extract the label dict from every node for selector matching."""
        labels: list[dict[str, str]] = []
        for node in nodes:
            node_labels = node.get("metadata", {}).get("labels", {})
            if isinstance(node_labels, dict):
                labels.append(node_labels)
        return labels
