"""Core scrubber — composes all detectors into a unified data protection pipeline.

Two operating modes:
1. scrub_for_storage() — Layer 1, pre-ingestion. Removes credentials, PII, infra metadata.
2. scrub_for_llm()     — Layer 2, pre-LLM transmission. All of Layer 1 + prompt injection guard.

Layer 2 is strictly a superset of Layer 1.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from bundle_analyzer.security.entropy import EntropyDetector
from bundle_analyzer.security.kubernetes import KubernetesStructuralScrubber
from bundle_analyzer.security.models import (
    SanitizationReport,
    SecurityPolicy,
)
from bundle_analyzer.security.patterns import PatternDetector
from bundle_analyzer.security.policy import PolicyEngine
from bundle_analyzer.security.prompt_guard import PromptInjectionGuard


class BundleScrubber:
    """Multi-layer data scrubber composing pattern, structural, and entropy detection.

    Provides two layers of protection:
    - ``scrub_for_storage()``: Applied at ingestion boundary.
    - ``scrub_for_llm()``: Applied before every LLM API call.
    """

    def __init__(self, policy: SecurityPolicy | None = None) -> None:
        """Initialise the scrubber with all detector components.

        Args:
            policy: Security policy controlling what to redact/preserve.
                    Defaults to standard mode.
        """
        self.policy = policy or SecurityPolicy()
        self.policy_engine = PolicyEngine(self.policy)
        self.pattern_detector = PatternDetector()
        self.k8s_scrubber = KubernetesStructuralScrubber()
        self.entropy_detector = EntropyDetector(
            threshold=self.policy.entropy_threshold,
            min_length=self.policy.min_entropy_length,
        )
        self.prompt_guard = PromptInjectionGuard()

    # ------------------------------------------------------------------
    # Layer 1: Pre-ingestion
    # ------------------------------------------------------------------

    def scrub_for_storage(
        self,
        data: str,
        source_type: str = "unknown",
        source_path: str = "",
    ) -> tuple[str, SanitizationReport]:
        """Layer 1: Scrub data before storage, indexing, or UI rendering.

        Applied to all data entering the system. Removes credentials, PII,
        and infrastructure metadata. Does NOT apply prompt injection guards.

        Args:
            data: Raw text to scrub.
            source_type: One of pod_spec, container_log, node_json, event,
                         configmap, secret, stack_trace, ci_output, unknown.
            source_path: Optional path hint for audit logging.

        Returns:
            Tuple of (scrubbed_text, sanitization_report).
        """
        report = SanitizationReport()

        if not data or not data.strip():
            return data, report

        result = data

        # Step 1: Pattern-based detection
        result, pattern_entries = self.pattern_detector.redact_all(result)
        for entry in pattern_entries:
            entry.location = source_path
            if self.policy_engine.should_redact_category(entry.category):
                report.add(entry)

        # Step 2: Entropy-based detection (if enabled)
        if self.policy.redact_high_entropy:
            scrub_level = self.policy_engine.get_scrub_level(source_type)
            if scrub_level in ("aggressive", "standard"):
                result, entropy_entries = self.entropy_detector.redact_high_entropy(
                    result, context=source_type
                )
                for entry in entropy_entries:
                    entry.location = source_path
                    report.add(entry)

        return result, report

    # ------------------------------------------------------------------
    # Layer 2: Pre-LLM
    # ------------------------------------------------------------------

    def scrub_for_llm(
        self,
        text: str,
        source_type: str = "prompt",
    ) -> tuple[str, SanitizationReport]:
        """Layer 2: Scrub text before sending to an LLM API.

        Runs all Layer 1 detectors plus prompt injection guard.
        This is called automatically by ``BundleAnalyzerClient.complete()``.

        Args:
            text: Prompt text to scrub.
            source_type: Source type hint for policy engine.

        Returns:
            Tuple of (sanitized_text, sanitization_report).
        """
        # Run Layer 1 first
        result, report = self.scrub_for_storage(text, source_type, source_path="llm-prompt")

        # Layer 2 addition: prompt injection guard
        result, injection_entries = self.prompt_guard.neutralize(result)
        for entry in injection_entries:
            entry.location = "llm-prompt"
            report.add(entry)

        if report.prompt_injection_detected:
            logger.warning(
                "Prompt injection neutralized before LLM call: {} detection(s)",
                report.prompt_injection_count,
            )

        return result, report

    # ------------------------------------------------------------------
    # Structural scrubbers (K8s-aware)
    # ------------------------------------------------------------------

    def scrub_pod_json(self, pod_data: dict[str, Any]) -> tuple[dict[str, Any], SanitizationReport]:
        """Structurally scrub a pod JSON object.

        Preserves diagnostic keys (names, labels, resources, probes)
        while redacting secret values (env values, secretKeyRef, etc.).

        Args:
            pod_data: Parsed pod JSON dict.

        Returns:
            Tuple of (scrubbed_pod_dict, sanitization_report).
        """
        report = SanitizationReport()
        scrubbed, entries = self.k8s_scrubber.scrub_pod_spec(pod_data)
        for entry in entries:
            report.add(entry)
        return scrubbed, report

    def scrub_node_json(self, node_data: dict[str, Any]) -> tuple[dict[str, Any], SanitizationReport]:
        """Structurally scrub a node JSON object.

        Redacts IPs and machine IDs, preserves conditions and capacity.

        Args:
            node_data: Parsed node JSON dict.

        Returns:
            Tuple of (scrubbed_node_dict, sanitization_report).
        """
        report = SanitizationReport()
        scrubbed, entries = self.k8s_scrubber.scrub_node_json(node_data)
        for entry in entries:
            report.add(entry)
        return scrubbed, report

    def scrub_log_lines(
        self,
        lines: list[str],
        source: str = "",
    ) -> tuple[list[str], SanitizationReport]:
        """Scrub container log lines through all detectors.

        Args:
            lines: List of log line strings.
            source: Source identifier for audit logging.

        Returns:
            Tuple of (scrubbed_lines, sanitization_report).
        """
        report = SanitizationReport()
        scrubbed, entries = self.k8s_scrubber.scrub_log_lines(lines, source=source)
        for entry in entries:
            report.add(entry)
        return scrubbed, report

    def scrub_event(self, event_data: dict[str, Any]) -> tuple[dict[str, Any], SanitizationReport]:
        """Scrub a Kubernetes event object.

        Args:
            event_data: Parsed event JSON dict.

        Returns:
            Tuple of (scrubbed_event_dict, sanitization_report).
        """
        report = SanitizationReport()
        scrubbed, entries = self.k8s_scrubber.scrub_event(event_data)
        for entry in entries:
            report.add(entry)
        return scrubbed, report

    def scrub_configmap(self, cm_data: dict[str, Any]) -> tuple[dict[str, Any], SanitizationReport]:
        """Scrub a ConfigMap — keep keys, redact all values.

        Args:
            cm_data: Parsed ConfigMap JSON dict.

        Returns:
            Tuple of (scrubbed_cm_dict, sanitization_report).
        """
        report = SanitizationReport()
        scrubbed, entries = self.k8s_scrubber.scrub_configmap_data(cm_data)
        for entry in entries:
            report.add(entry)
        return scrubbed, report
