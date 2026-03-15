"""Analyst steps — run pod, node, and config analysts in parallel."""

from __future__ import annotations

import asyncio

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.ai.context_injector import ContextInjector
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import AnalystOutput, TriageResult

from bundle_analyzer.ai.orchestration.helpers import (
    empty_analyst_output,
    find_node_json,
    find_pod_json,
)


async def run_analysts_parallel(
    client: BundleAnalyzerClient,
    triage: TriageResult,
    index: BundleIndex,
    context_injector: ContextInjector,
) -> list[AnalystOutput]:
    """Run pod, node, and config analysts concurrently.

    Args:
        client: API client for Claude calls.
        triage: Triage results for analyst input.
        index: Bundle index for reading resources.
        context_injector: ISV context for prompt augmentation.

    Returns:
        List of analyst outputs (may be fewer than 3 if some fail).
    """
    tasks = []

    # Pod analyst
    if triage.critical_pods or triage.warning_pods:
        tasks.append(run_single_analyst("pod", client, triage, index, context_injector))

    # Node analyst
    if triage.node_issues:
        tasks.append(run_single_analyst("node", client, triage, index, context_injector))

    # Config analyst
    if triage.config_issues or triage.drift_issues:
        tasks.append(run_single_analyst("config", client, triage, index, context_injector))

    if not tasks:
        logger.info("No analysts needed — triage found no issues requiring AI analysis")
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    outputs: list[AnalystOutput] = []
    for result in results:
        if isinstance(result, AnalystOutput):
            outputs.append(result)
        elif isinstance(result, Exception):
            logger.error("Analyst failed: {}", result)
    return outputs


async def run_single_analyst(
    analyst_type: str,
    client: BundleAnalyzerClient,
    triage: TriageResult,
    index: BundleIndex,
    context_injector: ContextInjector,
) -> AnalystOutput:
    """Run a single analyst and return its output.

    Args:
        analyst_type: One of "pod", "node", "config".
        client: API client for Claude calls.
        triage: Triage results.
        index: Bundle index.
        context_injector: ISV context injector.

    Returns:
        Structured analyst output.
    """
    try:
        if analyst_type == "pod":
            from bundle_analyzer.ai.analysts.pod_analyst import PodAnalyst
            analyst = PodAnalyst()
            # PodAnalyst works per-pod; analyze the first critical or warning pod
            all_pods = list(triage.critical_pods) + list(triage.warning_pods)
            if not all_pods:
                return empty_analyst_output("pod", "No pod issues to analyze")
            # Find the pod JSON from the bundle for the first critical pod
            target = all_pods[0]
            pod_data = find_pod_json(target.namespace, target.pod_name, index)
            if not pod_data:
                return empty_analyst_output("pod", f"Pod JSON not found for {target.namespace}/{target.pod_name}")
            return await analyst.analyze(client, pod_data, index, context_injector=context_injector)
        elif analyst_type == "node":
            from bundle_analyzer.ai.analysts.node_analyst import NodeAnalyst
            analyst = NodeAnalyst()
            # NodeAnalyst works per-node
            if not triage.node_issues:
                return empty_analyst_output("node", "No node issues to analyze")
            target = triage.node_issues[0]
            node_data = find_node_json(target.node_name, index)
            if not node_data:
                return empty_analyst_output("node", f"Node JSON not found for {target.node_name}")
            return await analyst.analyze(client, node_data, index, context_injector=context_injector)
        elif analyst_type == "config":
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
