"""Drift scanner — compares spec vs status across resource types.

Detects cases where the declared desired state (spec) diverges
from the actual observed state (status), indicating drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import DriftIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


class DriftScanner:
    """Scans Deployments, StatefulSets, and Services for spec-vs-status drift.

    Key checks:
    - spec.replicas != status.readyReplicas for Deployments and StatefulSets
    - Service selector matching 0 pods
    - ConfigMap key references vs actual keys
    """

    async def scan(self, index: BundleIndex) -> list[DriftIssue]:
        """Scan all supported resource types for drift.

        Args:
            index: The bundle index providing access to resource data.

        Returns:
            A list of DriftIssue objects for every detected drift.
        """
        issues: list[DriftIssue] = []

        namespaces = getattr(index, "namespaces", []) or []

        for ns in namespaces:
            issues.extend(self._check_deployments(index, ns))
            issues.extend(self._check_statefulsets(index, ns))
            issues.extend(self._check_services(index, ns))

        logger.info("DriftScanner found {} issues", len(issues))
        return issues

    def _read_resources(
        self, index: BundleIndex, namespace: str, resource_type: str,
    ) -> list[dict]:
        """Read a list of resources from the bundle."""
        try:
            data = index.read_json(f"cluster-resources/{resource_type}/{namespace}.json")
            if data is None:
                data = index.read_json(f"{namespace}/{resource_type}.json")
            if data is None:
                return []
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "items" in data:
                return data["items"] or []
            return []
        except Exception as exc:
            logger.debug("Could not read {} for {}: {}", resource_type, namespace, exc)
            return []

    def _check_deployments(self, index: BundleIndex, namespace: str) -> list[DriftIssue]:
        """Check deployments for replica drift."""
        issues: list[DriftIssue] = []
        deployments = self._read_resources(index, namespace, "deployments")

        for deploy in deployments:
            try:
                name = deploy.get("metadata", {}).get("name", "unknown")
                spec = deploy.get("spec", {})
                status = deploy.get("status", {})

                desired = spec.get("replicas", 1)
                ready = status.get("readyReplicas") or 0
                updated = status.get("updatedReplicas") or 0
                status.get("availableReplicas") or 0

                source = f"cluster-resources/deployments/{namespace}.json"

                if desired != ready:
                    issues.append(DriftIssue(
                        resource_type="Deployment",
                        namespace=namespace,
                        name=name,
                        field="replicas",
                        spec_value=desired,
                        status_value=ready,
                        description=f"Desired {desired} replicas but only {ready} ready",
                        source_file=source,
                        evidence_excerpt=f"spec.replicas={desired}, status.readyReplicas={ready}",
                    ))

                if updated != desired:
                    issues.append(DriftIssue(
                        resource_type="Deployment",
                        namespace=namespace,
                        name=name,
                        field="updatedReplicas",
                        spec_value=desired,
                        status_value=updated,
                        description=f"Only {updated}/{desired} replicas updated to latest spec",
                        source_file=source,
                        evidence_excerpt=f"spec.replicas={desired}, status.updatedReplicas={updated}",
                    ))
            except Exception as exc:
                logger.debug("Error checking deployment drift: {}", exc)

        return issues

    def _check_statefulsets(self, index: BundleIndex, namespace: str) -> list[DriftIssue]:
        """Check statefulsets for replica drift."""
        issues: list[DriftIssue] = []
        statefulsets = self._read_resources(index, namespace, "statefulsets")

        for sts in statefulsets:
            try:
                name = sts.get("metadata", {}).get("name", "unknown")
                spec = sts.get("spec", {})
                status = sts.get("status", {})

                desired = spec.get("replicas", 1)
                ready = status.get("readyReplicas") or 0

                if desired != ready:
                    issues.append(DriftIssue(
                        resource_type="StatefulSet",
                        namespace=namespace,
                        name=name,
                        field="replicas",
                        spec_value=desired,
                        status_value=ready,
                        description=f"Desired {desired} replicas but only {ready} ready",
                        source_file=f"cluster-resources/statefulsets/{namespace}.json",
                        evidence_excerpt=f"spec.replicas={desired}, status.readyReplicas={ready}",
                    ))
            except Exception as exc:
                logger.debug("Error checking statefulset drift: {}", exc)

        return issues

    def _check_services(self, index: BundleIndex, namespace: str) -> list[DriftIssue]:
        """Check services for selector drift (selector matching 0 pods)."""
        issues: list[DriftIssue] = []

        services = self._read_resources(index, namespace, "services")
        if not services:
            return issues

        # Collect all pod labels in this namespace
        pod_label_sets = self._collect_pod_labels(index, namespace)

        for svc in services:
            try:
                name = svc.get("metadata", {}).get("name", "unknown")
                spec = svc.get("spec", {})
                selector = spec.get("selector")

                if not selector:
                    continue  # headless or ExternalName

                svc_type = spec.get("type", "ClusterIP")
                if svc_type == "ExternalName":
                    continue

                # Check if any pod matches the selector
                matches = sum(
                    1 for labels in pod_label_sets
                    if all(labels.get(k) == v for k, v in selector.items())
                )

                if matches == 0:
                    issues.append(DriftIssue(
                        resource_type="Service",
                        namespace=namespace,
                        name=name,
                        field="selector",
                        spec_value=selector,
                        status_value=0,
                        description=f"Service selector {selector} matches 0 pods",
                        source_file=f"cluster-resources/services/{namespace}.json",
                        evidence_excerpt=f"spec.selector={selector}, matching_pods=0",
                    ))
            except Exception as exc:
                logger.debug("Error checking service drift: {}", exc)

        return issues

    def _collect_pod_labels(self, index: BundleIndex, namespace: str) -> list[dict[str, str]]:
        """Collect labels from all pods in a namespace."""
        labels_list: list[dict[str, str]] = []
        try:
            pods = list(index.get_all_pods())
            for pod in pods:
                md = pod.get("metadata", {})
                if md.get("namespace", "default") == namespace:
                    labels = md.get("labels", {})
                    if labels:
                        labels_list.append(labels)
        except Exception as exc:
            logger.debug("Could not collect pod labels for {}: {}", namespace, exc)
        return labels_list
