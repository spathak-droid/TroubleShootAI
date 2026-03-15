"""Regression test runner for bundle analyzer triage fixtures.

Discovers all fixture bundles under tests/fixtures/bundles/, runs the
full TriageEngine against each one, and asserts:
1. Expected issue types are detected
2. Correct resources are flagged
3. Confidence scores are within expected ranges
4. No false positive issue types appear
5. Every finding has evidence grounding (source_file + evidence_excerpt)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.rca.hypothesis_engine import HypothesisEngine
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


def _collect_all_findings(result) -> list[dict]:
    """Extract all findings with their evidence fields."""
    findings = []

    for p in list(result.critical_pods) + list(result.warning_pods):
        findings.append({
            "scanner": "PodScanner",
            "type": p.issue_type,
            "resource": f"{p.namespace}/{p.pod_name}",
            "source_file": p.source_file,
            "evidence_excerpt": p.evidence_excerpt,
            "confidence": p.confidence,
        })

    for n in result.node_issues:
        findings.append({
            "scanner": "NodeScanner",
            "type": n.condition,
            "resource": n.node_name,
            "source_file": n.source_file,
            "evidence_excerpt": n.evidence_excerpt,
            "confidence": n.confidence,
        })

    for d in result.deployment_issues:
        findings.append({
            "scanner": "DeploymentScanner",
            "type": "deployment_mismatch",
            "resource": f"{d.namespace}/{d.name}",
            "source_file": d.source_file,
            "evidence_excerpt": d.evidence_excerpt,
            "confidence": d.confidence,
        })

    for c in result.config_issues:
        findings.append({
            "scanner": "ConfigScanner",
            "type": c.issue,
            "resource": f"{c.namespace}/{c.resource_name}",
            "source_file": c.source_file,
            "evidence_excerpt": c.evidence_excerpt,
            "confidence": c.confidence,
        })

    for dns in result.dns_issues:
        findings.append({
            "scanner": "DNSScanner",
            "type": dns.issue_type,
            "resource": f"{dns.namespace}/{dns.resource_name}",
            "source_file": dns.source_file,
            "evidence_excerpt": dns.evidence_excerpt,
            "confidence": dns.confidence,
        })

    for tls in result.tls_issues:
        findings.append({
            "scanner": "TLSScanner",
            "type": tls.issue_type,
            "resource": f"{tls.namespace}/{tls.resource_name}",
            "source_file": tls.source_file,
            "evidence_excerpt": tls.evidence_excerpt,
            "confidence": tls.confidence,
        })

    for sched in result.scheduling_issues:
        findings.append({
            "scanner": "SchedulingScanner",
            "type": sched.issue_type,
            "resource": f"{sched.namespace}/{sched.pod_name}",
            "source_file": sched.source_file,
            "evidence_excerpt": sched.evidence_excerpt,
            "confidence": sched.confidence,
        })

    for s in result.storage_issues:
        findings.append({
            "scanner": "StorageScanner",
            "type": s.issue,
            "resource": f"{s.namespace}/{s.resource_name}",
            "source_file": s.source_file,
            "evidence_excerpt": s.evidence_excerpt,
            "confidence": s.confidence,
        })

    for dr in result.drift_issues:
        findings.append({
            "scanner": "DriftScanner",
            "type": dr.field,
            "resource": f"{dr.namespace}/{dr.name}",
            "source_file": dr.source_file,
            "evidence_excerpt": dr.evidence_excerpt,
            "confidence": dr.confidence,
        })

    for pr in result.probe_issues:
        findings.append({
            "scanner": "ProbeScanner",
            "type": pr.issue,
            "resource": f"{pr.namespace}/{pr.pod_name}",
            "source_file": pr.source_file,
            "evidence_excerpt": pr.evidence_excerpt,
            "confidence": pr.confidence,
        })

    for r in result.resource_issues:
        findings.append({
            "scanner": "ResourceScanner",
            "type": r.issue,
            "resource": f"{r.namespace}/{r.pod_name}",
            "source_file": r.source_file,
            "evidence_excerpt": r.evidence_excerpt,
            "confidence": r.confidence,
        })

    for ing in result.ingress_issues:
        findings.append({
            "scanner": "IngressScanner",
            "type": ing.issue,
            "resource": f"{ing.namespace}/{ing.ingress_name}",
            "source_file": ing.source_file,
            "evidence_excerpt": ing.evidence_excerpt,
            "confidence": ing.confidence,
        })

    for q in result.quota_issues:
        findings.append({
            "scanner": "QuotaScanner",
            "type": q.issue_type,
            "resource": f"{q.namespace}/{q.resource_name}",
            "source_file": q.source_file,
            "evidence_excerpt": q.evidence_excerpt,
            "confidence": q.confidence,
        })

    for np_iss in result.network_policy_issues:
        findings.append({
            "scanner": "NetworkPolicyScanner",
            "type": np_iss.issue_type,
            "resource": f"{np_iss.namespace}/{np_iss.policy_name}",
            "source_file": np_iss.source_file,
            "evidence_excerpt": np_iss.evidence_excerpt,
            "confidence": np_iss.confidence,
        })

    for esc in result.event_escalations:
        findings.append({
            "scanner": "EventScanner",
            "type": esc.escalation_type,
            "resource": f"{esc.namespace}/{esc.involved_object_name}",
            "source_file": esc.source_file,
            "evidence_excerpt": esc.evidence_excerpt,
            "confidence": esc.confidence,
        })

    for rbac in result.rbac_issues:
        findings.append({
            "scanner": "RBACScanner",
            "type": "rbac_error",
            "resource": f"{rbac.namespace}/{rbac.resource_type}",
            "source_file": rbac.source_file,
            "evidence_excerpt": rbac.evidence_excerpt,
            "confidence": rbac.confidence,
        })

    return findings


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_dir", get_fixture_dirs(), ids=lambda d: d.name)
async def test_fixture_bundle(fixture_dir: Path) -> None:
    """Run triage on a fixture bundle and verify expected findings."""
    expected = json.loads((fixture_dir / "expected.json").read_text())
    expected_types = set(expected.get("expected_issue_types", []))

    index = await BundleIndex.build(fixture_dir)
    engine = TriageEngine()
    result = await engine.run(index)

    findings = _collect_all_findings(result)
    all_issue_types = {f["type"] for f in findings}

    # 1. Validate expected types are present
    if expected_types:
        missing = expected_types - all_issue_types
        assert not missing, (
            f"Fixture '{fixture_dir.name}': missing expected issue types: {missing}. "
            f"Found: {all_issue_types}"
        )

    # 2. Validate minimum count
    expected_min = expected.get("expected_min_count", 0)
    if expected_min > 0:
        total = len(findings)
        assert total >= expected_min, (
            f"Fixture '{fixture_dir.name}': expected at least {expected_min} "
            f"finding(s), got {total}"
        )

    # 3. Validate correct resources are flagged
    expected_resources = expected.get("expected_resources", [])
    if expected_resources:
        found_resources = {f["resource"] for f in findings}
        for res in expected_resources:
            assert res in found_resources, (
                f"Fixture '{fixture_dir.name}': expected resource '{res}' not flagged. "
                f"Found resources: {found_resources}"
            )

    # 4. Validate confidence ranges
    conf_ranges = expected.get("expected_confidence_range", {})
    for issue_type, (low, high) in conf_ranges.items():
        matching = [f for f in findings if f["type"] == issue_type]
        for f in matching:
            assert low <= f["confidence"] <= high, (
                f"Fixture '{fixture_dir.name}': {issue_type} confidence {f['confidence']} "
                f"outside range [{low}, {high}]"
            )

    # 5. Validate no false positives
    absent_types = set(expected.get("expected_absent_types", []))
    false_positives = absent_types & all_issue_types
    assert not false_positives, (
        f"Fixture '{fixture_dir.name}': false positive issue types detected: {false_positives}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_dir", get_fixture_dirs(), ids=lambda d: d.name)
async def test_evidence_grounding(fixture_dir: Path) -> None:
    """Every finding must have source_file and evidence_excerpt populated."""
    index = await BundleIndex.build(fixture_dir)
    engine = TriageEngine()
    result = await engine.run(index)

    findings = _collect_all_findings(result)

    for f in findings:
        assert f["source_file"] is not None, (
            f"Fixture '{fixture_dir.name}': {f['scanner']} finding for "
            f"{f['resource']} ({f['type']}) has source_file=None"
        )
        assert f["evidence_excerpt"] is not None, (
            f"Fixture '{fixture_dir.name}': {f['scanner']} finding for "
            f"{f['resource']} ({f['type']}) has evidence_excerpt=None"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_dir", get_fixture_dirs(), ids=lambda d: d.name)
async def test_confidence_valid(fixture_dir: Path) -> None:
    """All confidence scores must be > 0 and <= 1.0."""
    index = await BundleIndex.build(fixture_dir)
    engine = TriageEngine()
    result = await engine.run(index)

    findings = _collect_all_findings(result)

    for f in findings:
        assert 0 < f["confidence"] <= 1.0, (
            f"Fixture '{fixture_dir.name}': {f['scanner']} finding for "
            f"{f['resource']} has invalid confidence: {f['confidence']}"
        )
