"""Cross-Pod Anomaly Detector -- compares failing pods against healthy siblings.

Identifies configuration and placement differences between failing and healthy
pods within the same owner group (Deployment, ReplicaSet, StatefulSet). When a
pod is crashing but its siblings are fine, the difference is often the root cause.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Literal

from loguru import logger
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex
    from bundle_analyzer.models import TriageResult


class PodAnomaly(BaseModel):
    """A detected anomaly between failing and healthy pods."""

    failing_pod: str  # namespace/pod_name
    comparison_group: str  # what was compared (e.g. "app=nginx replicas")
    anomaly_type: Literal[
        "node_placement",
        "image_version",
        "resource_limits",
        "env_config",
        "labels_annotations",
        "restart_pattern",
    ]
    description: str  # human readable description
    failing_value: str  # what the failing pod has
    healthy_value: str  # what healthy pods have
    severity: Literal["critical", "warning", "info"] = "warning"
    suggestion: str = ""  # what to do about it


class AnomalyDetector:
    """Compares failing pods against healthy siblings to surface anomalies.

    Groups pods by owner reference (Deployment/ReplicaSet/StatefulSet) and
    runs a battery of comparisons between failing and healthy members of each
    group. Differences in node placement, image versions, resource limits,
    environment variables, and restart counts are flagged as potential causes.
    """

    async def scan(
        self,
        index: "BundleIndex",
        triage: "TriageResult",
    ) -> list[PodAnomaly]:
        """Scan for cross-pod anomalies between failing and healthy pods.

        Args:
            index: The bundle index providing access to pod data.
            triage: Triage results identifying which pods are failing.

        Returns:
            A list of PodAnomaly objects describing detected differences.
        """
        anomalies: list[PodAnomaly] = []

        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods for anomaly detection: {}", exc)
            return anomalies

        if not pods:
            logger.debug("No pods found in bundle; skipping anomaly detection")
            return anomalies

        # Build the set of failing pod identifiers (namespace/name)
        failing_pod_ids = self._build_failing_set(triage)
        if not failing_pod_ids:
            logger.debug("No failing pods in triage results; skipping anomaly detection")
            return anomalies

        # Group pods by owner reference
        groups = self._group_pods_by_owner(pods)

        for group_name, group_pods in groups.items():
            failing_in_group = [
                p for p in group_pods
                if self._pod_id(p) in failing_pod_ids
            ]
            healthy_in_group = [
                p for p in group_pods
                if self._pod_id(p) not in failing_pod_ids
            ]

            # Need at least one failing and one healthy to compare
            if not failing_in_group or not healthy_in_group:
                continue

            for failing_pod in failing_in_group:
                pod_id = self._pod_id(failing_pod)
                try:
                    pod_anomalies = self._compare_pods(
                        failing_pod, healthy_in_group, pod_id, group_name,
                    )
                    anomalies.extend(pod_anomalies)
                except Exception as exc:
                    logger.warning(
                        "Error comparing pod {} against group {}: {}",
                        pod_id, group_name, exc,
                    )

        logger.info(
            "AnomalyDetector found {} anomalies across {} pod groups",
            len(anomalies),
            len(groups),
        )
        return anomalies

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pod_id(pod: dict) -> str:
        """Return a canonical namespace/name identifier for a pod."""
        metadata = pod.get("metadata", {})
        ns = metadata.get("namespace", "default")
        name = metadata.get("name", "unknown")
        return f"{ns}/{name}"

    @staticmethod
    def _build_failing_set(triage: "TriageResult") -> set[str]:
        """Extract the set of failing pod IDs from triage results."""
        failing: set[str] = set()
        for issue in triage.critical_pods + triage.warning_pods:
            failing.add(f"{issue.namespace}/{issue.pod_name}")
        return failing

    @staticmethod
    def _group_pods_by_owner(pods: list[dict]) -> dict[str, list[dict]]:
        """Group pods by their first ownerReference name.

        Pods controlled by the same Deployment/ReplicaSet/StatefulSet are
        placed in the same group, making them comparable siblings.

        Args:
            pods: List of raw pod JSON dicts.

        Returns:
            Mapping of owner key to list of pod dicts. Pods without an
            ownerReference are excluded (standalone pods are not comparable).
        """
        groups: dict[str, list[dict]] = defaultdict(list)

        for pod in pods:
            metadata = pod.get("metadata", {})
            ns = metadata.get("namespace", "default")
            owner_refs = metadata.get("ownerReferences", [])

            if not owner_refs:
                continue

            owner = owner_refs[0]
            owner_kind = owner.get("kind", "Unknown")
            owner_name = owner.get("name", "unknown")
            group_key = f"{ns}/{owner_kind}/{owner_name}"
            groups[group_key].append(pod)

        return dict(groups)

    def _compare_pods(
        self,
        failing: dict,
        healthy: list[dict],
        pod_id: str,
        group: str,
    ) -> list[PodAnomaly]:
        """Run all comparison checks between a failing pod and healthy siblings.

        Args:
            failing: The failing pod's raw JSON dict.
            healthy: List of healthy pod JSON dicts from the same group.
            pod_id: Canonical identifier for the failing pod.
            group: Name of the comparison group (owner reference key).

        Returns:
            List of detected anomalies for this failing pod.
        """
        anomalies: list[PodAnomaly] = []
        anomalies.extend(self._compare_nodes(failing, healthy, pod_id, group))
        anomalies.extend(self._compare_images(failing, healthy, pod_id, group))
        anomalies.extend(self._compare_resources(failing, healthy, pod_id, group))
        anomalies.extend(self._compare_env_vars(failing, healthy, pod_id, group))
        anomalies.extend(self._compare_restart_counts(failing, healthy, pod_id, group))
        return anomalies

    @staticmethod
    def _compare_nodes(
        failing: dict,
        healthy: list[dict],
        pod_id: str,
        group: str,
    ) -> list[PodAnomaly]:
        """Check whether the failing pod is on a different node than healthy pods.

        A pod landing on a unique node while all healthy siblings share another
        node (or set of nodes) may indicate a node-specific issue such as
        resource exhaustion, taint, or hardware fault.

        Args:
            failing: Failing pod dict.
            healthy: Healthy pod dicts.
            pod_id: Canonical pod identifier.
            group: Comparison group name.

        Returns:
            List of node-placement anomalies (0 or 1 items).
        """
        failing_node = failing.get("spec", {}).get("nodeName")
        if not failing_node:
            return []

        healthy_nodes = {
            p.get("spec", {}).get("nodeName")
            for p in healthy
            if p.get("spec", {}).get("nodeName")
        }

        if not healthy_nodes:
            return []

        # Only flag if the failing pod is on a node that NO healthy pod uses
        if failing_node not in healthy_nodes:
            healthy_str = ", ".join(sorted(healthy_nodes))
            return [PodAnomaly(
                failing_pod=pod_id,
                comparison_group=group,
                anomaly_type="node_placement",
                description=(
                    f"Failing pod is on node '{failing_node}' while all "
                    f"healthy siblings are on: {healthy_str}"
                ),
                failing_value=failing_node,
                healthy_value=healthy_str,
                severity="warning",
                suggestion=(
                    "Investigate node-specific issues: check node conditions, "
                    "resource pressure, taints, and hardware health for "
                    f"node '{failing_node}'."
                ),
            )]

        return []

    @staticmethod
    def _compare_images(
        failing: dict,
        healthy: list[dict],
        pod_id: str,
        group: str,
    ) -> list[PodAnomaly]:
        """Check whether the failing pod has different container image versions.

        A mismatched image tag within the same ReplicaSet often indicates a
        stuck or partial rollout.

        Args:
            failing: Failing pod dict.
            healthy: Healthy pod dicts.
            pod_id: Canonical pod identifier.
            group: Comparison group name.

        Returns:
            List of image-version anomalies.
        """
        anomalies: list[PodAnomaly] = []
        failing_containers = failing.get("spec", {}).get("containers", [])

        for container in failing_containers:
            container_name = container.get("name", "unknown")
            failing_image = container.get("image", "")
            if not failing_image:
                continue

            # Collect the same container's image from all healthy pods
            healthy_images: set[str] = set()
            for hp in healthy:
                for hc in hp.get("spec", {}).get("containers", []):
                    if hc.get("name") == container_name:
                        img = hc.get("image", "")
                        if img:
                            healthy_images.add(img)

            if not healthy_images:
                continue

            if failing_image not in healthy_images:
                healthy_str = ", ".join(sorted(healthy_images))
                severity: Literal["critical", "warning", "info"] = "critical"
                anomalies.append(PodAnomaly(
                    failing_pod=pod_id,
                    comparison_group=group,
                    anomaly_type="image_version",
                    description=(
                        f"Container '{container_name}' in failing pod uses "
                        f"image '{failing_image}' but healthy siblings use: "
                        f"{healthy_str}"
                    ),
                    failing_value=failing_image,
                    healthy_value=healthy_str,
                    severity=severity,
                    suggestion=(
                        "This may indicate a stuck rollout or broken image. "
                        "Check deployment rollout status and image pull errors."
                    ),
                ))

        return anomalies

    @staticmethod
    def _compare_resources(
        failing: dict,
        healthy: list[dict],
        pod_id: str,
        group: str,
    ) -> list[PodAnomaly]:
        """Check whether the failing pod has different resource limits or requests.

        Different resource configurations within the same owner group may
        explain why one pod is OOMKilled or throttled while siblings are fine.

        Args:
            failing: Failing pod dict.
            healthy: Healthy pod dicts.
            pod_id: Canonical pod identifier.
            group: Comparison group name.

        Returns:
            List of resource-limits anomalies.
        """
        anomalies: list[PodAnomaly] = []
        failing_containers = failing.get("spec", {}).get("containers", [])

        for container in failing_containers:
            container_name = container.get("name", "unknown")
            failing_resources = container.get("resources", {})
            failing_limits = failing_resources.get("limits", {})
            failing_requests = failing_resources.get("requests", {})

            for hp in healthy:
                for hc in hp.get("spec", {}).get("containers", []):
                    if hc.get("name") != container_name:
                        continue

                    healthy_resources = hc.get("resources", {})
                    healthy_limits = healthy_resources.get("limits", {})
                    healthy_requests = healthy_resources.get("requests", {})

                    # Compare limits
                    if failing_limits != healthy_limits:
                        anomalies.append(PodAnomaly(
                            failing_pod=pod_id,
                            comparison_group=group,
                            anomaly_type="resource_limits",
                            description=(
                                f"Container '{container_name}' has different "
                                f"resource limits than healthy siblings"
                            ),
                            failing_value=str(failing_limits) if failing_limits else "(none)",
                            healthy_value=str(healthy_limits) if healthy_limits else "(none)",
                            severity="warning",
                            suggestion=(
                                "Ensure all pods in the same group have "
                                "consistent resource limits to avoid unexpected "
                                "OOM kills or CPU throttling."
                            ),
                        ))
                        # Only report once per container (first healthy mismatch)
                        break

                    # Compare requests
                    if failing_requests != healthy_requests:
                        anomalies.append(PodAnomaly(
                            failing_pod=pod_id,
                            comparison_group=group,
                            anomaly_type="resource_limits",
                            description=(
                                f"Container '{container_name}' has different "
                                f"resource requests than healthy siblings"
                            ),
                            failing_value=str(failing_requests) if failing_requests else "(none)",
                            healthy_value=str(healthy_requests) if healthy_requests else "(none)",
                            severity="info",
                            suggestion=(
                                "Different resource requests may affect "
                                "scheduling and QoS class."
                            ),
                        ))
                        break

        return anomalies

    @staticmethod
    def _compare_env_vars(
        failing: dict,
        healthy: list[dict],
        pod_id: str,
        group: str,
    ) -> list[PodAnomaly]:
        """Check whether the failing pod has different environment variable names.

        Only compares env var NAMES for security -- values are never examined
        or logged. A missing or extra env var often indicates a broken
        ConfigMap/Secret mount or incomplete rollout.

        Args:
            failing: Failing pod dict.
            healthy: Healthy pod dicts.
            pod_id: Canonical pod identifier.
            group: Comparison group name.

        Returns:
            List of env-config anomalies.
        """
        anomalies: list[PodAnomaly] = []
        failing_containers = failing.get("spec", {}).get("containers", [])

        for container in failing_containers:
            container_name = container.get("name", "unknown")
            failing_env_names = {
                e.get("name", "")
                for e in container.get("env", [])
                if e.get("name")
            }

            for hp in healthy:
                for hc in hp.get("spec", {}).get("containers", []):
                    if hc.get("name") != container_name:
                        continue

                    healthy_env_names = {
                        e.get("name", "")
                        for e in hc.get("env", [])
                        if e.get("name")
                    }

                    if not failing_env_names and not healthy_env_names:
                        continue

                    extra = failing_env_names - healthy_env_names
                    missing = healthy_env_names - failing_env_names

                    if extra or missing:
                        parts: list[str] = []
                        if missing:
                            parts.append(
                                f"missing: {', '.join(sorted(missing))}"
                            )
                        if extra:
                            parts.append(
                                f"extra: {', '.join(sorted(extra))}"
                            )
                        diff_str = "; ".join(parts)

                        anomalies.append(PodAnomaly(
                            failing_pod=pod_id,
                            comparison_group=group,
                            anomaly_type="env_config",
                            description=(
                                f"Container '{container_name}' has different "
                                f"env var names than healthy siblings ({diff_str})"
                            ),
                            failing_value=", ".join(sorted(failing_env_names)) or "(none)",
                            healthy_value=", ".join(sorted(healthy_env_names)) or "(none)",
                            severity="warning",
                            suggestion=(
                                "Check ConfigMap and Secret references. "
                                "Missing env vars may cause the application "
                                "to fail on startup."
                            ),
                        ))
                        # Only report once per container
                        break

        return anomalies

    @staticmethod
    def _compare_restart_counts(
        failing: dict,
        healthy: list[dict],
        pod_id: str,
        group: str,
    ) -> list[PodAnomaly]:
        """Check whether the failing pod has significantly more restarts.

        A restart count much higher than siblings indicates a persistent
        issue affecting only this pod replica.

        Args:
            failing: Failing pod dict.
            healthy: Healthy pod dicts.
            pod_id: Canonical pod identifier.
            group: Comparison group name.

        Returns:
            List of restart-pattern anomalies.
        """
        anomalies: list[PodAnomaly] = []

        failing_restarts = 0
        for cs in failing.get("status", {}).get("containerStatuses", []):
            failing_restarts += cs.get("restartCount", 0)

        healthy_restarts: list[int] = []
        for hp in healthy:
            total = 0
            for cs in hp.get("status", {}).get("containerStatuses", []):
                total += cs.get("restartCount", 0)
            healthy_restarts.append(total)

        if not healthy_restarts:
            return anomalies

        avg_healthy = sum(healthy_restarts) / len(healthy_restarts)
        max_healthy = max(healthy_restarts)

        # Flag if failing pod has 3x the average or at least 5 more than max
        if failing_restarts > max(avg_healthy * 3, max_healthy + 5):
            severity: Literal["critical", "warning", "info"] = (
                "critical" if failing_restarts > 10 else "warning"
            )
            anomalies.append(PodAnomaly(
                failing_pod=pod_id,
                comparison_group=group,
                anomaly_type="restart_pattern",
                description=(
                    f"Failing pod has {failing_restarts} restarts while "
                    f"healthy siblings average {avg_healthy:.0f} "
                    f"(max {max_healthy})"
                ),
                failing_value=str(failing_restarts),
                healthy_value=f"avg={avg_healthy:.0f}, max={max_healthy}",
                severity=severity,
                suggestion=(
                    "This pod is restarting far more than its siblings. "
                    "Check pod-specific factors: node issues, volume mounts, "
                    "or configuration differences."
                ),
            ))

        return anomalies
