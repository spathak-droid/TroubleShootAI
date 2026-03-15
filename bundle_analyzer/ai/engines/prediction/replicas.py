"""Replica exhaustion prediction functions.

Predicts when deployments will run out of schedulable replicas
by checking ready vs desired counts and degradation trends.
"""

from __future__ import annotations

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import PredictedFailure


def predict_replica_exhaustion(
    index: BundleIndex,
) -> list[PredictedFailure]:
    """Predict when deployments will run out of schedulable replicas.

    Checks deployments where ready < desired and estimates if the
    situation is degrading or stable.

    Args:
        index: The indexed support bundle.

    Returns:
        List of PredictedFailure objects for replica-related predictions.
    """
    predictions: list[PredictedFailure] = []
    deployments_dir = index.root / "cluster-resources" / "deployments"

    if not deployments_dir.is_dir():
        return predictions

    for ns_dir in sorted(deployments_dir.iterdir()):
        if not ns_dir.is_dir():
            continue

        for deploy_file in sorted(ns_dir.glob("*.json")):
            rel = str(deploy_file.relative_to(index.root))
            data = index.read_json(rel)
            if not isinstance(data, dict):
                continue

            # Handle items-wrapped lists (common in troubleshoot.sh bundles)
            if "items" in data:
                items = data["items"]
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict):
                        prediction = predict_replica_exhaustion_single(item)
                        if prediction:
                            predictions.append(prediction)
            else:
                prediction = predict_replica_exhaustion_single(data)
                if prediction:
                    predictions.append(prediction)

    return predictions


def predict_replica_exhaustion_single(
    deployment_json: dict,
) -> PredictedFailure | None:
    """Predict replica exhaustion for a single deployment.

    Args:
        deployment_json: Deployment JSON with spec and status.

    Returns:
        PredictedFailure if capacity is degrading, or None.
    """
    metadata = deployment_json.get("metadata", {})
    deploy_name = metadata.get("name", "unknown")
    namespace = metadata.get("namespace", "unknown")
    spec = deployment_json.get("spec", {})
    status = deployment_json.get("status", {})

    desired = spec.get("replicas", 0)
    ready = status.get("readyReplicas", 0) or 0
    status.get("availableReplicas", 0) or 0
    unavailable = status.get("unavailableReplicas", 0) or 0

    if desired == 0:
        return None

    ready_ratio = ready / desired if desired > 0 else 1.0

    if ready_ratio < 1.0 and unavailable > 0:
        if ready == 0:
            return PredictedFailure(
                resource=f"deployment/{namespace}/{deploy_name}",
                failure_type="TOTAL_REPLICA_FAILURE",
                estimated_eta_seconds=None,
                confidence=0.95,
                evidence=[
                    f"0/{desired} replicas ready",
                    f"{unavailable} replicas unavailable",
                ],
                prevention=(
                    f"Investigate why no replicas are ready: "
                    f"kubectl describe deployment {deploy_name} -n {namespace}"
                ),
            )
        elif ready_ratio <= 0.5:
            return PredictedFailure(
                resource=f"deployment/{namespace}/{deploy_name}",
                failure_type="REPLICA_DEGRADATION",
                estimated_eta_seconds=None,
                confidence=0.7,
                evidence=[
                    f"{ready}/{desired} replicas ready ({ready_ratio:.0%})",
                    f"{unavailable} replicas unavailable",
                ],
                prevention=(
                    f"Deployment {deploy_name} is degraded. Check pod events: "
                    f"kubectl get pods -l app={deploy_name} -n {namespace}"
                ),
            )

    return None
