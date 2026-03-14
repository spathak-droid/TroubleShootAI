"""Cross-container correlation detection.

Finds temporal correlations between containers in the same pod,
including sidecar failures preceding main container errors and
shared dependency failures.
"""

from __future__ import annotations

from datetime import datetime

from bundle_analyzer.models import CrossContainerCorrelation, LogIntelligence


def correlate_containers(
    container_intels: list[LogIntelligence],
) -> list[CrossContainerCorrelation]:
    """Find correlations between containers in the same pod.

    Detects two correlation types:
    1. Sidecar errors that precede main container errors (within 30s).
    2. Shared dependency failures (same pattern in multiple containers).

    Args:
        container_intels: LogIntelligence results for each container.

    Returns:
        List of detected cross-container correlations.
    """
    correlations: list[CrossContainerCorrelation] = []

    # Build error timeline per container
    error_timelines: dict[str, list[tuple[datetime, str]]] = {}
    for ci in container_intels:
        errors: list[tuple[datetime, str]] = []
        for pf in ci.top_patterns:
            if pf.first_seen and pf.count > 0:
                errors.append((pf.first_seen, pf.pattern))
        error_timelines[ci.container_name] = sorted(errors)

    # Check for sidecar errors preceding main container errors
    main_containers = [c for c in container_intels if not c.is_sidecar]
    sidecar_containers = [c for c in container_intels if c.is_sidecar]

    for main in main_containers:
        main_errors = error_timelines.get(main.container_name, [])
        for sidecar in sidecar_containers:
            sidecar_errors = error_timelines.get(sidecar.container_name, [])

            for main_ts, main_err in main_errors:
                for sc_ts, sc_err in sidecar_errors:
                    delta = (main_ts - sc_ts).total_seconds()
                    if 0 < delta < 30:  # sidecar error happened 0-30s before main
                        correlations.append(CrossContainerCorrelation(
                            source_container=sidecar.container_name,
                            target_container=main.container_name,
                            source_event=sc_err,
                            target_event=main_err,
                            time_delta_seconds=delta,
                            correlation_type="sidecar_failure_precedes_main",
                        ))

    # Shared dependency failures (same pattern category in multiple containers)
    if len(container_intels) >= 2:
        pattern_by_container: dict[str, set[str]] = {}
        for ci in container_intels:
            cats = {pf.pattern for pf in ci.top_patterns}
            pattern_by_container[ci.container_name] = cats

        names = list(pattern_by_container.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                shared = pattern_by_container[names[i]] & pattern_by_container[names[j]]
                for pat in shared:
                    correlations.append(CrossContainerCorrelation(
                        source_container=names[i],
                        target_container=names[j],
                        source_event=pat,
                        target_event=pat,
                        time_delta_seconds=0.0,
                        correlation_type="shared_dependency_failure",
                    ))

    return correlations
