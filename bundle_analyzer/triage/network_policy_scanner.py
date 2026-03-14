"""Network policy scanner -- detects network policy misconfigurations.

Examines NetworkPolicy objects to find deny-all policies, orphaned policies
whose label selectors match no pods, and namespaces with no network policies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import NetworkPolicyIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


class NetworkPolicyScanner:
    """Scans for network policy misconfigurations.

    Detects deny-all ingress/egress policies, orphaned policies with
    selectors matching no pods, and namespaces running without any
    network policies defined.
    """

    async def scan(self, index: "BundleIndex") -> list[NetworkPolicyIssue]:
        """Scan all network policies for issues.

        Args:
            index: The bundle index providing access to bundle data.

        Returns:
            A list of NetworkPolicyIssue objects for every problem found.
        """
        issues: list[NetworkPolicyIssue] = []

        # Build a map of namespace -> list of pod labels for orphan detection
        pod_labels_by_ns = self._build_pod_labels_map(index)

        # Parse network policies
        policies_by_ns = self._scan_network_policies(index, pod_labels_by_ns, issues)

        # Check for namespaces with pods but no network policies
        self._check_namespaces_without_policies(index, policies_by_ns, issues)

        logger.info("NetworkPolicyScanner found {} issues", len(issues))
        return issues

    def _build_pod_labels_map(
        self, index: "BundleIndex",
    ) -> dict[str, list[dict[str, str]]]:
        """Build a mapping of namespace to list of pod label dicts.

        Args:
            index: The bundle index.

        Returns:
            Dict mapping namespace to list of label dicts from pods in that namespace.
        """
        pod_labels: dict[str, list[dict[str, str]]] = {}

        try:
            for pod in index.get_all_pods():
                metadata = pod.get("metadata", {})
                namespace = metadata.get("namespace", "default")
                labels = metadata.get("labels", {})
                if namespace not in pod_labels:
                    pod_labels[namespace] = []
                pod_labels[namespace].append(labels)
        except Exception as exc:
            logger.warning("Failed to enumerate pods for network policy scan: {}", exc)

        return pod_labels

    def _scan_network_policies(
        self,
        index: "BundleIndex",
        pod_labels_by_ns: dict[str, list[dict[str, str]]],
        issues: list[NetworkPolicyIssue],
    ) -> dict[str, list[str]]:
        """Parse network policy files and detect issues.

        Args:
            index: The bundle index.
            pod_labels_by_ns: Mapping of namespace to pod label sets.
            issues: List to append findings to.

        Returns:
            Dict mapping namespace to list of policy names found.
        """
        policies_by_ns: dict[str, list[str]] = {}

        np_dir = index.root / "cluster-resources" / "network-policy"
        if not np_dir.is_dir():
            # Try alternative path
            np_dir = index.root / "cluster-resources" / "network-policies"
            if not np_dir.is_dir():
                return policies_by_ns

        for np_file in sorted(np_dir.glob("*.json")):
            namespace = np_file.stem
            try:
                data = index.read_json(str(np_file.relative_to(index.root)))
                if data is None:
                    continue
                self._parse_policies(
                    namespace, data, pod_labels_by_ns, policies_by_ns, issues,
                )
            except (ValueError, TypeError, KeyError) as exc:
                logger.warning(
                    "Error parsing network policies for namespace {}: {}",
                    namespace, exc,
                )

        return policies_by_ns

    def _parse_policies(
        self,
        namespace: str,
        data: dict | list,
        pod_labels_by_ns: dict[str, list[dict[str, str]]],
        policies_by_ns: dict[str, list[str]],
        issues: list[NetworkPolicyIssue],
    ) -> None:
        """Parse network policy JSON and detect misconfigurations.

        Args:
            namespace: The namespace these policies belong to.
            data: Parsed JSON data.
            pod_labels_by_ns: Pod labels for orphan detection.
            policies_by_ns: Accumulator for policies per namespace.
            issues: List to append findings to.
        """
        items: list[dict] = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if "items" in data:
                raw_items = data["items"]
                items = raw_items if isinstance(raw_items, list) else []
            elif "metadata" in data:
                items = [data]

        if namespace not in policies_by_ns:
            policies_by_ns[namespace] = []

        for policy in items:
            if not isinstance(policy, dict):
                continue

            policy_name = policy.get("metadata", {}).get("name", "unknown")
            policies_by_ns[namespace].append(policy_name)

            spec = policy.get("spec", {})
            policy_types = spec.get("policyTypes", [])
            pod_selector = spec.get("podSelector", {})
            ingress_rules = spec.get("ingress")
            egress_rules = spec.get("egress")

            # Detect deny-all ingress: policyTypes includes Ingress but
            # ingress rules list is empty or None
            if "Ingress" in policy_types and not ingress_rules:
                # Check if ingress key exists but is empty list vs not present
                if ingress_rules is not None or "ingress" not in spec:
                    affected = self._find_affected_pods(
                        namespace, pod_selector, pod_labels_by_ns,
                    )
                    issues.append(NetworkPolicyIssue(
                        namespace=namespace,
                        policy_name=policy_name,
                        issue_type="deny_all_ingress",
                        affected_pods=affected,
                        message=(
                            f"NetworkPolicy '{policy_name}' in namespace '{namespace}' "
                            f"denies all ingress traffic. "
                            f"Affected pods: {len(affected)}."
                        ),
                        severity="warning",
                    ))

            # Detect deny-all egress: policyTypes includes Egress but
            # egress rules list is empty or None
            if "Egress" in policy_types and not egress_rules:
                if egress_rules is not None or "egress" not in spec:
                    affected = self._find_affected_pods(
                        namespace, pod_selector, pod_labels_by_ns,
                    )
                    issues.append(NetworkPolicyIssue(
                        namespace=namespace,
                        policy_name=policy_name,
                        issue_type="deny_all_egress",
                        affected_pods=affected,
                        message=(
                            f"NetworkPolicy '{policy_name}' in namespace '{namespace}' "
                            f"denies all egress traffic. Pods cannot make outbound "
                            f"connections. Affected pods: {len(affected)}."
                        ),
                        severity="warning",
                    ))

            # Detect orphaned policies: selector matches no pods
            match_labels = pod_selector.get("matchLabels", {})
            if match_labels:
                affected = self._find_affected_pods(
                    namespace, pod_selector, pod_labels_by_ns,
                )
                if not affected:
                    issues.append(NetworkPolicyIssue(
                        namespace=namespace,
                        policy_name=policy_name,
                        issue_type="orphaned_policy",
                        affected_pods=[],
                        message=(
                            f"NetworkPolicy '{policy_name}' in namespace '{namespace}' "
                            f"has a podSelector ({match_labels}) that matches no "
                            f"existing pods. This policy has no effect."
                        ),
                        severity="info",
                    ))

    def _find_affected_pods(
        self,
        namespace: str,
        pod_selector: dict,
        pod_labels_by_ns: dict[str, list[dict[str, str]]],
    ) -> list[str]:
        """Find pods matching a network policy's podSelector.

        Args:
            namespace: The namespace to search in.
            pod_selector: The podSelector from the network policy spec.
            pod_labels_by_ns: Mapping of namespace to pod label sets.

        Returns:
            List of pod names (or label descriptions) that match the selector.
        """
        match_labels = pod_selector.get("matchLabels", {})
        ns_pods = pod_labels_by_ns.get(namespace, [])

        if not match_labels:
            # Empty selector matches all pods in the namespace
            return [f"all-pods-in-{namespace} ({len(ns_pods)} pods)"] if ns_pods else []

        matched: list[str] = []
        for pod_labels in ns_pods:
            if all(pod_labels.get(k) == v for k, v in match_labels.items()):
                # Build a descriptive name from labels
                app_name = (
                    pod_labels.get("app")
                    or pod_labels.get("app.kubernetes.io/name")
                    or pod_labels.get("name")
                    or str(match_labels)
                )
                if app_name not in matched:
                    matched.append(app_name)

        return matched

    def _check_namespaces_without_policies(
        self,
        index: "BundleIndex",
        policies_by_ns: dict[str, list[str]],
        issues: list[NetworkPolicyIssue],
    ) -> None:
        """Flag namespaces with pods but no network policies.

        Args:
            index: The bundle index.
            policies_by_ns: Mapping of namespace to policy names.
            issues: List to append findings to.
        """
        system_namespaces = frozenset({
            "kube-system", "kube-public", "kube-node-lease",
            "local-path-storage",
        })

        pods_dir = index.root / "cluster-resources" / "pods"
        if not pods_dir.is_dir():
            return

        for ns_dir in sorted(pods_dir.iterdir()):
            if not ns_dir.is_dir():
                continue
            namespace = ns_dir.name
            if namespace in system_namespaces:
                continue

            pod_files = list(ns_dir.glob("*.json"))
            if pod_files and namespace not in policies_by_ns:
                issues.append(NetworkPolicyIssue(
                    namespace=namespace,
                    policy_name="(none)",
                    issue_type="no_policies",
                    affected_pods=[],
                    message=(
                        f"Namespace '{namespace}' has {len(pod_files)} pod(s) "
                        f"but no NetworkPolicies defined. All network traffic "
                        f"is unrestricted."
                    ),
                    severity="info",
                ))
