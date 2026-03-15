"""Independent evaluation engine — "second opinion" on pipeline analysis.

Gathers exhaustive raw evidence from the bundle (pod specs, events, logs,
all triage signals), builds a detailed prompt, and produces per-failure
dependency traces with cross-referenced signals.
"""

from __future__ import annotations

import json
import time
from typing import Any

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.ai.prompts.evaluator import (
    EVALUATOR_SYSTEM_PROMPT,
    build_evaluator_user_prompt,
)
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import (
    AnalysisResult,
    CorrelatedSignal,
    DependencyLink,
    EvaluationResult,
    EvaluationVerdict,
    MissedFailurePoint,
)

MAX_LOG_LINES = 300


class EvaluationEngine:
    """Independently evaluates the main pipeline's analysis results.

    Gathers raw pod specs (probes, resources, volumes, status), events,
    logs, and ALL triage scanner signals. Feeds these to an LLM with a
    different persona to produce detailed dependency traces.
    """

    async def evaluate(
        self,
        client: BundleAnalyzerClient,
        analysis: AnalysisResult,
        index: BundleIndex,
    ) -> EvaluationResult:
        """Run the independent evaluation pass.

        Args:
            client: The AI client for making LLM calls.
            analysis: The completed analysis from the main pipeline.
            index: The bundle index for reading raw files.

        Returns:
            EvaluationResult with per-failure dependency traces and cross-referenced signals.
        """
        start = time.monotonic()

        # Step 1: Gather all raw evidence
        raw_log_excerpts = await self._gather_raw_logs(analysis, index)
        raw_pod_specs = self._gather_pod_specs(analysis, index)
        raw_events = self._gather_events(analysis, index)

        # Step 2: Build prompt with exhaustive evidence
        user_prompt = build_evaluator_user_prompt(
            analysis, raw_log_excerpts, raw_pod_specs, raw_events,
        )
        logger.debug(
            "Evaluator prompt built: {} findings, {} pod specs, {} event namespaces, "
            "{} log sources, {} chars",
            len(analysis.findings),
            len(raw_pod_specs),
            len(raw_events),
            len(raw_log_excerpts),
            len(user_prompt),
        )

        # Step 3: LLM call
        try:
            raw_response = await client.complete(
                system=EVALUATOR_SYSTEM_PROMPT,
                user=user_prompt,
                max_tokens=16384,
                temperature=0.2,
            )

            # Step 4: Parse response (with truncation repair)
            result = self._parse_response(raw_response)
            elapsed = time.monotonic() - start
            result.evaluation_duration_seconds = elapsed

            logger.info(
                "Evaluation complete: overall={}, confidence={:.2f}, "
                "{} verdicts, {} missed, duration={:.1f}s",
                result.overall_correctness,
                result.overall_confidence,
                len(result.verdicts),
                len(result.missed_failure_points),
                elapsed,
            )
            return result

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.error("Evaluation response parsing failed: {}", exc)
            elapsed = time.monotonic() - start
            return self._fallback_result(elapsed, str(exc))
        except RuntimeError as exc:
            logger.error("Evaluation API call failed: {}", exc)
            elapsed = time.monotonic() - start
            return self._fallback_result(elapsed, str(exc))

    def _gather_pod_specs(
        self,
        analysis: AnalysisResult,
        index: BundleIndex,
    ) -> dict[str, dict]:
        """Extract relevant pod spec sections for all failure-related pods.

        Pulls probes, resources, volumes, env references, and full status
        for each pod referenced in findings or critical triage signals.

        Args:
            analysis: The analysis result.
            index: The bundle index.

        Returns:
            Dict mapping pod key (ns/name) to spec data dict.
        """
        pod_specs: dict[str, dict] = {}
        pods_needed: set[tuple[str, str]] = set()

        # From findings
        for finding in analysis.findings:
            resource = finding.resource or ""
            # Parse "pod/namespace/name" or "Pod/namespace/name"
            parts = resource.split("/")
            if len(parts) >= 3 and parts[0].lower() == "pod":
                pods_needed.add((parts[1], parts[2]))

        # From critical + warning pods
        for pod in analysis.triage.critical_pods + analysis.triage.warning_pods[:10]:
            pods_needed.add((pod.namespace, pod.pod_name))

        # Gather from bundle
        pod_cache: dict[str, dict] = {}
        for pod_json in index.get_all_pods():
            meta = pod_json.get("metadata", {})
            ns = meta.get("namespace", "")
            name = meta.get("name", "")
            if (ns, name) in pods_needed:
                pod_cache[f"{ns}/{name}"] = pod_json

        # Extract relevant sections
        for key, pod_json in pod_cache.items():
            spec = pod_json.get("spec", {})
            status = pod_json.get("status", {})

            containers = []
            for c in spec.get("containers", []):
                container_info: dict[str, Any] = {
                    "name": c.get("name", ""),
                    "image": c.get("image", ""),
                    "resources": c.get("resources", {}),
                    "volumeMounts": c.get("volumeMounts", [])[:5],
                }
                # Probes
                for probe_type in ["livenessProbe", "readinessProbe", "startupProbe"]:
                    if probe_type in c:
                        container_info[probe_type] = c[probe_type]

                # Env references (ConfigMap/Secret refs, not values)
                env_refs = []
                for env in c.get("env", []):
                    vf = env.get("valueFrom", {})
                    if vf.get("configMapKeyRef"):
                        ref = vf["configMapKeyRef"]
                        env_refs.append(f"ConfigMap/{ref.get('name', '?')}/{ref.get('key', '?')}")
                    if vf.get("secretKeyRef"):
                        ref = vf["secretKeyRef"]
                        env_refs.append(f"Secret/{ref.get('name', '?')}/{ref.get('key', '?')}")
                for ef in c.get("envFrom", []):
                    if ef.get("configMapRef"):
                        env_refs.append(f"ConfigMap/{ef['configMapRef'].get('name', '?')}")
                    if ef.get("secretRef"):
                        env_refs.append(f"Secret/{ef['secretRef'].get('name', '?')}")
                if env_refs:
                    container_info["env_refs"] = env_refs

                containers.append(container_info)

            pod_specs[key] = {
                "containers": containers,
                "restartPolicy": spec.get("restartPolicy", "Always"),
                "nodeName": spec.get("nodeName"),
                "volumes": spec.get("volumes", [])[:8],
                "status": {
                    "phase": status.get("phase"),
                    "nodeName": status.get("hostIP"),
                    "conditions": status.get("conditions", []),
                    "containerStatuses": status.get("containerStatuses", []),
                },
            }

        return pod_specs

    def _gather_events(
        self,
        analysis: AnalysisResult,
        index: BundleIndex,
    ) -> dict[str, list[dict]]:
        """Gather Kubernetes events for all relevant namespaces.

        Args:
            analysis: The analysis result.
            index: The bundle index.

        Returns:
            Dict mapping namespace to list of event dicts.
        """
        namespaces: set[str] = set()

        # From critical pods
        for pod in analysis.triage.critical_pods:
            namespaces.add(pod.namespace)

        # From findings
        for finding in analysis.findings:
            parts = (finding.resource or "").split("/")
            if len(parts) >= 3:
                namespaces.add(parts[1])

        events_by_ns: dict[str, list[dict]] = {}
        for ns in namespaces:
            events = index.get_events(ns)
            if events:
                # Keep warning events + first few normal events
                filtered = [e for e in events if e.get("type") == "Warning"][:30]
                normal = [e for e in events if e.get("type") == "Normal"][:5]
                events_by_ns[ns] = filtered + normal

        return events_by_ns

    async def _gather_raw_logs(
        self,
        analysis: AnalysisResult,
        index: BundleIndex,
    ) -> dict[str, str]:
        """Collect raw log excerpts from evidence paths and critical pod logs.

        Args:
            analysis: The analysis result.
            index: The bundle index.

        Returns:
            Dict mapping source path to log content (capped at MAX_LOG_LINES).
        """
        excerpts: dict[str, str] = {}
        paths_seen: set[str] = set()

        # From evidence citations in findings
        for finding in analysis.findings:
            for evidence in finding.evidence:
                path = evidence.file
                if path in paths_seen:
                    continue
                paths_seen.add(path)
                content = await self._read_log_safe(index, path)
                if content:
                    excerpts[path] = content

        # From critical pod log paths
        for pod in analysis.triage.critical_pods:
            for log_path in [pod.log_path, pod.previous_log_path]:
                if log_path and log_path not in paths_seen:
                    paths_seen.add(log_path)
                    content = await self._read_log_safe(index, log_path)
                    if content:
                        excerpts[log_path] = content

        # Also try streaming logs for critical pods
        for pod in analysis.triage.critical_pods[:5]:
            container = pod.container_name or ""
            if not container:
                continue
            stream_key = f"{pod.namespace}/{pod.pod_name}/{container}.log"
            if stream_key in paths_seen:
                continue
            paths_seen.add(stream_key)
            lines = list(index.stream_log(
                namespace=pod.namespace,
                pod=pod.pod_name,
                container=container,
                previous=False,
                last_n_lines=MAX_LOG_LINES,
            ))
            if lines:
                excerpts[stream_key] = "\n".join(lines)
            else:
                # Try previous logs
                prev_lines = list(index.stream_log(
                    namespace=pod.namespace,
                    pod=pod.pod_name,
                    container=container,
                    previous=True,
                    last_n_lines=MAX_LOG_LINES,
                ))
                if prev_lines:
                    excerpts[f"{stream_key} (previous)"] = "\n".join(prev_lines)

        return excerpts

    async def _read_log_safe(
        self,
        index: BundleIndex,
        path: str,
    ) -> str | None:
        """Safely read a file from the bundle, returning None on failure.

        Args:
            index: The bundle index.
            path: Path within the bundle to read.

        Returns:
            The last MAX_LOG_LINES of the file content, or None.
        """
        try:
            content = index.read_text(path)
            if not content:
                return None
            lines = content.splitlines()
            if len(lines) > MAX_LOG_LINES:
                lines = lines[-MAX_LOG_LINES:]
            return "\n".join(lines)
        except Exception as exc:
            logger.debug("Could not read {}: {}", path, exc)
            return None

    def _parse_response(self, raw: str) -> EvaluationResult:
        """Parse the JSON response from the evaluator LLM call.

        Args:
            raw: Raw text response from the API.

        Returns:
            Parsed EvaluationResult with full dependency traces.

        Raises:
            json.JSONDecodeError: If the response cannot be parsed as JSON.
        """
        text = raw.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines)

        # Try parsing as-is first
        try:
            data: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError:
            # Attempt to repair truncated JSON by closing open structures
            data = self._repair_truncated_json(text)

        verdicts = []
        valid_significance = {"root_cause", "contributing", "symptom", "context"}
        valid_correctness = {"Correct", "Partially Correct", "Incorrect", "Inconclusive"}
        valid_severity = {"critical", "warning", "info"}

        def safe_link(link: dict) -> DependencyLink:
            """Parse a DependencyLink, coercing invalid significance values."""
            sig = link.get("significance", "context")
            if sig not in valid_significance:
                sig = "contributing" if "cause" in str(sig).lower() else "context"
            link["significance"] = sig
            return DependencyLink(**link)

        def safe_signal(sig: dict) -> CorrelatedSignal:
            """Parse a CorrelatedSignal, coercing invalid severity values."""
            sev = sig.get("severity", "info")
            if sev not in valid_severity:
                sev = "warning"
            sig["severity"] = sev
            return CorrelatedSignal(**sig)

        for v in data.get("verdicts", []):
            try:
                dep_chain = [safe_link(link) for link in v.get("dependency_chain", [])]
                corr_signals = [safe_signal(sig) for sig in v.get("correlated_signals", [])]
                # Coerce correctness
                correctness = v.get("correctness", "Inconclusive")
                if correctness not in valid_correctness:
                    correctness = "Inconclusive"
                verdicts.append(EvaluationVerdict(
                    failure_point=v.get("failure_point", ""),
                    resource=v.get("resource", ""),
                    app_claimed_cause=v.get("app_claimed_cause", ""),
                    true_likely_cause=v.get("true_likely_cause", ""),
                    correctness=correctness,
                    dependency_chain=dep_chain,
                    correlated_signals=corr_signals,
                    supporting_evidence=v.get("supporting_evidence", []),
                    contradicting_evidence=v.get("contradicting_evidence", []),
                    missed=v.get("missed", []),
                    misinterpreted=v.get("misinterpreted", []),
                    stronger_alternative=v.get("stronger_alternative"),
                    alternative_hypotheses=v.get("alternative_hypotheses", []),
                    blast_radius=v.get("blast_radius", []),
                    remediation_assessment=v.get("remediation_assessment", ""),
                    confidence_score=v.get("confidence_score", 0.0),
                    notes=v.get("notes", ""),
                ))
            except (TypeError, ValueError, KeyError) as exc:
                logger.warning("Skipping malformed verdict: {}", exc)

        missed = []
        for m in data.get("missed_failure_points", []):
            if isinstance(m, str):
                # Simple string format fallback
                missed.append(MissedFailurePoint(
                    failure_point=m,
                    resource="",
                    evidence_summary=m,
                    severity="warning",
                ))
            elif isinstance(m, dict):
                dep_chain = [safe_link(link) for link in m.get("dependency_chain", [])]
                corr_signals = [safe_signal(sig) for sig in m.get("correlated_signals", [])]
                sev = m.get("severity", "warning")
                if sev not in valid_severity:
                    sev = "warning"
                missed.append(MissedFailurePoint(
                    failure_point=m.get("failure_point", ""),
                    resource=m.get("resource", ""),
                    evidence_summary=m.get("evidence_summary", ""),
                    severity=sev,
                    dependency_chain=dep_chain,
                    correlated_signals=corr_signals,
                    recommended_action=m.get("recommended_action", ""),
                ))

        overall = data.get("overall_correctness", "Inconclusive")
        if overall not in valid_correctness:
            overall = "Inconclusive"

        return EvaluationResult(
            verdicts=verdicts,
            overall_correctness=overall,
            overall_confidence=data.get("overall_confidence", 0.0),
            missed_failure_points=missed,
            cross_cutting_concerns=data.get("cross_cutting_concerns", []),
            evaluation_summary=data.get("evaluation_summary", ""),
        )

    def _repair_truncated_json(self, text: str) -> dict[str, Any]:
        """Attempt to repair truncated JSON from a token-limited LLM response.

        Closes open strings, arrays, and objects so that the parseable prefix
        can be recovered. If repair fails, raises json.JSONDecodeError.

        Args:
            text: The truncated JSON text.

        Returns:
            Parsed dict from the repaired JSON.

        Raises:
            json.JSONDecodeError: If even the repaired text cannot be parsed.
        """
        logger.warning("Attempting to repair truncated JSON ({} chars)", len(text))

        # Strategy: find the last complete value boundary and close structures
        # First, try truncating to the last complete array element or object
        repair = text.rstrip()

        # Remove any trailing partial string (unterminated quote)
        # Walk backwards to find a good truncation point
        for trim_suffix in ['", ', ',"', ', "', '"', ',']:
            idx = repair.rfind(trim_suffix)
            if idx > len(repair) * 0.5:  # Only trim from the second half
                candidate = repair[:idx]
                # Close open structures
                closed = self._close_json(candidate)
                try:
                    return json.loads(closed)
                except json.JSONDecodeError:
                    continue

        # Last resort: try closing as-is
        closed = self._close_json(repair)
        return json.loads(closed)

    @staticmethod
    def _close_json(text: str) -> str:
        """Close open JSON brackets/braces.

        Args:
            text: Partial JSON text.

        Returns:
            Text with closing brackets appended.
        """
        # Track open structures
        in_string = False
        escape = False
        stack: list[str] = []

        for ch in text:
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in ('{', '['):
                stack.append('}' if ch == '{' else ']')
            elif ch in ('}', ']'):
                if stack and stack[-1] == ch:
                    stack.pop()

        # If we're inside a string, close it
        if in_string:
            text += '"'

        # Close remaining open structures
        stack.reverse()
        text += ''.join(stack)
        return text

    def _fallback_result(self, elapsed: float, error_msg: str) -> EvaluationResult:
        """Return a fallback result when evaluation fails.

        Args:
            elapsed: Time elapsed before failure.
            error_msg: Description of what went wrong.

        Returns:
            EvaluationResult with Inconclusive overall verdict.
        """
        return EvaluationResult(
            verdicts=[],
            overall_correctness="Inconclusive",
            overall_confidence=0.0,
            missed_failure_points=[],
            cross_cutting_concerns=[],
            evaluation_summary=f"Evaluation failed: {error_msg}",
            evaluation_duration_seconds=elapsed,
        )
