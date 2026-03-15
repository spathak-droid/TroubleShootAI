"""Triage engine that orchestrates all scanners and produces a TriageResult.

Runs each scanner in parallel using asyncio.gather, collects findings,
and returns a complete TriageResult for downstream AI analysis.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import TriageResult
from bundle_analyzer.triage.anomaly_detector import AnomalyDetector
from bundle_analyzer.triage.change_correlator import ChangeCorrelator
from bundle_analyzer.triage.config_scanner import ConfigScanner
from bundle_analyzer.triage.coverage_analyzer import CoverageAnalyzer
from bundle_analyzer.triage.crashloop_analyzer import CrashLoopAnalyzer
from bundle_analyzer.triage.dependency_scanner import DependencyScanner
from bundle_analyzer.triage.deployment_scanner import DeploymentScanner
from bundle_analyzer.triage.dns_scanner import DNSScanner
from bundle_analyzer.triage.drift_scanner import DriftScanner
from bundle_analyzer.triage.event_scanner import EventScanner
from bundle_analyzer.triage.ingress_scanner import IngressScanner
from bundle_analyzer.triage.log_intelligence import LogIntelligenceEngine
from bundle_analyzer.triage.network_policy_scanner import NetworkPolicyScanner
from bundle_analyzer.triage.node_scanner import NodeScanner
from bundle_analyzer.triage.pod_scanner import PodScanner
from bundle_analyzer.triage.probe_scanner import ProbeScanner
from bundle_analyzer.triage.quota_scanner import QuotaScanner
from bundle_analyzer.triage.rbac_scanner import RBACScanner
from bundle_analyzer.triage.resource_scanner import ResourceScanner
from bundle_analyzer.triage.scheduling_scanner import SchedulingScanner
from bundle_analyzer.triage.silence_scanner import SilenceScanner
from bundle_analyzer.triage.storage_scanner import StorageScanner
from bundle_analyzer.triage.tls_scanner import TLSScanner
from bundle_analyzer.triage.troubleshoot_scanner import TroubleshootAnalyzerScanner

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex

# Issue types considered critical (placed in critical_pods rather than warning_pods)
_CRITICAL_TYPES = frozenset({
    "CrashLoopBackOff",
    "OOMKilled",
    "CreateContainerConfigError",
})


class TriageEngine:
    """Orchestrates all triage scanners and aggregates results.

    Runs PodScanner, NodeScanner, DeploymentScanner, EventScanner,
    ConfigScanner, DriftScanner, SilenceScanner, ProbeScanner,
    ResourceScanner, IngressScanner, StorageScanner, RBACScanner,
    QuotaScanner, NetworkPolicyScanner, and CrashLoopAnalyzer in
    parallel, then combines their outputs into a single TriageResult.
    """

    def __init__(self) -> None:
        """Initialize the triage engine with all scanner instances."""
        self.pod_scanner = PodScanner()
        self.node_scanner = NodeScanner()
        self.deployment_scanner = DeploymentScanner()
        self.event_scanner = EventScanner()
        self.config_scanner = ConfigScanner()
        self.drift_scanner = DriftScanner()
        self.silence_scanner = SilenceScanner()
        self.probe_scanner = ProbeScanner()
        self.resource_scanner = ResourceScanner()
        self.ingress_scanner = IngressScanner()
        self.storage_scanner = StorageScanner()
        self.rbac_scanner = RBACScanner()
        self.quota_scanner = QuotaScanner()
        self.network_policy_scanner = NetworkPolicyScanner()
        self.crashloop_analyzer = CrashLoopAnalyzer()
        self.dns_scanner = DNSScanner()
        self.tls_scanner = TLSScanner()
        self.scheduling_scanner = SchedulingScanner()
        self.troubleshoot_scanner = TroubleshootAnalyzerScanner()
        self.coverage_analyzer = CoverageAnalyzer()
        self.anomaly_detector = AnomalyDetector()
        self.dependency_scanner = DependencyScanner()
        self.change_correlator = ChangeCorrelator()
        self.log_intelligence_engine = LogIntelligenceEngine()

    async def run(self, index: BundleIndex) -> TriageResult:
        """Run all scanners in parallel and aggregate results.

        Args:
            index: The bundle index providing access to all bundle data.

        Returns:
            A TriageResult containing all findings from every scanner.
        """
        logger.info("Starting triage engine with all 18 scanners")

        # Run all scanners in parallel
        results = await asyncio.gather(
            self.pod_scanner.scan(index),
            self.node_scanner.scan(index),
            self.deployment_scanner.scan(index),
            self.event_scanner.scan(index),
            self.config_scanner.scan(index),
            self.drift_scanner.scan(index),
            self.silence_scanner.scan(index),
            self.probe_scanner.scan(index),
            self.resource_scanner.scan(index),
            self.ingress_scanner.scan(index),
            self.storage_scanner.scan(index),
            self.rbac_scanner.scan(index),
            self.quota_scanner.scan(index),
            self.network_policy_scanner.scan(index),
            self.crashloop_analyzer.scan(index),
            self.dns_scanner.scan(index),
            self.tls_scanner.scan(index),
            self.scheduling_scanner.scan(index),
            return_exceptions=True,
        )

        # Unpack results, handling any exceptions
        pod_issues = self._safe_result(results[0], "PodScanner", [])
        node_issues = self._safe_result(results[1], "NodeScanner", [])
        deployment_issues = self._safe_result(results[2], "DeploymentScanner", [])
        warning_events = self._safe_result(results[3], "EventScanner", [])
        event_escalations = self.event_scanner.detect_escalations(warning_events)
        config_issues = self._safe_result(results[4], "ConfigScanner", [])
        drift_issues = self._safe_result(results[5], "DriftScanner", [])
        silence_signals = self._safe_result(results[6], "SilenceScanner", [])
        probe_issues = self._safe_result(results[7], "ProbeScanner", [])
        resource_issues = self._safe_result(results[8], "ResourceScanner", [])
        ingress_issues = self._safe_result(results[9], "IngressScanner", [])
        storage_issues = self._safe_result(results[10], "StorageScanner", [])
        rbac_issues = self._safe_result(results[11], "RBACScanner", [])
        quota_issues = self._safe_result(results[12], "QuotaScanner", [])
        network_policy_issues = self._safe_result(results[13], "NetworkPolicyScanner", [])
        crash_contexts = self._safe_result(results[14], "CrashLoopAnalyzer", [])
        dns_issues = self._safe_result(results[15], "DNSScanner", [])
        tls_issues = self._safe_result(results[16], "TLSScanner", [])
        scheduling_issues = self._safe_result(results[17], "SchedulingScanner", [])

        # Separate pod issues into critical and warning
        critical_pods = [p for p in pod_issues if p.issue_type in _CRITICAL_TYPES]
        warning_pods = [p for p in pod_issues if p.issue_type not in _CRITICAL_TYPES]

        # Read existing analysis from the bundle itself (if present)
        existing_analysis: list[dict] = []
        try:
            if hasattr(index, "read_existing_analysis"):
                existing_analysis = index.read_existing_analysis() or []
        except Exception as exc:
            logger.debug("Could not read existing analysis: {}", exc)

        # Collect RBAC errors
        rbac_errors: list[str] = []
        if hasattr(index, "rbac_errors"):
            rbac_errors = index.rbac_errors or []

        result = TriageResult(
            critical_pods=critical_pods,
            warning_pods=warning_pods,
            node_issues=node_issues,
            deployment_issues=deployment_issues,
            config_issues=config_issues,
            drift_issues=drift_issues,
            silence_signals=silence_signals,
            warning_events=warning_events,
            existing_analysis=existing_analysis,
            rbac_errors=rbac_errors,
            probe_issues=probe_issues,
            resource_issues=resource_issues,
            ingress_issues=ingress_issues,
            storage_issues=storage_issues,
            rbac_issues=rbac_issues,
            quota_issues=quota_issues,
            network_policy_issues=network_policy_issues,
            dns_issues=dns_issues,
            tls_issues=tls_issues,
            scheduling_issues=scheduling_issues,
            crash_contexts=crash_contexts,
            event_escalations=event_escalations,
        )

        # Phase 2: Run TroubleshootAnalyzerScanner with Phase 1 results for dedup
        try:
            ts_analysis, preflight, ext_issues = await self.troubleshoot_scanner.scan(
                index, result
            )
            result.troubleshoot_analysis = ts_analysis
            result.preflight_report = preflight
            result.external_analyzer_issues = ext_issues
        except Exception as exc:
            logger.warning("Troubleshoot scanner failed: {}", exc)

        # Phase 3: Coverage gap analysis
        try:
            coverage_gaps = await self.coverage_analyzer.scan(index)
            result.coverage_gaps = coverage_gaps
        except Exception as exc:
            logger.warning("Coverage analyzer failed: {}", exc)

        # Phase 4: Advanced analyzers (need triage result as input)
        try:
            anomalies = await self.anomaly_detector.scan(index, result)
            result.pod_anomalies = anomalies
        except Exception as exc:
            logger.warning("Anomaly detector failed: {}", exc)

        try:
            dep_map = await self.dependency_scanner.scan(index)
            result.dependency_map = dep_map
        except Exception as exc:
            logger.warning("Dependency scanner failed: {}", exc)

        try:
            change_report = await self.change_correlator.scan(index, result)
            result.change_report = change_report
        except Exception as exc:
            logger.warning("Change correlator failed: {}", exc)

        # Phase 5: Log intelligence — deep scan of logs for pods with issues
        try:
            pods_of_interest = self._collect_pods_of_interest(
                index, critical_pods, warning_pods, crash_contexts,
            )
            if pods_of_interest:
                log_intel = await self.log_intelligence_engine.scan(index, pods_of_interest)
                result.log_intelligence = log_intel
                logger.info("Log intelligence: scanned {} pod(s)", len(log_intel))
        except Exception as exc:
            logger.warning("Log intelligence engine failed: {}", exc)

        total = (
            len(critical_pods) + len(warning_pods) + len(node_issues)
            + len(deployment_issues) + len(config_issues) + len(drift_issues)
            + len(silence_signals) + len(warning_events)
            + len(probe_issues) + len(resource_issues) + len(ingress_issues)
            + len(storage_issues) + len(event_escalations)
            + len(rbac_issues) + len(quota_issues) + len(network_policy_issues)
            + len(crash_contexts) + len(dns_issues) + len(tls_issues)
            + len(scheduling_issues)
        )
        logger.info(
            "Triage complete: {} total findings "
            "({} critical pods, {} warning pods, {} node, {} deployment, "
            "{} config, {} drift, {} silence, {} events, {} escalations, "
            "{} probe, {} resource, {} ingress, {} storage, "
            "{} rbac, {} quota, {} network policy, {} crash contexts, "
            "{} dns, {} tls, {} scheduling)",
            total,
            len(critical_pods),
            len(warning_pods),
            len(node_issues),
            len(deployment_issues),
            len(config_issues),
            len(drift_issues),
            len(silence_signals),
            len(warning_events),
            len(event_escalations),
            len(probe_issues),
            len(resource_issues),
            len(ingress_issues),
            len(storage_issues),
            len(rbac_issues),
            len(quota_issues),
            len(network_policy_issues),
            len(crash_contexts),
            len(dns_issues),
            len(tls_issues),
            len(scheduling_issues),
        )

        return result

    @staticmethod
    def _collect_pods_of_interest(
        index: BundleIndex,
        critical_pods: list,
        warning_pods: list,
        crash_contexts: list,
    ) -> list[dict]:
        """Collect pod JSON dicts for pods that have known issues.

        Only these pods get the full log intelligence scan (not all pods),
        keeping runtime bounded.
        """
        # Gather unique namespace/name pairs
        pod_keys: set[tuple[str, str]] = set()
        for issue in critical_pods + warning_pods:
            pod_keys.add((issue.namespace, issue.pod_name))
        for ctx in crash_contexts:
            pod_keys.add((ctx.namespace, ctx.pod_name))

        if not pod_keys:
            return []

        pods: list[dict] = []
        try:
            for pod in index.get_all_pods():
                md = pod.get("metadata", {})
                ns = md.get("namespace", "default")
                name = md.get("name", "unknown")
                if (ns, name) in pod_keys:
                    pods.append(pod)
        except Exception:
            pass
        return pods

    def _safe_result(self, result: object, scanner_name: str, default: list) -> list:
        """Extract a scanner result, logging and returning default if it raised."""
        if isinstance(result, BaseException):
            logger.error("{} failed with exception: {}", scanner_name, result)
            return default
        return result  # type: ignore[return-value]
