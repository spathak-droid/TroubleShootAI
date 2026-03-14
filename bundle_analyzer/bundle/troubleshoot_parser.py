"""Parser for troubleshoot.sh analysis.json and preflight results.

Converts raw list[dict] from bundle analysis into typed models,
handling format variations across troubleshoot.sh versions.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from bundle_analyzer.models import (
    PreflightCheckResult,
    PreflightReport,
    TroubleshootAnalysis,
    TroubleshootAnalyzerResult,
)


class TroubleshootParser:
    """Parses raw troubleshoot.sh analysis and preflight JSON into typed models."""

    def parse_analysis(self, raw: list[dict[str, Any]]) -> TroubleshootAnalysis:
        """Parse raw analysis.json entries into a TroubleshootAnalysis.

        Args:
            raw: List of dicts from analysis.json. Each dict represents
                 one analyzer result.

        Returns:
            Typed TroubleshootAnalysis with computed counts.
        """
        if not raw:
            return TroubleshootAnalysis()

        results: list[TroubleshootAnalyzerResult] = []
        for entry in raw:
            if not isinstance(entry, dict):
                logger.debug("Skipping non-dict analysis entry: {}", type(entry))
                continue
            try:
                result = self.parse_single_result(entry)
                results.append(result)
            except Exception as exc:
                logger.debug("Failed to parse analysis entry: {}", exc)

        pass_count = sum(1 for r in results if r.is_pass)
        warn_count = sum(1 for r in results if r.is_warn)
        fail_count = sum(1 for r in results if r.is_fail)

        return TroubleshootAnalysis(
            results=results,
            pass_count=pass_count,
            warn_count=warn_count,
            fail_count=fail_count,
            has_results=len(results) > 0,
        )

    def parse_single_result(self, raw: dict[str, Any]) -> TroubleshootAnalyzerResult:
        """Parse a single analyzer result entry.

        Handles multiple field name conventions across troubleshoot.sh versions:
        - ``isFail``/``is_fail``, ``isWarn``/``is_warn``, ``isPass``/``is_pass``
        - ``checkName``/``check_name``
        - ``URI``/``uri``

        Args:
            raw: Single analyzer result dict.

        Returns:
            Typed TroubleshootAnalyzerResult.
        """
        # Support nested "insight" structure used by newer troubleshoot.sh
        insight = raw.get("insight", {}) or {}

        name = raw.get("name", raw.get("checkName", raw.get("check_name", "")))
        check_name = raw.get("checkName", raw.get("check_name", ""))

        is_fail = bool(raw.get("isFail", raw.get("is_fail", False)))
        is_warn = bool(raw.get("isWarn", raw.get("is_warn", False)))
        is_pass = bool(raw.get("isPass", raw.get("is_pass", False)))

        # If none of the bools are set, try to infer from a "severity" or "outcome" field
        if not (is_fail or is_warn or is_pass):
            outcome = str(
                raw.get("severity", insight.get("severity", raw.get("outcome", "")))
            ).lower()
            if outcome in ("fail", "error"):
                is_fail = True
            elif outcome in ("warn", "warning"):
                is_warn = True
            elif outcome in ("debug", "info", "pass"):
                is_pass = True
            else:
                is_pass = True

        # Title: try top-level, then insight.primary
        title = raw.get("title", "") or insight.get("primary", "")
        # Message: try top-level, then insight.detail
        message = raw.get("message", "") or insight.get("detail", "")
        uri = raw.get("URI", raw.get("uri", insight.get("uri", "")))
        strict = bool(raw.get("strict", False))

        analyzer_type = self._infer_analyzer_type(raw)
        severity = self._compute_severity(is_pass, is_warn, is_fail)

        return TroubleshootAnalyzerResult(
            name=name,
            check_name=check_name,
            is_pass=is_pass,
            is_warn=is_warn,
            is_fail=is_fail,
            title=title,
            message=message,
            uri=uri,
            analyzer_type=analyzer_type,
            severity=severity,
            strict=strict,
        )

    def parse_preflight(self, raw: list[dict[str, Any]]) -> PreflightReport:
        """Parse preflight check results into a PreflightReport.

        Args:
            raw: List of dicts from preflight.json.

        Returns:
            Typed PreflightReport with computed counts.
        """
        if not raw:
            return PreflightReport()

        results: list[PreflightCheckResult] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            try:
                result = self._parse_preflight_result(entry)
                results.append(result)
            except Exception as exc:
                logger.debug("Failed to parse preflight entry: {}", exc)

        pass_count = sum(1 for r in results if r.is_pass)
        warn_count = sum(1 for r in results if r.is_warn)
        fail_count = sum(1 for r in results if r.is_fail)

        return PreflightReport(
            results=results,
            pass_count=pass_count,
            warn_count=warn_count,
            fail_count=fail_count,
        )

    def _parse_preflight_result(self, raw: dict[str, Any]) -> PreflightCheckResult:
        """Parse a single preflight check result."""
        insight = raw.get("insight", {}) or {}

        name = raw.get("name", raw.get("checkName", raw.get("check_name", "")))
        check_name = raw.get("checkName", raw.get("check_name", ""))

        is_fail = bool(raw.get("isFail", raw.get("is_fail", False)))
        is_warn = bool(raw.get("isWarn", raw.get("is_warn", False)))
        is_pass = bool(raw.get("isPass", raw.get("is_pass", False)))

        if not (is_fail or is_warn or is_pass):
            outcome = str(
                raw.get("severity", insight.get("severity", raw.get("outcome", "")))
            ).lower()
            if outcome in ("fail", "error"):
                is_fail = True
            elif outcome in ("warn", "warning"):
                is_warn = True
            elif outcome in ("debug", "info", "pass"):
                is_pass = True
            else:
                is_pass = True

        severity = self._compute_severity(is_pass, is_warn, is_fail)

        return PreflightCheckResult(
            name=name,
            check_name=check_name,
            is_pass=is_pass,
            is_warn=is_warn,
            is_fail=is_fail,
            title=raw.get("title", "") or insight.get("primary", ""),
            message=raw.get("message", "") or insight.get("detail", ""),
            uri=raw.get("URI", raw.get("uri", insight.get("uri", ""))),
            analyzer_type=self._infer_analyzer_type(raw),
            severity=severity,
        )

    @staticmethod
    def _compute_severity(
        is_pass: bool, is_warn: bool, is_fail: bool
    ) -> str:
        """Derive severity string from boolean flags.

        Args:
            is_pass: Whether the check passed.
            is_warn: Whether the check produced a warning.
            is_fail: Whether the check failed.

        Returns:
            One of "pass", "warn", "fail".
        """
        if is_fail:
            return "fail"
        if is_warn:
            return "warn"
        return "pass"

    @staticmethod
    def _infer_analyzer_type(raw: dict[str, Any]) -> str:
        """Extract analyzer type from the result name or structure.

        Troubleshoot.sh results often encode the analyzer type in the name
        field (e.g. ``"clusterVersion"`` or ``"Node resources"``).

        Args:
            raw: Single result dict.

        Returns:
            Inferred analyzer type string, or "unknown".
        """
        # Check explicit analyzer type/spec field
        for key in ("analyzerType", "analyzer_type", "type", "analyzerSpec"):
            if key in raw and raw[key]:
                return str(raw[key])

        # Check involvedObject.kind for pod/node/service-level results
        involved = raw.get("involvedObject", {})
        if isinstance(involved, dict) and involved.get("kind"):
            kind = involved["kind"]
            kind_map = {
                "Pod": "clusterPodStatuses",
                "Node": "nodeResources",
                "Deployment": "deploymentStatus",
                "StatefulSet": "statefulsetStatus",
                "Service": "ingress",
            }
            if kind in kind_map:
                return kind_map[kind]

        # Infer from name
        name = raw.get("name", "")
        if not name:
            name = raw.get("checkName", raw.get("check_name", ""))

        # Map common patterns
        known_types = {
            "clusterversion": "clusterVersion",
            "noderesource": "nodeResources",
            "deploymentstatus": "deploymentStatus",
            "statefulsetstatus": "statefulsetStatus",
            "containerruntime": "containerRuntime",
            "distribution": "distribution",
            "storageclass": "storageClass",
            "imagepullsecret": "imagePullSecret",
            "ingress": "ingress",
            "cephstatus": "cephStatus",
            "longhorn": "longhorn",
            "weave": "weave",
            "textanalyze": "textAnalyze",
            "jsoncompare": "jsonCompare",
        }

        name_lower = re.sub(r"[\s_-]", "", name.lower())
        for pattern, analyzer_type in known_types.items():
            if pattern in name_lower:
                return analyzer_type

        return name if name else "unknown"
