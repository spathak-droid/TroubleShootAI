"""Analyst steps — run pod, node, and config analysts in parallel.

Analyzes ALL failing resources (not just the first), merging results
into consolidated AnalystOutput objects per analyst type.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.ai.context_injector import ContextInjector
from bundle_analyzer.ai.orchestration.helpers import (
    empty_analyst_output,
    find_node_json,
    find_pod_json,
)
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import AnalystOutput, TriageResult

# Limit per-analyst-type concurrency to avoid API rate limits
MAX_PODS_TO_ANALYZE = 5
MAX_NODES_TO_ANALYZE = 3

# Timeout constants for AI analyst calls (seconds)
AI_ANALYST_TIMEOUT = 120  # overall timeout for the parallel analyst batch
PER_RESOURCE_TIMEOUT = 60  # timeout for a single pod/node analysis


async def _analyze_with_timeout(
    coro,
    resource_name: str,
    timeout: float = PER_RESOURCE_TIMEOUT,
):
    """Run a single analyst coroutine with a timeout guard.

    Args:
        coro: The analyst coroutine to execute.
        resource_name: Human-readable name for logging on timeout.
        timeout: Maximum seconds to wait before cancelling.

    Returns:
        The analyst result, or None if the call timed out.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except TimeoutError:
        logger.warning("Analysis timed out for {} after {}s", resource_name, timeout)
        return None


def _merge_analyst_outputs(outputs: list[AnalystOutput], analyst_type: str) -> AnalystOutput:
    """Merge multiple per-resource outputs into a single AnalystOutput.

    Args:
        outputs: Individual analyst outputs to merge.
        analyst_type: The analyst type label.

    Returns:
        A single AnalystOutput combining all findings, evidence, etc.
    """
    if not outputs:
        return empty_analyst_output(analyst_type, "No outputs to merge")
    if len(outputs) == 1:
        return outputs[0]

    all_findings = []
    all_evidence = []
    all_remediation = []
    all_uncertainty = []
    max_confidence = 0.0
    root_causes = []

    for out in outputs:
        all_findings.extend(out.findings)
        all_evidence.extend(out.evidence)
        all_remediation.extend(out.remediation)
        all_uncertainty.extend(out.uncertainty)
        if out.confidence > max_confidence:
            max_confidence = out.confidence
        if out.root_cause:
            root_causes.append(out.root_cause)

    # Combine root causes into a summary if multiple
    combined_root_cause = root_causes[0] if len(root_causes) == 1 else (
        " | ".join(f"[{i+1}] {rc}" for i, rc in enumerate(root_causes))
        if root_causes else None
    )

    return AnalystOutput(
        analyst=analyst_type,
        findings=all_findings,
        root_cause=combined_root_cause,
        confidence=max_confidence,
        evidence=all_evidence,
        remediation=all_remediation,
        uncertainty=all_uncertainty,
    )


async def run_analysts_parallel(
    client: BundleAnalyzerClient,
    triage: TriageResult,
    index: BundleIndex,
    context_injector: ContextInjector,
) -> list[AnalystOutput]:
    """Run pod, node, and config analysts concurrently.

    Analyzes ALL failing pods and nodes (up to limits), not just the first.
    The entire batch is guarded by AI_ANALYST_TIMEOUT to prevent hung LLM
    calls from blocking the pipeline indefinitely.

    Args:
        client: API client for Claude calls.
        triage: Triage results for analyst input.
        index: Bundle index for reading resources.
        context_injector: ISV context for prompt augmentation.

    Returns:
        List of analyst outputs (may be fewer than 3 if some fail or time out).
    """
    tasks = []

    # Pod analyst — analyze ALL critical + warning pods (up to limit)
    if triage.critical_pods or triage.warning_pods:
        tasks.append(_run_all_pod_analysts(client, triage, index, context_injector))

    # Node analyst — analyze ALL nodes with issues (up to limit)
    if triage.node_issues:
        tasks.append(_run_all_node_analysts(client, triage, index, context_injector))

    # Config analyst (already analyzes all config issues at once)
    if triage.config_issues or triage.drift_issues:
        tasks.append(run_single_analyst("config", client, triage, index, context_injector))

    if not tasks:
        logger.info("No analysts needed — triage found no issues requiring AI analysis")
        return []

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=AI_ANALYST_TIMEOUT,
        )
    except TimeoutError:
        logger.error("AI analysts timed out after {}s", AI_ANALYST_TIMEOUT)
        results = []

    outputs: list[AnalystOutput] = []
    for result in results:
        if isinstance(result, AnalystOutput):
            outputs.append(result)
        elif isinstance(result, Exception):
            logger.error("Analyst failed: {}", result)
    return outputs


async def _run_all_pod_analysts(
    client: BundleAnalyzerClient,
    triage: TriageResult,
    index: BundleIndex,
    context_injector: ContextInjector,
) -> AnalystOutput:
    """Analyze ALL failing pods (critical first, then warning) up to limit.

    Each individual pod analysis is guarded by PER_RESOURCE_TIMEOUT to prevent
    a single hung LLM call from blocking the rest of the batch.

    Args:
        client: API client for Claude calls.
        triage: Triage results with pod issues.
        index: Bundle index.
        context_injector: ISV context injector.

    Returns:
        Merged AnalystOutput combining all pod analyses.
    """
    from bundle_analyzer.ai.analysts.pod_analyst import PodAnalyst

    all_pods = list(triage.critical_pods) + list(triage.warning_pods)
    if not all_pods:
        return empty_analyst_output("pod", "No pod issues to analyze")

    # Deduplicate by namespace/pod_name (same pod can appear in both lists)
    seen = set()
    unique_pods = []
    for pod in all_pods:
        key = f"{pod.namespace}/{pod.pod_name}"
        if key not in seen:
            seen.add(key)
            unique_pods.append(pod)

    pods_to_analyze = unique_pods[:MAX_PODS_TO_ANALYZE]
    logger.info(
        "PodAnalyst: analyzing {}/{} failing pods",
        len(pods_to_analyze), len(unique_pods),
    )

    analyst = PodAnalyst()
    tasks = []
    for target in pods_to_analyze:
        pod_data = find_pod_json(target.namespace, target.pod_name, index)
        if pod_data:
            coro = analyst.analyze(client, pod_data, index, context_injector=context_injector)
            tasks.append(_analyze_with_timeout(coro, f"{target.namespace}/{target.pod_name}"))
        else:
            logger.warning("Pod JSON not found for {}/{}", target.namespace, target.pod_name)

    if not tasks:
        return empty_analyst_output("pod", "No pod JSON found in bundle")

    results = await asyncio.gather(*tasks, return_exceptions=True)
    outputs = []
    for result in results:
        if isinstance(result, AnalystOutput):
            outputs.append(result)
        elif isinstance(result, Exception):
            logger.error("Pod analyst failed for a pod: {}", result)
        # None results come from _analyze_with_timeout on timeout — already logged

    return _merge_analyst_outputs(outputs, "pod")


async def _run_all_node_analysts(
    client: BundleAnalyzerClient,
    triage: TriageResult,
    index: BundleIndex,
    context_injector: ContextInjector,
) -> AnalystOutput:
    """Analyze ALL nodes with issues up to limit.

    Each individual node analysis is guarded by PER_RESOURCE_TIMEOUT to prevent
    a single hung LLM call from blocking the rest of the batch.

    Args:
        client: API client for Claude calls.
        triage: Triage results with node issues.
        index: Bundle index.
        context_injector: ISV context injector.

    Returns:
        Merged AnalystOutput combining all node analyses.
    """
    from bundle_analyzer.ai.analysts.node_analyst import NodeAnalyst

    if not triage.node_issues:
        return empty_analyst_output("node", "No node issues to analyze")

    # Deduplicate by node name
    seen = set()
    unique_nodes = []
    for node in triage.node_issues:
        if node.node_name not in seen:
            seen.add(node.node_name)
            unique_nodes.append(node)

    nodes_to_analyze = unique_nodes[:MAX_NODES_TO_ANALYZE]
    logger.info(
        "NodeAnalyst: analyzing {}/{} failing nodes",
        len(nodes_to_analyze), len(unique_nodes),
    )

    analyst = NodeAnalyst()
    tasks = []
    for target in nodes_to_analyze:
        node_data = find_node_json(target.node_name, index)
        if node_data:
            coro = analyst.analyze(client, node_data, index, context_injector=context_injector)
            tasks.append(_analyze_with_timeout(coro, target.node_name))
        else:
            logger.warning("Node JSON not found for {}", target.node_name)

    if not tasks:
        return empty_analyst_output("node", "No node JSON found in bundle")

    results = await asyncio.gather(*tasks, return_exceptions=True)
    outputs = []
    for result in results:
        if isinstance(result, AnalystOutput):
            outputs.append(result)
        elif isinstance(result, Exception):
            logger.error("Node analyst failed for a node: {}", result)
        # None results come from _analyze_with_timeout on timeout — already logged

    return _merge_analyst_outputs(outputs, "node")


async def run_single_analyst(
    analyst_type: str,
    client: BundleAnalyzerClient,
    triage: TriageResult,
    index: BundleIndex,
    context_injector: ContextInjector,
) -> AnalystOutput:
    """Run a single analyst and return its output.

    Args:
        analyst_type: Currently only "config" uses this path.
        client: API client for Claude calls.
        triage: Triage results.
        index: Bundle index.
        context_injector: ISV context injector.

    Returns:
        Structured analyst output.
    """
    try:
        if analyst_type == "config":
            from bundle_analyzer.ai.analysts.config_analyst import ConfigAnalyst
            analyst = ConfigAnalyst()
            return await analyst.analyze(client, triage, index, context_injector=context_injector)
        else:
            raise ValueError(f"Unknown analyst type: {analyst_type}")
    except (ImportError, AttributeError) as exc:
        logger.warning("{} analyst not yet implemented: {}", analyst_type, exc)
        return AnalystOutput(
            analyst=analyst_type,
            findings=[],
            root_cause=None,
            confidence=0.0,
            evidence=[],
            remediation=[],
            uncertainty=[f"{analyst_type} analyst not available: {exc}"],
        )
