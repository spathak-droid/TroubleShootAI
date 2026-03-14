"""Issue walker functions for pods, deployments, and nodes.

Each function walks a specific triage issue type and produces a CausalChain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bundle_analyzer.models import (
    CausalChain,
    CausalStep,
    DeploymentIssue,
    NodeIssue,
    PodIssue,
    TriageResult,
)

from .constants import _gen_id
from .data_access import check_config_issues, find_pod_json, find_related_events
from .deployment_helpers import find_biggest_consumer, find_deployment_pods, find_pods_on_node
from .pattern_walkers import walk_crash_loop, walk_pending

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


async def walk_pod_issue(
    issue: PodIssue,
    index: BundleIndex,
    triage: TriageResult,
    pod_cache: dict[str, dict],
) -> CausalChain | None:
    """Walk a single pod issue to produce a causal chain.

    Implements Pattern 1 (CrashLoopBackOff) and Pattern 2 (Pending).

    Args:
        issue: The pod issue from triage.
        index: The bundle index for reading raw Kubernetes JSON.
        triage: The triage results.
        pod_cache: The pre-built pod cache.

    Returns:
        A CausalChain tracing the symptom, or None if no chain produced.
    """
    resource_key = f"Pod/{issue.namespace}/{issue.pod_name}"
    evidence_file = f"cluster-resources/pods/{issue.namespace}.json"

    steps: list[CausalStep] = []
    root_cause: str | None = None
    confidence = 0.0
    needs_ai = False
    related: list[str] = []

    pod_json = find_pod_json(pod_cache, issue.namespace, issue.pod_name)

    # Initial symptom step
    steps.append(CausalStep(
        resource=resource_key,
        observation=f"Pod is in {issue.issue_type} state (restarts: {issue.restart_count})",
        evidence_file=evidence_file,
        evidence_excerpt=f"issue_type: {issue.issue_type}, message: {issue.message}",
    ))

    if issue.issue_type == "Pending":
        root_cause, confidence = walk_pending(
            issue, pod_json, steps, related, evidence_file, triage,
        )
    elif issue.issue_type in ("CrashLoopBackOff", "OOMKilled"):
        root_cause, confidence, needs_ai = walk_crash_loop(
            issue, pod_json, steps, related, evidence_file, index, triage,
        )
    elif issue.issue_type == "ImagePullBackOff":
        steps.append(CausalStep(
            resource=resource_key,
            observation="Image pull is failing",
            evidence_file=evidence_file,
            evidence_excerpt=issue.message,
        ))
        root_cause = f"Image pull failure: {issue.message}"
        confidence = 0.85
    elif issue.issue_type == "CreateContainerConfigError":
        config_issues = check_config_issues(triage, issue.namespace, issue.pod_name)
        if config_issues:
            ci = config_issues[0]
            steps.append(CausalStep(
                resource=resource_key,
                observation=f"Missing {ci.resource_type} '{ci.resource_name}'",
                evidence_file=evidence_file,
                evidence_excerpt=f"referenced_by: {ci.referenced_by}, issue: {ci.issue}",
            ))
            root_cause = f"Missing {ci.resource_type} '{ci.resource_name}' referenced by pod"
            confidence = 0.9
        else:
            root_cause = f"Container config error: {issue.message}"
            confidence = 0.6
            needs_ai = True
    else:
        # Generic fallback for other issue types
        root_cause = issue.message or f"{issue.issue_type} detected"
        confidence = 0.4
        needs_ai = True

    # Check for warning events
    events = find_related_events(index, issue.namespace, issue.pod_name)
    for ev in events[:3]:
        steps.append(CausalStep(
            resource=resource_key,
            observation=f"Event: {ev.get('reason', 'Unknown')} — {ev.get('message', '')}",
            evidence_file=f"cluster-resources/events/{issue.namespace}.json",
            evidence_excerpt=f"type: {ev.get('type')}, count: {ev.get('count', 1)}",
        ))

    # Check for config cascade (Pattern 5)
    config_issues = check_config_issues(triage, issue.namespace, issue.pod_name)
    for ci in config_issues:
        related.append(f"{ci.resource_type}/{ci.namespace}/{ci.resource_name}")

    return CausalChain(
        id=_gen_id(),
        symptom=f"Pod {issue.pod_name} is in {issue.issue_type}",
        symptom_resource=resource_key,
        steps=steps,
        root_cause=root_cause,
        confidence=confidence,
        ambiguous=confidence < 0.5,
        needs_ai=needs_ai,
        related_resources=related,
    )


async def walk_deployment_issue(
    issue: DeploymentIssue,
    index: BundleIndex,
    triage: TriageResult,
    pod_cache: dict[str, dict],
) -> CausalChain | None:
    """Walk a deployment issue by examining its owned pods.

    Implements Pattern 3 (Deployment unavailable): finds all pods owned
    by the deployment and aggregates their individual root causes.

    Args:
        issue: The deployment issue from triage.
        index: The bundle index for reading raw Kubernetes JSON.
        triage: The triage results.
        pod_cache: The pre-built pod cache.

    Returns:
        A CausalChain for the deployment, or None if no chain produced.
    """
    resource_key = f"Deployment/{issue.namespace}/{issue.name}"
    evidence_file = f"cluster-resources/deployments/{issue.namespace}.json"

    steps: list[CausalStep] = [
        CausalStep(
            resource=resource_key,
            observation=f"Deployment has {issue.ready_replicas}/{issue.desired_replicas} replicas ready",
            evidence_file=evidence_file,
            evidence_excerpt=issue.issue,
        ),
    ]

    # Find pods that belong to this deployment
    related_pods = find_deployment_pods(triage, pod_cache, issue.namespace, issue.name)
    related: list[str] = []
    pod_root_causes: list[str] = []

    for pod_issue in related_pods:
        pod_chain = await walk_pod_issue(pod_issue, index, triage, pod_cache)
        if pod_chain is not None and pod_chain.root_cause:
            pod_root_causes.append(pod_chain.root_cause)
            related.append(pod_chain.symptom_resource)
            # Add a summary step from the pod chain
            steps.append(CausalStep(
                resource=f"Pod/{pod_issue.namespace}/{pod_issue.pod_name}",
                observation=f"Owned pod failing: {pod_chain.root_cause}",
                evidence_file=f"cluster-resources/pods/{pod_issue.namespace}.json",
                evidence_excerpt=f"root_cause: {pod_chain.root_cause}",
            ))

    unique_causes = list(set(pod_root_causes))
    ambiguous = len(unique_causes) > 1

    if len(unique_causes) == 1:
        root_cause = unique_causes[0]
        confidence = 0.8
    elif len(unique_causes) > 1:
        root_cause = f"Multiple causes: {'; '.join(unique_causes[:3])}"
        confidence = 0.5
    else:
        root_cause = f"Deployment {issue.name} unavailable: {issue.issue}"
        confidence = 0.4

    if issue.stuck_rollout:
        steps.append(CausalStep(
            resource=resource_key,
            observation="Deployment rollout appears stuck",
            evidence_file=evidence_file,
            evidence_excerpt="stuck_rollout: true",
        ))

    return CausalChain(
        id=_gen_id(),
        symptom=f"Deployment {issue.name} has {issue.issue}",
        symptom_resource=resource_key,
        steps=steps,
        root_cause=root_cause,
        confidence=confidence,
        ambiguous=ambiguous,
        needs_ai=ambiguous,
        related_resources=related,
    )


async def walk_node_issue(
    issue: NodeIssue,
    triage: TriageResult,
    pod_cache: dict[str, dict],
) -> CausalChain | None:
    """Walk a node issue by checking resource pressure and pod scheduling.

    Implements Pattern 4 (Node pressure): examines the node's conditions,
    lists pods scheduled on the node, and checks for overcommitment.

    Args:
        issue: The node issue from triage.
        triage: The triage results.
        pod_cache: The pre-built pod cache.

    Returns:
        A CausalChain for the node issue, or None if no chain produced.
    """
    resource_key = f"Node/{issue.node_name}"
    evidence_file = "cluster-resources/nodes.json"

    steps: list[CausalStep] = [
        CausalStep(
            resource=resource_key,
            observation=f"Node condition: {issue.condition}",
            evidence_file=evidence_file,
            evidence_excerpt=f"condition: {issue.condition}, message: {issue.message}",
        ),
    ]

    related: list[str] = []

    # Find all pods on this node
    pods_on_node = find_pods_on_node(pod_cache, issue.node_name)
    if pods_on_node:
        steps.append(CausalStep(
            resource=resource_key,
            observation=f"{len(pods_on_node)} pods scheduled on this node",
            evidence_file="cluster-resources/pods/",
            evidence_excerpt=f"pods: {', '.join(p['name'] for p in pods_on_node[:5])}",
        ))
        for p in pods_on_node:
            related.append(f"Pod/{p.get('namespace', 'unknown')}/{p['name']}")

    # Check for biggest resource consumer
    biggest = find_biggest_consumer(pods_on_node)
    if biggest:
        steps.append(CausalStep(
            resource=f"Pod/{biggest.get('namespace', 'unknown')}/{biggest['name']}",
            observation=f"Largest resource consumer on node: {biggest.get('resource_desc', 'unknown')}",
            evidence_file=f"cluster-resources/pods/{biggest.get('namespace', 'default')}.json",
            evidence_excerpt=biggest.get("resource_desc", ""),
        ))

    root_cause: str | None
    confidence: float

    if issue.condition == "MemoryPressure":
        root_cause = f"Node {issue.node_name} under memory pressure"
        if biggest:
            root_cause += f" (largest consumer: {biggest['name']})"
        confidence = 0.75
    elif issue.condition == "DiskPressure":
        root_cause = f"Node {issue.node_name} under disk pressure"
        confidence = 0.75
    elif issue.condition == "NotReady":
        root_cause = f"Node {issue.node_name} is NotReady: {issue.message}"
        confidence = 0.5
    elif issue.condition == "Unschedulable":
        root_cause = f"Node {issue.node_name} is cordoned/unschedulable"
        confidence = 0.9
    else:
        root_cause = f"Node {issue.node_name} has {issue.condition}"
        confidence = 0.5

    return CausalChain(
        id=_gen_id(),
        symptom=f"Node {issue.node_name} has {issue.condition}",
        symptom_resource=resource_key,
        steps=steps,
        root_cause=root_cause,
        confidence=confidence,
        ambiguous=False,
        needs_ai=issue.condition == "NotReady",
        related_resources=related,
    )
