"""Deployment scanner — detects replica mismatches, stuck rollouts, and update failures.

Compares desired vs available replicas, checks rollout conditions,
and identifies deployments that are not converging.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import DeploymentIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


class DeploymentScanner:
    """Scans deployments for replica mismatches and stuck rollouts.

    Compares spec.replicas against status.readyReplicas and checks for
    multiple ReplicaSets indicating a stuck rollout.
    """

    async def scan(self, index: BundleIndex) -> list[DeploymentIssue]:
        """Scan all deployments and return detected issues.

        Args:
            index: The bundle index providing access to deployment and replicaset data.

        Returns:
            A list of DeploymentIssue objects for every problematic deployment found.
        """
        issues: list[DeploymentIssue] = []

        namespaces = self._get_namespaces(index)
        replicaset_owners = self._build_replicaset_owner_map(index, namespaces)

        for ns in namespaces:
            deployments = self._read_deployments(index, ns)
            for deploy in deployments:
                try:
                    issue = self._check_deployment(deploy, ns, replicaset_owners)
                    if issue is not None:
                        issues.append(issue)
                except Exception as exc:
                    name = deploy.get("metadata", {}).get("name", "<unknown>")
                    logger.warning("Error scanning deployment {}/{}: {}", ns, name, exc)

        logger.info("DeploymentScanner found {} issues", len(issues))
        return issues

    def _get_namespaces(self, index: BundleIndex) -> list[str]:
        """Get list of namespaces from the index."""
        if hasattr(index, "namespaces"):
            return index.namespaces or []
        return []

    def _read_deployments(self, index: BundleIndex, namespace: str) -> list[dict]:
        """Read deployments for a namespace."""
        try:
            data = index.read_json(f"cluster-resources/deployments/{namespace}.json")
            if data is None:
                # Try alternate path
                data = index.read_json(f"{namespace}/deployments.json")
            if data is None:
                return []
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "items" in data:
                return data["items"] or []
            return []
        except Exception as exc:
            logger.debug("Could not read deployments for {}: {}", namespace, exc)
            return []

    def _build_replicaset_owner_map(
        self,
        index: BundleIndex,
        namespaces: list[str],
    ) -> dict[str, list[str]]:
        """Build a map of deployment -> list of active replicaset names.

        Used to detect stuck rollouts (multiple active ReplicaSets for one deployment).
        Key format: 'namespace/deployment-name'.
        """
        owner_map: dict[str, list[str]] = {}

        for ns in namespaces:
            replicasets = self._read_replicasets(index, ns)
            for rs in replicasets:
                metadata = rs.get("metadata", {})
                rs_name = metadata.get("name", "")
                status = rs.get("status", {})
                replicas = status.get("replicas", 0)

                # Skip inactive replicasets
                if replicas == 0:
                    continue

                # Find owning deployment
                owner_refs = metadata.get("ownerReferences", [])
                for ref in owner_refs:
                    if ref.get("kind") == "Deployment":
                        key = f"{ns}/{ref.get('name', '')}"
                        owner_map.setdefault(key, []).append(rs_name)

        return owner_map

    def _read_replicasets(self, index: BundleIndex, namespace: str) -> list[dict]:
        """Read replicasets for a namespace."""
        try:
            data = index.read_json(f"cluster-resources/replicasets/{namespace}.json")
            if data is None:
                data = index.read_json(f"{namespace}/replicasets.json")
            if data is None:
                return []
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "items" in data:
                return data["items"] or []
            return []
        except Exception as exc:
            logger.debug("Could not read replicasets for {}: {}", namespace, exc)
            return []

    def _check_deployment(
        self,
        deploy: dict,
        namespace: str,
        replicaset_owners: dict[str, list[str]],
    ) -> DeploymentIssue | None:
        """Check a single deployment for issues."""
        metadata = deploy.get("metadata", {})
        spec = deploy.get("spec", {})
        status = deploy.get("status", {})
        name = metadata.get("name", "unknown")
        ns = metadata.get("namespace", namespace)

        desired = spec.get("replicas", 1)
        ready = status.get("readyReplicas", 0) or 0
        available = status.get("availableReplicas", 0) or 0

        # Check for stuck rollout
        key = f"{ns}/{name}"
        active_rs = replicaset_owners.get(key, [])
        stuck_rollout = len(active_rs) > 1

        if ready < desired or stuck_rollout:
            issue_msg = f"{ready}/{desired} replicas ready"
            if stuck_rollout:
                issue_msg += f" (stuck rollout: {len(active_rs)} active ReplicaSets)"
            return DeploymentIssue(
                namespace=ns,
                name=name,
                desired_replicas=desired,
                ready_replicas=ready,
                issue=issue_msg,
                stuck_rollout=stuck_rollout,
                confidence=0.9 if stuck_rollout else 0.8,
                source_file=f"cluster-resources/deployments/{ns}.json",
                evidence_excerpt=f"spec.replicas={desired}, status.readyReplicas={ready}, status.availableReplicas={available}",
            )

        return None
