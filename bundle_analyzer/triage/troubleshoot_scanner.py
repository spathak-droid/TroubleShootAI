"""Scanner that integrates troubleshoot.sh analyzer and preflight results.

Runs AFTER the 15 native scanners so it can deduplicate against existing
findings and only surface gap-fill issues that our scanners don't cover.
Also detects contradictions where troubleshoot.sh says PASS but native
scanners found issues, or vice versa.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.bundle.troubleshoot_parser import TroubleshootParser
from bundle_analyzer.models import (
    ExternalAnalyzerIssue,
    PreflightReport,
    TriageResult,
    TroubleshootAnalysis,
    TroubleshootAnalyzerResult,
)

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex

# Mapping: troubleshoot.sh analyzer type -> our native scanner category
_OVERLAP_MAP: dict[str, str] = {
    "deploymentStatus": "deployment",
    "statefulsetStatus": "deployment",
    "nodeResources": "node",
    "storageClass": "storage",
    "ingress": "ingress",
    "clusterPodStatuses": "pod",
    "clusterContainerStatuses": "pod",
    "event": "event",
}


class TroubleshootAnalyzerScanner:
    """Scanner that parses and deduplicates troubleshoot.sh analyzer results.

    Runs as Phase 2 of triage -- after all 15 native scanners have produced
    their results. For each troubleshoot.sh finding:

    - If it overlaps with a native scanner result, it is marked as
      corroboration (not duplicated).
    - If it contradicts a native scanner result (PASS vs found issues),
      it is marked with a contradiction reference.
    - If it covers an analyzer type we have no native scanner for
      (e.g. cephStatus, containerRuntime), it creates an
      ExternalAnalyzerIssue as a gap-fill.
    """

    def __init__(self) -> None:
        """Initialize with a TroubleshootParser instance."""
        self._parser = TroubleshootParser()

    async def scan(
        self,
        index: BundleIndex,
        native_results: TriageResult,
    ) -> tuple[TroubleshootAnalysis, PreflightReport | None, list[ExternalAnalyzerIssue]]:
        """Parse troubleshoot.sh results and produce typed output with dedup.

        Args:
            index: Bundle index for reading analysis.json and preflight files.
            native_results: Results from the 15 native scanners for dedup.

        Returns:
            Tuple of (analysis, preflight_report, external_issues).
        """
        # Parse analysis.json
        raw_analysis = index.read_existing_analysis()
        analysis = self._parser.parse_analysis(raw_analysis)

        # Parse preflight results
        preflight: PreflightReport | None = None
        raw_preflight = index.read_preflight_results()
        if raw_preflight:
            preflight = self._parser.parse_preflight(raw_preflight)

        # Build external issues (gap-fill + corroboration + contradiction)
        external_issues = self._build_external_issues(analysis, native_results)

        # Detect contradictions (PASS in troubleshoot but issues found natively)
        contradictions = self._detect_contradictions(analysis, native_results)
        external_issues.extend(contradictions)

        logger.info(
            "Troubleshoot scanner: {} analysis results ({} pass, {} warn, {} fail), "
            "{} preflight results, {} external issues ({} contradictions)",
            len(analysis.results),
            analysis.pass_count,
            analysis.warn_count,
            analysis.fail_count,
            len(preflight.results) if preflight else 0,
            len(external_issues),
            len(contradictions),
        )

        return analysis, preflight, external_issues

    def _build_external_issues(
        self,
        analysis: TroubleshootAnalysis,
        native_results: TriageResult,
    ) -> list[ExternalAnalyzerIssue]:
        """Build ExternalAnalyzerIssue list from non-passing results.

        For each fail/warn result:
        - Check if it overlaps with a native scanner finding
        - If overlap: mark as corroboration
        - If gap: create as new external issue

        Args:
            analysis: Parsed troubleshoot.sh analysis.
            native_results: Native scanner results for dedup.

        Returns:
            List of external analyzer issues.
        """
        issues: list[ExternalAnalyzerIssue] = []

        for result in analysis.results:
            if result.is_pass:
                continue  # Don't create issues for passing checks

            severity = self._map_severity(result)
            corroborates = self._find_corroboration(result, native_results)

            # If it corroborates a native finding, mark it but still include
            # as it provides independent validation
            if corroborates:
                issues.append(ExternalAnalyzerIssue(
                    source="troubleshoot.sh",
                    analyzer_type=result.analyzer_type,
                    name=result.name,
                    title=result.title,
                    message=result.message,
                    severity=severity,
                    uri=result.uri,
                    corroborates=corroborates,
                ))
            else:
                # Gap-fill: no native scanner covers this
                issues.append(ExternalAnalyzerIssue(
                    source="troubleshoot.sh",
                    analyzer_type=result.analyzer_type,
                    name=result.name,
                    title=result.title,
                    message=result.message,
                    severity=severity,
                    uri=result.uri,
                ))

        return issues

    def _detect_contradictions(
        self,
        analysis: TroubleshootAnalysis,
        native_results: TriageResult,
    ) -> list[ExternalAnalyzerIssue]:
        """Detect contradictions between troubleshoot.sh and native scanners.

        A contradiction occurs when:
        - Troubleshoot.sh reports PASS but our native scanner found issues
        - Troubleshoot.sh reports FAIL but our native scanner found nothing

        Args:
            analysis: Parsed troubleshoot.sh analysis.
            native_results: Native scanner results.

        Returns:
            List of ExternalAnalyzerIssue with contradicts field set.
        """
        contradictions: list[ExternalAnalyzerIssue] = []

        # Build a lookup of which analyzer types passed vs failed
        pass_types: dict[str, list[TroubleshootAnalyzerResult]] = {}
        fail_types: dict[str, list[TroubleshootAnalyzerResult]] = {}
        for result in analysis.results:
            if result.analyzer_type not in _OVERLAP_MAP:
                continue
            if result.is_pass:
                pass_types.setdefault(result.analyzer_type, []).append(result)
            elif result.is_fail or result.is_warn:
                fail_types.setdefault(result.analyzer_type, []).append(result)

        # Case 1: Troubleshoot says PASS but native found issues
        native_issue_checks: list[tuple[str, str, bool]] = [
            ("deploymentStatus", "deployment", bool(native_results.deployment_issues)),
            ("statefulsetStatus", "deployment", bool(native_results.deployment_issues)),
            ("nodeResources", "node", bool(native_results.node_issues)),
            ("storageClass", "storage", bool(native_results.storage_issues)),
            ("ingress", "ingress", bool(native_results.ingress_issues)),
            ("clusterPodStatuses", "pod", bool(native_results.critical_pods or native_results.warning_pods)),
            ("clusterContainerStatuses", "pod", bool(native_results.critical_pods or native_results.warning_pods)),
            ("event", "event", bool(native_results.warning_events)),
        ]

        for analyzer_type, native_category, has_native_issues in native_issue_checks:
            if analyzer_type in pass_types and has_native_issues:
                for result in pass_types[analyzer_type]:
                    contradictions.append(ExternalAnalyzerIssue(
                        source="troubleshoot.sh",
                        analyzer_type=result.analyzer_type,
                        name=result.name,
                        title=f"Contradiction: {result.title}",
                        message=(
                            f"Troubleshoot.sh reports PASS for '{result.name}' "
                            f"but native {native_category} scanner found issues. "
                            f"Original message: {result.message}"
                        ),
                        severity="info",
                        uri=result.uri,
                        contradicts=f"{native_category}/native-scanner-found-issues",
                    ))

        # Case 2: Troubleshoot says FAIL but native found nothing
        for analyzer_type, native_category, has_native_issues in native_issue_checks:
            if analyzer_type in fail_types and not has_native_issues:
                for result in fail_types[analyzer_type]:
                    contradictions.append(ExternalAnalyzerIssue(
                        source="troubleshoot.sh",
                        analyzer_type=result.analyzer_type,
                        name=result.name,
                        title=f"Contradiction: {result.title}",
                        message=(
                            f"Troubleshoot.sh reports {result.severity.upper()} for "
                            f"'{result.name}' but native {native_category} scanner "
                            f"found no issues. This may indicate a gap in native "
                            f"scanning or a false positive from troubleshoot.sh. "
                            f"Original message: {result.message}"
                        ),
                        severity=self._map_severity(result),
                        uri=result.uri,
                        contradicts=f"{native_category}/native-scanner-found-nothing",
                    ))

        return contradictions

    @staticmethod
    def _map_severity(result: TroubleshootAnalyzerResult) -> str:
        """Map troubleshoot.sh severity to our severity levels.

        Args:
            result: A troubleshoot.sh analyzer result.

        Returns:
            One of "critical", "warning", "info".
        """
        if result.is_fail:
            return "critical"
        if result.is_warn:
            return "warning"
        return "info"

    @staticmethod
    def _find_corroboration(
        result: TroubleshootAnalyzerResult,
        native_results: TriageResult,
    ) -> str | None:
        """Check if a troubleshoot.sh result overlaps with a native finding.

        Args:
            result: The troubleshoot.sh result to check.
            native_results: Native scanner results.

        Returns:
            A descriptive ID of the corroborated native finding, or None.
        """
        analyzer_type = result.analyzer_type
        msg_lower = result.message.lower()
        name_lower = result.name.lower()

        # deploymentStatus / statefulsetStatus -> DeploymentScanner
        if analyzer_type in ("deploymentStatus", "statefulsetStatus"):
            for dep in native_results.deployment_issues:
                if dep.name.lower() in name_lower or dep.name.lower() in msg_lower:
                    return f"deployment/{dep.namespace}/{dep.name}"
            return None

        # nodeResources -> NodeScanner
        if analyzer_type == "nodeResources":
            for node in native_results.node_issues:
                if node.node_name.lower() in name_lower or node.node_name.lower() in msg_lower:
                    return f"node/{node.node_name}"
            # Even without name match, if we have node issues it's corroboration
            if native_results.node_issues:
                return "node/any"
            return None

        # storageClass -> StorageScanner
        if analyzer_type == "storageClass":
            for sto in native_results.storage_issues:
                if sto.resource_name.lower() in name_lower or sto.resource_name.lower() in msg_lower:
                    return f"storage/{sto.namespace}/{sto.resource_name}"
            if native_results.storage_issues:
                return "storage/any"
            return None

        # ingress -> IngressScanner
        if analyzer_type == "ingress":
            for ing in native_results.ingress_issues:
                if ing.ingress_name.lower() in name_lower or ing.ingress_name.lower() in msg_lower:
                    return f"ingress/{ing.namespace}/{ing.ingress_name}"
            if native_results.ingress_issues:
                return "ingress/any"
            return None

        # clusterPodStatuses / clusterContainerStatuses -> PodScanner
        if analyzer_type in ("clusterPodStatuses", "clusterContainerStatuses"):
            all_pod_issues = list(native_results.critical_pods) + list(native_results.warning_pods)
            for pod in all_pod_issues:
                if pod.pod_name.lower() in name_lower or pod.pod_name.lower() in msg_lower:
                    return f"pod/{pod.namespace}/{pod.pod_name}"
            if all_pod_issues:
                return "pod/any"
            return None

        # event -> EventScanner
        if analyzer_type == "event":
            for evt in native_results.warning_events:
                if (
                    evt.involved_object_name.lower() in name_lower
                    or evt.involved_object_name.lower() in msg_lower
                ):
                    return f"event/{evt.namespace}/{evt.involved_object_name}"
            if native_results.warning_events:
                return "event/any"
            return None

        return None
