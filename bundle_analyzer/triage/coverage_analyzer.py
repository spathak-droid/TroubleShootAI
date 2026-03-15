"""Analyzer that identifies areas of the bundle with no scanner coverage.

Checks which Kubernetes resource types exist in the bundle but have no
native or troubleshoot.sh scanner examining them. This helps engineers
understand what the analysis did NOT look at.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import CoverageGap

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex

# Areas covered by at least one native scanner.
_COVERED_AREAS: dict[str, str] = {
    "Pods": "PodScanner",
    "Nodes": "NodeScanner",
    "Deployments": "DeploymentScanner",
    "Events": "EventScanner",
    "ConfigMaps": "ConfigScanner",
    "Secrets": "ConfigScanner",
    "Ingress": "IngressScanner",
    "PVCs/PVs/StorageClasses": "StorageScanner",
    "ResourceQuotas": "QuotaScanner",
    "LimitRanges": "QuotaScanner",
    "NetworkPolicies": "NetworkPolicyScanner",
    "RBAC/Auth": "RBACScanner",
    "Probes": "ProbeScanner",
    "Resources (requests/limits)": "ResourceScanner",
    "Drift (spec/status)": "DriftScanner",
    "Silence (missing data)": "SilenceScanner",
    "CrashLoop analysis": "CrashLoopAnalyzer",
}

# Areas that no native scanner covers, with metadata for reporting.
_UNCOVERED_AREAS: list[dict[str, str]] = [
    {
        "area": "CronJobs",
        "data_path": "cluster-resources/cronjobs",
        "why_it_matters": "Failed or suspended CronJobs can indicate broken batch processing or certificate renewal",
        "severity": "medium",
    },
    {
        "area": "Jobs",
        "data_path": "cluster-resources/jobs",
        "why_it_matters": "Failed Jobs may indicate broken migrations, backups, or batch operations",
        "severity": "medium",
    },
    {
        "area": "DaemonSets",
        "data_path": "cluster-resources/daemonsets",
        "why_it_matters": "DaemonSet issues affect every node — missing logging, monitoring, or networking agents",
        "severity": "high",
    },
    {
        "area": "StatefulSets",
        "data_path": "cluster-resources/statefulsets",
        "why_it_matters": "StatefulSet issues can cause data loss or split-brain in databases and queues",
        "severity": "high",
    },
    {
        "area": "HorizontalPodAutoscalers",
        "data_path": "cluster-resources/horizontalpodautoscalers",
        "why_it_matters": "Misconfigured HPA can cause under-provisioning (crashes) or over-provisioning (cost)",
        "severity": "medium",
    },
    {
        "area": "PodDisruptionBudgets",
        "data_path": "cluster-resources/pod-disruption-budgets",
        "why_it_matters": "PDBs can block node drains, rollouts, and cluster upgrades",
        "severity": "medium",
    },
    {
        "area": "ServiceAccounts",
        "data_path": "cluster-resources/serviceaccounts",
        "why_it_matters": "Missing or misconfigured service accounts cause auth failures for pods",
        "severity": "medium",
    },
    {
        "area": "Endpoints/EndpointSlices",
        "data_path": "cluster-resources/endpoints",
        "why_it_matters": "Empty endpoints mean services route to nothing — silent traffic black holes",
        "severity": "high",
    },
    {
        "area": "CustomResourceDefinitions",
        "data_path": "cluster-resources/custom-resource-definitions",
        "why_it_matters": "Missing CRDs cause cascading failures in operators and controllers",
        "severity": "medium",
    },
    {
        "area": "ClusterRoles/ClusterRoleBindings",
        "data_path": "cluster-resources/clusterroles",
        "why_it_matters": "Overly permissive or missing cluster roles affect security and functionality",
        "severity": "low",
    },
    {
        "area": "Certificates",
        "data_path": "certificates",
        "why_it_matters": "Expired or misconfigured TLS certificates cause connection failures",
        "severity": "high",
    },
    {
        "area": "VolumeAttachments",
        "data_path": "cluster-resources/volumeattachments",
        "why_it_matters": "Stuck volume attachments prevent pods from starting on new nodes",
        "severity": "medium",
    },
]


class CoverageAnalyzer:
    """Identifies bundle areas that no scanner examines.

    For each known uncovered Kubernetes resource area, checks whether the
    bundle actually contains data at the expected path. Only reports gaps
    where data IS present -- there is no point flagging missing CronJobs
    if the bundle does not contain any CronJob data.
    """

    async def scan(self, index: BundleIndex) -> list[CoverageGap]:
        """Scan the bundle for coverage gaps.

        Checks each uncovered area definition against the bundle filesystem
        to determine whether data exists but goes unanalyzed.

        Args:
            index: The bundle index providing access to bundle structure.

        Returns:
            List of CoverageGap instances for areas where data is present
            but no scanner examines it.
        """
        gaps: list[CoverageGap] = []

        for area_def in _UNCOVERED_AREAS:
            data_path = area_def["data_path"]
            full_path = index.root / data_path

            # Check if the data exists -- either as a directory or a file
            data_present = full_path.is_dir() or full_path.is_file()

            # Also check with .json suffix for single-file resources
            if not data_present:
                json_path = index.root / f"{data_path}.json"
                data_present = json_path.is_file()

            if data_present:
                gaps.append(CoverageGap(
                    area=area_def["area"],
                    data_present=True,
                    data_path=data_path,
                    why_it_matters=area_def["why_it_matters"],
                    severity=area_def["severity"],  # type: ignore[arg-type]
                ))

        if gaps:
            high_count = sum(1 for g in gaps if g.severity == "high")
            logger.info(
                "Coverage analyzer: {} gaps found ({} high priority)",
                len(gaps),
                high_count,
            )
        else:
            logger.info("Coverage analyzer: no gaps found (all uncovered areas absent from bundle)")

        return gaps
