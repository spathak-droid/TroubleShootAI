"""Quota scanner -- detects resource quota and limit range issues.

Examines ResourceQuota and LimitRange objects across namespaces to find
quotas that are exceeded or near their limits, limit range conflicts,
and namespaces with pods but no quotas defined.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import QuotaIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


def _parse_quantity(value: str | int | float) -> float:
    """Parse a Kubernetes resource quantity to a float in base units.

    Handles CPU (cores/millicores) and memory (bytes with suffixes).

    Args:
        value: The raw quantity string or number.

    Returns:
        Numeric value in base units (cores for CPU, bytes for memory).
    """
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return 0.0

    # CPU millicores
    if s.endswith("m"):
        return float(s[:-1]) / 1000.0

    # Memory suffixes
    multipliers = {
        "Ki": 1024,
        "Mi": 1024 ** 2,
        "Gi": 1024 ** 3,
        "Ti": 1024 ** 4,
        "Pi": 1024 ** 5,
        "k": 1000,
        "M": 1000 ** 2,
        "G": 1000 ** 3,
        "T": 1000 ** 4,
        "P": 1000 ** 5,
    }
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if s.endswith(suffix):
            return float(s[: -len(suffix)]) * mult

    return float(s)


class QuotaScanner:
    """Scans for resource quota and limit range issues.

    Detects quotas that are exceeded, near their limits (>80% usage),
    limit range conflicts, and namespaces running pods without quotas.
    """

    async def scan(self, index: "BundleIndex") -> list[QuotaIssue]:
        """Scan all resource quotas and limit ranges for issues.

        Args:
            index: The bundle index providing access to bundle data.

        Returns:
            A list of QuotaIssue objects for every quota problem found.
        """
        issues: list[QuotaIssue] = []

        self._scan_resource_quotas(index, issues)
        self._scan_limit_ranges(index, issues)
        self._check_namespaces_without_quotas(index, issues)

        logger.info("QuotaScanner found {} issues", len(issues))
        return issues

    def _scan_resource_quotas(
        self, index: "BundleIndex", issues: list[QuotaIssue],
    ) -> None:
        """Parse resource quota files and check usage against limits.

        Args:
            index: The bundle index.
            issues: List to append findings to.
        """
        quota_dir = index.root / "cluster-resources" / "resource-quota"
        if not quota_dir.is_dir():
            # Try alternative path
            quota_dir = index.root / "cluster-resources" / "resource-quotas"
            if not quota_dir.is_dir():
                return

        for quota_file in sorted(quota_dir.glob("*.json")):
            namespace = quota_file.stem
            try:
                data = index.read_json(str(quota_file.relative_to(index.root)))
                if data is None:
                    continue
                self._parse_quota_data(namespace, data, issues)
            except (ValueError, TypeError, KeyError) as exc:
                logger.warning(
                    "Error parsing resource quota for namespace {}: {}",
                    namespace, exc,
                )

    def _parse_quota_data(
        self,
        namespace: str,
        data: dict | list,
        issues: list[QuotaIssue],
    ) -> None:
        """Parse resource quota JSON data and detect issues.

        Args:
            namespace: The namespace this quota belongs to.
            data: Parsed JSON data.
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

        for quota in items:
            if not isinstance(quota, dict):
                continue

            quota_name = quota.get("metadata", {}).get("name", "unknown")
            status = quota.get("status", {})
            hard = status.get("hard", {})
            used = status.get("used", {})

            if not hard:
                # Fallback to spec.hard if status is empty
                hard = quota.get("spec", {}).get("hard", {})

            for resource_key, limit_str in hard.items():
                used_str = used.get(resource_key, "0")
                try:
                    limit_val = _parse_quantity(limit_str)
                    used_val = _parse_quantity(used_str)
                except (ValueError, TypeError):
                    continue

                if limit_val <= 0:
                    continue

                usage_pct = (used_val / limit_val) * 100

                # Determine resource type category
                resource_type = self._categorize_resource(resource_key)

                quota_source = f"cluster-resources/resource-quota/{namespace}.json"

                if used_val > limit_val:
                    issues.append(QuotaIssue(
                        namespace=namespace,
                        resource_name=quota_name,
                        issue_type="quota_exceeded",
                        resource_type=resource_type,
                        current_usage=str(used_str),
                        limit=str(limit_str),
                        message=(
                            f"Quota '{quota_name}' in namespace '{namespace}' "
                            f"has exceeded its {resource_key} limit: "
                            f"using {used_str} of {limit_str} ({usage_pct:.0f}%)."
                        ),
                        severity="critical",
                        source_file=quota_source,
                        evidence_excerpt=f"status.used.{resource_key}={used_str}, status.hard.{resource_key}={limit_str}",
                    ))
                elif usage_pct >= 80:
                    issues.append(QuotaIssue(
                        namespace=namespace,
                        resource_name=quota_name,
                        issue_type="quota_near_limit",
                        resource_type=resource_type,
                        current_usage=str(used_str),
                        limit=str(limit_str),
                        message=(
                            f"Quota '{quota_name}' in namespace '{namespace}' "
                            f"is near its {resource_key} limit: "
                            f"using {used_str} of {limit_str} ({usage_pct:.0f}%)."
                        ),
                        severity="warning",
                        source_file=quota_source,
                        evidence_excerpt=f"status.used.{resource_key}={used_str}, status.hard.{resource_key}={limit_str}, usage={usage_pct:.0f}%",
                    ))

    def _scan_limit_ranges(
        self, index: "BundleIndex", issues: list[QuotaIssue],
    ) -> None:
        """Parse limit range files and check for conflicts.

        Args:
            index: The bundle index.
            issues: List to append findings to.
        """
        lr_dir = index.root / "cluster-resources" / "limitranges"
        if not lr_dir.is_dir():
            # Try alternative path
            lr_dir = index.root / "cluster-resources" / "limit-ranges"
            if not lr_dir.is_dir():
                return

        for lr_file in sorted(lr_dir.glob("*.json")):
            namespace = lr_file.stem
            try:
                data = index.read_json(str(lr_file.relative_to(index.root)))
                if data is None:
                    continue
                self._parse_limit_range_data(namespace, data, issues)
            except (ValueError, TypeError, KeyError) as exc:
                logger.warning(
                    "Error parsing limit ranges for namespace {}: {}",
                    namespace, exc,
                )

    def _parse_limit_range_data(
        self,
        namespace: str,
        data: dict | list,
        issues: list[QuotaIssue],
    ) -> None:
        """Parse limit range JSON data and detect conflicts.

        Checks for cases where default limits are lower than default requests,
        or where min exceeds max.

        Args:
            namespace: The namespace this limit range belongs to.
            data: Parsed JSON data.
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

        for lr in items:
            if not isinstance(lr, dict):
                continue

            lr_name = lr.get("metadata", {}).get("name", "unknown")
            spec = lr.get("spec", {})
            limits = spec.get("limits", [])

            for limit_entry in limits:
                if not isinstance(limit_entry, dict):
                    continue

                limit_type = limit_entry.get("type", "Container")
                min_vals = limit_entry.get("min", {})
                max_vals = limit_entry.get("max", {})
                default_vals = limit_entry.get("default", {})
                default_req = limit_entry.get("defaultRequest", {})

                # Check min > max conflict
                for resource_key in set(list(min_vals.keys()) + list(max_vals.keys())):
                    if resource_key in min_vals and resource_key in max_vals:
                        try:
                            min_v = _parse_quantity(min_vals[resource_key])
                            max_v = _parse_quantity(max_vals[resource_key])
                            if min_v > max_v:
                                lr_source = f"cluster-resources/limitranges/{namespace}.json"
                                issues.append(QuotaIssue(
                                    namespace=namespace,
                                    resource_name=lr_name,
                                    issue_type="limit_range_conflict",
                                    resource_type=self._categorize_resource(resource_key),
                                    current_usage=str(min_vals[resource_key]),
                                    limit=str(max_vals[resource_key]),
                                    message=(
                                        f"LimitRange '{lr_name}' in namespace '{namespace}' "
                                        f"has {resource_key} min ({min_vals[resource_key]}) "
                                        f"greater than max ({max_vals[resource_key]}) "
                                        f"for type '{limit_type}'."
                                    ),
                                    severity="critical",
                                    source_file=lr_source,
                                    evidence_excerpt=f"min.{resource_key}={min_vals[resource_key]}, max.{resource_key}={max_vals[resource_key]}",
                                ))
                        except (ValueError, TypeError):
                            continue

                # Check default limit < default request conflict
                for resource_key in set(list(default_vals.keys()) + list(default_req.keys())):
                    if resource_key in default_vals and resource_key in default_req:
                        try:
                            limit_v = _parse_quantity(default_vals[resource_key])
                            req_v = _parse_quantity(default_req[resource_key])
                            if limit_v < req_v:
                                lr_source = f"cluster-resources/limitranges/{namespace}.json"
                                issues.append(QuotaIssue(
                                    namespace=namespace,
                                    resource_name=lr_name,
                                    issue_type="limit_range_conflict",
                                    resource_type=self._categorize_resource(resource_key),
                                    current_usage=str(default_req[resource_key]),
                                    limit=str(default_vals[resource_key]),
                                    message=(
                                        f"LimitRange '{lr_name}' in namespace '{namespace}' "
                                        f"has {resource_key} default limit ({default_vals[resource_key]}) "
                                        f"less than default request ({default_req[resource_key]}) "
                                        f"for type '{limit_type}'."
                                    ),
                                    severity="warning",
                                    source_file=lr_source,
                                    evidence_excerpt=f"default.{resource_key}={default_vals[resource_key]}, defaultRequest.{resource_key}={default_req[resource_key]}",
                                ))
                        except (ValueError, TypeError):
                            continue

    def _check_namespaces_without_quotas(
        self, index: "BundleIndex", issues: list[QuotaIssue],
    ) -> None:
        """Flag namespaces that have pods but no resource quotas.

        Args:
            index: The bundle index.
            issues: List to append findings to.
        """
        # Collect namespaces that have quotas
        namespaces_with_quotas: set[str] = set()
        for quota_dir_name in ("resource-quota", "resource-quotas"):
            quota_dir = index.root / "cluster-resources" / quota_dir_name
            if quota_dir.is_dir():
                for f in quota_dir.glob("*.json"):
                    namespaces_with_quotas.add(f.stem)

        # System namespaces to skip
        system_namespaces = frozenset({
            "kube-system", "kube-public", "kube-node-lease",
            "local-path-storage", "default",
        })

        # Check which namespaces have pods but no quotas
        pods_dir = index.root / "cluster-resources" / "pods"
        if not pods_dir.is_dir():
            return

        for ns_dir in sorted(pods_dir.iterdir()):
            if not ns_dir.is_dir():
                continue
            namespace = ns_dir.name
            if namespace in system_namespaces:
                continue
            if namespace not in namespaces_with_quotas:
                # Verify there are actually pod files
                pod_files = list(ns_dir.glob("*.json"))
                if pod_files:
                    issues.append(QuotaIssue(
                        namespace=namespace,
                        resource_name="(none)",
                        issue_type="no_quota",
                        resource_type="all",
                        message=(
                            f"Namespace '{namespace}' has {len(pod_files)} pod(s) "
                            f"but no ResourceQuota defined. Workloads can consume "
                            f"unbounded resources."
                        ),
                        severity="info",
                        source_file=f"cluster-resources/pods/{namespace}/",
                        evidence_excerpt=f"{len(pod_files)} pods in namespace, no ResourceQuota found",
                    ))

    @staticmethod
    def _categorize_resource(resource_key: str) -> str:
        """Categorize a Kubernetes resource quantity key.

        Args:
            resource_key: The resource key (e.g. "requests.cpu", "limits.memory", "pods").

        Returns:
            A simplified category string.
        """
        key_lower = resource_key.lower()
        if "cpu" in key_lower:
            return "cpu"
        if "memory" in key_lower or "mem" in key_lower:
            return "memory"
        if "pod" in key_lower:
            return "pods"
        if "service" in key_lower:
            return "services"
        if "storage" in key_lower or "pvc" in key_lower:
            return "storage"
        if "gpu" in key_lower:
            return "gpu"
        return resource_key
