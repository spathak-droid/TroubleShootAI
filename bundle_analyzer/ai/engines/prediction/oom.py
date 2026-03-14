"""OOM prediction functions.

Predicts OOM kills by comparing memory usage to limits and
estimating time until OOM from growth rates.
"""

from __future__ import annotations

from typing import Optional

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import PredictedFailure

from .helpers import parse_k8s_memory


def predict_oom_from_pods(index: BundleIndex) -> list[PredictedFailure]:
    """Predict OOM kills by comparing memory usage to limits.

    Looks at pods with memory limits set and current usage data
    (from metrics or status) to estimate time until OOM.

    Args:
        index: The indexed support bundle.

    Returns:
        List of PredictedFailure objects for OOM-related predictions.
    """
    predictions: list[PredictedFailure] = []

    for pod in index.get_all_pods():
        metadata = pod.get("metadata", {})
        pod_name = metadata.get("name", "unknown")
        namespace = metadata.get("namespace", "unknown")
        resource = f"pod/{namespace}/{pod_name}"

        spec = pod.get("spec", {})
        status = pod.get("status", {})

        for container_spec in spec.get("containers", []):
            container_name = container_spec.get("name", "unknown")
            limits = container_spec.get("resources", {}).get("limits", {})
            memory_limit_str = limits.get("memory")

            if not memory_limit_str:
                continue

            memory_limit_bytes = parse_k8s_memory(memory_limit_str)
            if memory_limit_bytes is None or memory_limit_bytes == 0:
                continue

            # Check if container has had previous OOM kills
            for cs in status.get("containerStatuses", []) or []:
                if cs.get("name") != container_name:
                    continue

                restart_count = cs.get("restartCount", 0)
                last_state = cs.get("lastState", {})
                terminated = last_state.get("terminated", {})
                reason = terminated.get("reason", "")
                exit_code = terminated.get("exitCode")

                if reason == "OOMKilled" or exit_code == 137:
                    # Already OOM'd -- predict recurrence
                    if restart_count >= 2:
                        predictions.append(
                            PredictedFailure(
                                resource=f"{resource}/{container_name}",
                                failure_type="OOM_RECURRENCE",
                                estimated_eta_seconds=None,  # already happening
                                confidence=0.9,
                                evidence=[
                                    f"Container {container_name} OOM killed "
                                    f"with {restart_count} restarts",
                                    f"Memory limit: {memory_limit_str}",
                                    f"Last exit code: {exit_code}",
                                ],
                                prevention=(
                                    f"Increase memory limit for container "
                                    f"{container_name} (currently {memory_limit_str}), "
                                    f"or investigate memory leak in the application"
                                ),
                            )
                        )

    return predictions


def predict_oom(
    pod_json: dict, metrics: dict | None = None
) -> Optional[PredictedFailure]:
    """Estimate OOM ETA from memory growth rate for a single pod.

    Args:
        pod_json: Pod JSON with spec and status.
        metrics: Optional metrics dict with memory usage data.

    Returns:
        A PredictedFailure if OOM is predicted, or None.
    """
    metadata = pod_json.get("metadata", {})
    pod_name = metadata.get("name", "unknown")
    namespace = metadata.get("namespace", "unknown")
    resource = f"pod/{namespace}/{pod_name}"

    spec = pod_json.get("spec", {})

    for container_spec in spec.get("containers", []):
        container_name = container_spec.get("name", "unknown")
        limits = container_spec.get("resources", {}).get("limits", {})
        memory_limit_str = limits.get("memory")

        if not memory_limit_str:
            continue

        memory_limit_bytes = parse_k8s_memory(memory_limit_str)
        if memory_limit_bytes is None:
            continue

        # If we have metrics, estimate growth
        if metrics:
            current_usage = metrics.get("memory_bytes", 0)
            if current_usage > 0 and memory_limit_bytes > 0:
                usage_pct = current_usage / memory_limit_bytes
                if usage_pct > 0.8:
                    remaining = memory_limit_bytes - current_usage
                    # Rough estimate: assume linear growth at 1% per minute
                    eta_seconds = int(remaining / (memory_limit_bytes * 0.01 / 60))
                    return PredictedFailure(
                        resource=f"{resource}/{container_name}",
                        failure_type="OOM_PREDICTED",
                        estimated_eta_seconds=max(eta_seconds, 0),
                        confidence=0.6,
                        evidence=[
                            f"Memory usage at {usage_pct:.0%} of limit",
                            f"Limit: {memory_limit_str}",
                        ],
                        prevention=(
                            f"Increase memory limit or reduce memory consumption "
                            f"for {container_name}"
                        ),
                    )

    return None
