"""Regression test runner for bundle analyzer triage fixtures.

Discovers all fixture bundles under tests/fixtures/bundles/, runs the
full TriageEngine against each one, and asserts that expected issue types
are detected. Uses pytest parametrize so each fixture is a separate test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.triage.engine import TriageEngine

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "bundles"


def get_fixture_dirs() -> list[Path]:
    """Discover all fixture bundle directories that contain an expected.json."""
    if not FIXTURES_DIR.exists():
        return []
    return [
        d
        for d in sorted(FIXTURES_DIR.iterdir())
        if d.is_dir() and (d / "expected.json").exists()
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_dir", get_fixture_dirs(), ids=lambda d: d.name)
async def test_fixture_bundle(fixture_dir: Path) -> None:
    """Run triage on a fixture bundle and verify expected findings.

    For each fixture directory:
    1. Build a BundleIndex from the directory (handles missing subdirs gracefully).
    2. Run the full TriageEngine.
    3. Load expected.json and check that every expected issue type appears
       somewhere in the triage result.
    """
    expected = json.loads((fixture_dir / "expected.json").read_text())
    expected_types = set(expected.get("expected_issue_types", []))

    # If no issue types are expected, we just verify no crash and optionally
    # that the result is clean.
    index = await BundleIndex.build(fixture_dir)
    engine = TriageEngine()
    result = await engine.run(index)

    # Collect all issue types found across every scanner output
    all_issue_types: set[str] = set()

    # Pod issues (critical + warning)
    for pod_issue in result.critical_pods + result.warning_pods:
        all_issue_types.add(pod_issue.issue_type)

    # Node issues
    for node_issue in result.node_issues:
        all_issue_types.add(node_issue.condition)

    # Deployment issues
    for dep_issue in result.deployment_issues:
        all_issue_types.add(dep_issue.issue)

    # Config issues
    for cfg_issue in result.config_issues:
        all_issue_types.add(cfg_issue.issue)

    # Drift issues
    for drift in result.drift_issues:
        all_issue_types.add(drift.field)

    # Probe issues
    for probe in result.probe_issues:
        all_issue_types.add(probe.issue)

    # Resource issues
    for res in result.resource_issues:
        all_issue_types.add(res.issue)

    # Ingress issues
    for ing in result.ingress_issues:
        all_issue_types.add(ing.issue)

    # Storage issues
    for stor in result.storage_issues:
        all_issue_types.add(stor.issue)

    # RBAC issues
    for rbac in result.rbac_issues:
        all_issue_types.add(rbac.resource_type)

    # Quota issues
    for quota in result.quota_issues:
        all_issue_types.add(quota.issue_type)

    # Network policy issues
    for np in result.network_policy_issues:
        all_issue_types.add(np.issue_type)

    # DNS issues
    for dns in result.dns_issues:
        all_issue_types.add(dns.issue_type)

    # TLS issues
    for tls in result.tls_issues:
        all_issue_types.add(tls.issue_type)

    # Scheduling issues
    for sched in result.scheduling_issues:
        all_issue_types.add(sched.issue_type)

    # Event escalations
    for esc in result.event_escalations:
        all_issue_types.add(esc.escalation_type)

    # Crash contexts
    for ctx in result.crash_contexts:
        if hasattr(ctx, "issue_type"):
            all_issue_types.add(ctx.issue_type)

    # Validate expected types are present
    if not expected_types:
        # Fixture expects no issues (e.g., tls_expired with healthy pod).
        # We still ran the engine successfully — that is the test.
        return

    missing = expected_types - all_issue_types
    assert not missing, (
        f"Fixture '{fixture_dir.name}': missing expected issue types: {missing}. "
        f"Found: {all_issue_types}"
    )

    # Validate minimum count if specified
    expected_min = expected.get("expected_min_count", 0)
    if expected_min > 0:
        total_findings = (
            len(result.critical_pods)
            + len(result.warning_pods)
            + len(result.node_issues)
            + len(result.deployment_issues)
            + len(result.config_issues)
            + len(result.dns_issues)
            + len(result.tls_issues)
            + len(result.scheduling_issues)
            + len(result.storage_issues)
        )
        assert total_findings >= expected_min, (
            f"Fixture '{fixture_dir.name}': expected at least {expected_min} "
            f"finding(s), got {total_findings}"
        )
