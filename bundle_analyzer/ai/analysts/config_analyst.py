"""Config analyst — analyzes broken dependency chains and network issues.

Traces configuration dependencies (ConfigMaps, Secrets, Services)
to identify cascading failures from missing or misconfigured resources.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.ai.prompts.config import CONFIG_SYSTEM_PROMPT, build_config_user_prompt
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import (
    AnalystOutput,
    ConfigIssue,
    DriftIssue,
    Evidence,
    Finding,
    Fix,
    TriageResult,
)


class ConfigAnalyst:
    """Analyzes configuration issues using Claude for root-cause determination.

    Gathers config/drift findings, service data, endpoint slices,
    and RBAC errors, then asks Claude to find broken dependency chains.
    """

    MAX_RETRIES: int = 3

    async def analyze(
        self,
        client: BundleAnalyzerClient,
        triage: TriageResult,
        index: BundleIndex,
        context_injector: Any | None = None,
    ) -> AnalystOutput:
        """Run AI analysis on configuration issues.

        Args:
            client: The AI client to use for completions.
            triage: Triage results containing config and drift findings.
            index: Bundle index for reading related data.
            context_injector: Optional ISV context injector.

        Returns:
            AnalystOutput with findings, root cause, evidence, and fixes.
        """
        start = time.monotonic()
        logger.debug("ConfigAnalyst: analyzing configuration issues")

        config_findings = self._serialize_config_issues(triage.config_issues)
        drift_findings = self._serialize_drift_issues(triage.drift_issues)
        services = self._get_services(index)
        endpoint_slices = self._get_endpoint_slices(index)
        ingress_resources = self._get_ingress(index)
        config_maps = self._get_config_map_names(index)
        secrets = self._get_secret_names(index)
        network_policies = self._get_network_policies(index)
        rbac_errors = (
            "\n".join(triage.rbac_errors) if triage.rbac_errors else None
        )

        user_prompt = build_config_user_prompt(
            config_findings=config_findings,
            drift_findings=drift_findings,
            services=services,
            endpoint_slices=endpoint_slices,
            ingress_resources=ingress_resources,
            config_maps=config_maps,
            secrets=secrets,
            network_policies=network_policies,
            rbac_errors=rbac_errors,
        )

        for attempt in range(self.MAX_RETRIES):
            try:
                system_prompt = CONFIG_SYSTEM_PROMPT
                if context_injector is not None:
                    system_prompt = context_injector.inject(system_prompt)
                raw_response = await client.complete(
                    system=system_prompt,
                    user=user_prompt,
                )
                result = self._parse_response(raw_response)
                elapsed = time.monotonic() - start
                logger.debug(
                    "ConfigAnalyst: completed in {:.2f}s", elapsed,
                )
                return result

            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning(
                    "ConfigAnalyst: parse error on attempt {}/{}: {}",
                    attempt + 1, self.MAX_RETRIES, exc,
                )
                if attempt == self.MAX_RETRIES - 1:
                    return self._fallback_output(str(exc))

        return self._fallback_output("all retries exhausted")

    @staticmethod
    def _serialize_config_issues(issues: list[ConfigIssue]) -> str | None:
        """Serialize config issues to a human-readable string."""
        if not issues:
            return None
        lines: list[str] = []
        for ci in issues:
            line = (
                f"  [{ci.issue}] {ci.resource_type}/{ci.resource_name} "
                f"in {ci.namespace}, referenced by {ci.referenced_by}"
            )
            if ci.missing_key:
                line += f" (missing key: {ci.missing_key})"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _serialize_drift_issues(issues: list[DriftIssue]) -> str | None:
        """Serialize drift issues to a human-readable string."""
        if not issues:
            return None
        lines: list[str] = []
        for di in issues:
            lines.append(
                f"  {di.resource_type}/{di.namespace}/{di.name}: "
                f"{di.field} spec={di.spec_value} status={di.status_value} "
                f"— {di.description}"
            )
        return "\n".join(lines)

    def _get_services(self, index: BundleIndex) -> str | None:
        """Get services data from the bundle."""
        if not index.has("services"):
            return None
        services_dir = index.root / "cluster-resources" / "services"
        if not services_dir.is_dir():
            return None

        entries: list[str] = []
        for ns_dir in sorted(services_dir.iterdir()):
            if not ns_dir.is_dir():
                continue
            for svc_file in sorted(ns_dir.glob("*.json")):
                data = index.read_json(str(svc_file.relative_to(index.root)))
                if data and isinstance(data, dict):
                    name = data.get("metadata", {}).get("name", "?")
                    ns = data.get("metadata", {}).get("namespace", "?")
                    selector = data.get("spec", {}).get("selector", {})
                    svc_type = data.get("spec", {}).get("type", "ClusterIP")
                    ports = data.get("spec", {}).get("ports", [])
                    port_strs = [
                        f"{p.get('port', '?')}/{p.get('protocol', 'TCP')}"
                        for p in ports
                    ]
                    entries.append(
                        f"  {ns}/{name} type={svc_type} "
                        f"selector={json.dumps(selector)} "
                        f"ports=[{', '.join(port_strs)}]"
                    )

        return "\n".join(entries) if entries else None

    def _get_endpoint_slices(self, index: BundleIndex) -> str | None:
        """Get endpoint slice data from the bundle."""
        if not index.has("endpoints"):
            return None
        endpoints_dir = index.root / "cluster-resources" / "endpoints"
        if not endpoints_dir.is_dir():
            return None

        entries: list[str] = []
        for ns_dir in sorted(endpoints_dir.iterdir()):
            if not ns_dir.is_dir():
                continue
            for ep_file in sorted(ns_dir.glob("*.json")):
                data = index.read_json(str(ep_file.relative_to(index.root)))
                if data and isinstance(data, dict):
                    name = data.get("metadata", {}).get("name", "?")
                    ns = data.get("metadata", {}).get("namespace", "?")
                    subsets = data.get("subsets", [])
                    ready_count = sum(
                        len(s.get("addresses", [])) for s in subsets
                    )
                    not_ready_count = sum(
                        len(s.get("notReadyAddresses", [])) for s in subsets
                    )
                    entries.append(
                        f"  {ns}/{name} ready={ready_count} notReady={not_ready_count}"
                    )

        return "\n".join(entries) if entries else None

    def _get_ingress(self, index: BundleIndex) -> str | None:
        """Get ingress resources from the bundle."""
        if not index.has("ingress"):
            return None
        ingress_dir = index.root / "cluster-resources" / "ingress"
        if not ingress_dir.is_dir():
            return None

        entries: list[str] = []
        for ns_dir in sorted(ingress_dir.iterdir()):
            if not ns_dir.is_dir():
                continue
            for ing_file in sorted(ns_dir.glob("*.json")):
                data = index.read_json(str(ing_file.relative_to(index.root)))
                if data and isinstance(data, dict):
                    name = data.get("metadata", {}).get("name", "?")
                    ns = data.get("metadata", {}).get("namespace", "?")
                    rules = data.get("spec", {}).get("rules", [])
                    backends: list[str] = []
                    for rule in rules:
                        host = rule.get("host", "*")
                        for path_rule in rule.get("http", {}).get("paths", []):
                            backend = path_rule.get("backend", {})
                            svc = backend.get("service", {}).get("name", "?")
                            port = backend.get("service", {}).get("port", {}).get("number", "?")
                            backends.append(f"{host} -> {svc}:{port}")
                    entries.append(
                        f"  {ns}/{name}: {', '.join(backends) if backends else 'no rules'}"
                    )

        return "\n".join(entries) if entries else None

    def _get_config_map_names(self, index: BundleIndex) -> str | None:
        """Get ConfigMap names (not values) grouped by namespace."""
        if not index.has("configmaps"):
            return None
        cm_dir = index.root / "cluster-resources" / "configmaps"
        if not cm_dir.is_dir():
            return None

        entries: list[str] = []
        for ns_dir in sorted(cm_dir.iterdir()):
            if not ns_dir.is_dir():
                continue
            names = sorted(f.stem for f in ns_dir.glob("*.json"))
            if names:
                entries.append(f"  {ns_dir.name}: {', '.join(names)}")

        return "\n".join(entries) if entries else None

    def _get_secret_names(self, index: BundleIndex) -> str | None:
        """Get Secret names (not values) grouped by namespace."""
        if not index.has("secrets"):
            return None
        sec_dir = index.root / "cluster-resources" / "secrets"
        if not sec_dir.is_dir():
            return None

        entries: list[str] = []
        for ns_dir in sorted(sec_dir.iterdir()):
            if not ns_dir.is_dir():
                continue
            names = sorted(f.stem for f in ns_dir.glob("*.json"))
            if names:
                entries.append(f"  {ns_dir.name}: {', '.join(names)}")

        return "\n".join(entries) if entries else None

    def _get_network_policies(self, index: BundleIndex) -> str | None:
        """Get NetworkPolicy resources if present."""
        netpol_dir = index.root / "cluster-resources" / "network-policies"
        if not netpol_dir.is_dir():
            return None

        entries: list[str] = []
        for ns_dir in sorted(netpol_dir.iterdir()):
            if not ns_dir.is_dir():
                continue
            for np_file in sorted(ns_dir.glob("*.json")):
                data = index.read_json(str(np_file.relative_to(index.root)))
                if data and isinstance(data, dict):
                    name = data.get("metadata", {}).get("name", "?")
                    ns = data.get("metadata", {}).get("namespace", "?")
                    pod_selector = data.get("spec", {}).get("podSelector", {})
                    entries.append(
                        f"  {ns}/{name} podSelector={json.dumps(pod_selector)}"
                    )

        return "\n".join(entries) if entries else None

    def _parse_response(self, raw: str) -> AnalystOutput:
        """Parse Claude's JSON response into an AnalystOutput.

        Args:
            raw: Raw text response from Claude (should be JSON).

        Returns:
            Structured AnalystOutput.

        Raises:
            json.JSONDecodeError: If response is not valid JSON.
        """
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        data = json.loads(cleaned)

        resource = "cluster/config"
        confidence_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
        confidence = confidence_map.get(data.get("confidence", "low"), 0.3)

        finding = Finding(
            id=f"config-{uuid.uuid4().hex[:8]}",
            severity="critical" if confidence >= 0.6 else "warning",
            type="config-issue",
            resource=resource,
            symptom=data.get("immediate_cause", "Unknown symptom"),
            root_cause=data.get("root_cause", "Could not determine root cause"),
            evidence=[
                Evidence(file=resource, excerpt=e)
                for e in data.get("evidence", [])
            ],
            fix=Fix(
                description=data.get("fix", "No fix suggested"),
                commands=[],
            ) if data.get("fix") else None,
            confidence=confidence,
        )

        return AnalystOutput(
            analyst="config",
            findings=[finding],
            root_cause=data.get("root_cause"),
            confidence=confidence,
            evidence=[
                Evidence(file=resource, excerpt=e)
                for e in data.get("evidence", [])
            ],
            remediation=[
                Fix(description=data.get("fix", "No fix suggested"), commands=[])
            ] if data.get("fix") else [],
            uncertainty=data.get("what_i_cant_tell", []),
        )

    @staticmethod
    def _fallback_output(error: str) -> AnalystOutput:
        """Return a low-confidence output when parsing fails.

        Args:
            error: Error description.

        Returns:
            AnalystOutput with low confidence and error note.
        """
        return AnalystOutput(
            analyst="config",
            findings=[
                Finding(
                    id=f"config-fallback-{uuid.uuid4().hex[:8]}",
                    severity="warning",
                    type="config-issue",
                    resource="cluster/config",
                    symptom="AI analysis could not parse response",
                    root_cause=f"Analysis error: {error}",
                    evidence=[],
                    confidence=0.1,
                )
            ],
            root_cause=None,
            confidence=0.1,
            evidence=[],
            remediation=[],
            uncertainty=[f"AI response parsing failed: {error}"],
        )
