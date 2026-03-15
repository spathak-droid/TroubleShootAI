#!/usr/bin/env python3
"""System validation script — measures evidence grounding, confidence, and correctness.

Runs the triage engine and RCA hypothesis engine against all fixture bundles
and optionally against real support bundles. Produces a structured validation
report showing evidence population rates, confidence distributions, and
finding accuracy.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tarfile
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bundle_analyzer.bundle.indexer import BundleIndex  # noqa: E402
from bundle_analyzer.rca.hypothesis_engine import HypothesisEngine  # noqa: E402
from bundle_analyzer.triage.engine import TriageEngine  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_all_issues(result) -> list[dict]:
    """Extract all issues from a TriageResult as flat dicts with type info."""
    issues = []

    for p in list(result.critical_pods) + list(result.warning_pods):
        issues.append({
            "scanner": "PodScanner",
            "type": p.issue_type,
            "resource": f"{p.namespace}/{p.pod_name}",
            "source_file": p.source_file,
            "evidence_excerpt": p.evidence_excerpt,
            "confidence": p.confidence,
            "message": p.message,
        })

    for n in result.node_issues:
        issues.append({
            "scanner": "NodeScanner",
            "type": n.condition,
            "resource": n.node_name,
            "source_file": n.source_file,
            "evidence_excerpt": n.evidence_excerpt,
            "confidence": n.confidence,
            "message": n.message,
        })

    for d in result.deployment_issues:
        issues.append({
            "scanner": "DeploymentScanner",
            "type": "deployment_mismatch",
            "resource": f"{d.namespace}/{d.name}",
            "source_file": d.source_file,
            "evidence_excerpt": d.evidence_excerpt,
            "confidence": d.confidence,
            "message": d.issue,
        })

    for c in result.config_issues:
        issues.append({
            "scanner": "ConfigScanner",
            "type": c.issue,
            "resource": f"{c.namespace}/{c.resource_name}",
            "source_file": c.source_file,
            "evidence_excerpt": c.evidence_excerpt,
            "confidence": c.confidence,
            "message": f"{c.resource_type} {c.resource_name} {c.issue}",
        })

    for dr in result.drift_issues:
        issues.append({
            "scanner": "DriftScanner",
            "type": "drift",
            "resource": f"{dr.namespace}/{dr.name}",
            "source_file": dr.source_file,
            "evidence_excerpt": dr.evidence_excerpt,
            "confidence": dr.confidence,
            "message": dr.description,
        })

    for pr in result.probe_issues:
        issues.append({
            "scanner": "ProbeScanner",
            "type": pr.issue,
            "resource": f"{pr.namespace}/{pr.pod_name}",
            "source_file": pr.source_file,
            "evidence_excerpt": pr.evidence_excerpt,
            "confidence": pr.confidence,
            "message": pr.message,
        })

    for r in result.resource_issues:
        issues.append({
            "scanner": "ResourceScanner",
            "type": r.issue,
            "resource": f"{r.namespace}/{r.pod_name}",
            "source_file": r.source_file,
            "evidence_excerpt": r.evidence_excerpt,
            "confidence": r.confidence,
            "message": r.message,
        })

    for s in result.storage_issues:
        issues.append({
            "scanner": "StorageScanner",
            "type": s.issue,
            "resource": f"{s.namespace}/{s.resource_name}",
            "source_file": s.source_file,
            "evidence_excerpt": s.evidence_excerpt,
            "confidence": s.confidence,
            "message": s.message,
        })

    for dns in result.dns_issues:
        issues.append({
            "scanner": "DNSScanner",
            "type": dns.issue_type,
            "resource": f"{dns.namespace}/{dns.resource_name}",
            "source_file": dns.source_file,
            "evidence_excerpt": dns.evidence_excerpt,
            "confidence": dns.confidence,
            "message": dns.message,
        })

    for tls in result.tls_issues:
        issues.append({
            "scanner": "TLSScanner",
            "type": tls.issue_type,
            "resource": f"{tls.namespace}/{tls.resource_name}",
            "source_file": tls.source_file,
            "evidence_excerpt": tls.evidence_excerpt,
            "confidence": tls.confidence,
            "message": tls.message,
        })

    for sched in result.scheduling_issues:
        issues.append({
            "scanner": "SchedulingScanner",
            "type": sched.issue_type,
            "resource": f"{sched.namespace}/{sched.pod_name}",
            "source_file": sched.source_file,
            "evidence_excerpt": sched.evidence_excerpt,
            "confidence": sched.confidence,
            "message": sched.message,
        })

    for esc in result.event_escalations:
        issues.append({
            "scanner": "EventScanner",
            "type": esc.escalation_type,
            "resource": f"{esc.namespace}/{esc.involved_object_name}",
            "source_file": esc.source_file,
            "evidence_excerpt": esc.evidence_excerpt,
            "confidence": esc.confidence,
            "message": esc.message,
        })

    for q in result.quota_issues:
        issues.append({
            "scanner": "QuotaScanner",
            "type": q.issue_type,
            "resource": f"{q.namespace}/{q.resource_name}",
            "source_file": q.source_file,
            "evidence_excerpt": q.evidence_excerpt,
            "confidence": q.confidence,
            "message": q.message,
        })

    for np in result.network_policy_issues:
        issues.append({
            "scanner": "NetworkPolicyScanner",
            "type": np.issue_type,
            "resource": f"{np.namespace}/{np.policy_name}",
            "source_file": np.source_file,
            "evidence_excerpt": np.evidence_excerpt,
            "confidence": np.confidence,
            "message": np.message,
        })

    for rbac in result.rbac_issues:
        issues.append({
            "scanner": "RBACScanner",
            "type": "rbac_error",
            "resource": f"{rbac.namespace}/{rbac.resource_type}",
            "source_file": rbac.source_file,
            "evidence_excerpt": rbac.evidence_excerpt,
            "confidence": rbac.confidence,
            "message": rbac.error_message,
        })

    return issues


async def validate_fixture_bundle(fixture_dir: Path) -> dict:
    """Validate a single fixture bundle and return a result dict."""
    expected_path = fixture_dir / "expected.json"
    expected = json.loads(expected_path.read_text()) if expected_path.exists() else {}
    expected_types = set(expected.get("expected_issue_types", []))

    index = await BundleIndex.build(fixture_dir)
    engine = TriageEngine()
    result = await engine.run(index)

    all_issues = _collect_all_issues(result)

    # Check expected types
    found_types = {i["type"] for i in all_issues}
    missing_types = expected_types - found_types
    unexpected_types = found_types - expected_types if expected_types else set()

    # Evidence population analysis
    total = len(all_issues)
    with_source = sum(1 for i in all_issues if i["source_file"])
    with_evidence = sum(1 for i in all_issues if i["evidence_excerpt"])

    # Confidence distribution
    confidences = [i["confidence"] for i in all_issues]
    conf_distribution = {}
    if confidences:
        conf_distribution = {
            "min": min(confidences),
            "max": max(confidences),
            "mean": round(sum(confidences) / len(confidences), 3),
            "all_1.0": all(c == 1.0 for c in confidences),
        }

    # Per-scanner evidence rates
    scanner_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "with_source": 0, "with_evidence": 0})
    for issue in all_issues:
        s = scanner_stats[issue["scanner"]]
        s["total"] += 1
        if issue["source_file"]:
            s["with_source"] += 1
        if issue["evidence_excerpt"]:
            s["with_evidence"] += 1

    # RCA hypothesis analysis
    hyp_engine = HypothesisEngine()
    hypotheses = await hyp_engine.analyze(result)
    hyp_data = [
        {
            "title": h.title,
            "category": h.category,
            "confidence": h.confidence,
            "evidence_count": len(h.supporting_evidence),
            "affected_resources": h.affected_resources,
        }
        for h in hypotheses
    ]

    return {
        "bundle": fixture_dir.name,
        "description": expected.get("description", ""),
        "expected_types": sorted(expected_types),
        "found_types": sorted(found_types),
        "missing_types": sorted(missing_types),
        "unexpected_types": sorted(unexpected_types),
        "total_findings": total,
        "evidence": {
            "with_source_file": with_source,
            "with_evidence_excerpt": with_evidence,
            "source_file_rate": round(with_source / total, 3) if total else 1.0,
            "evidence_excerpt_rate": round(with_evidence / total, 3) if total else 1.0,
        },
        "confidence": conf_distribution,
        "per_scanner": dict(scanner_stats),
        "findings": all_issues,
        "hypotheses": hyp_data,
        "passed": len(missing_types) == 0,
    }


async def validate_real_bundle(tar_path: Path) -> dict:
    """Extract and validate a real support bundle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(tmpdir_path, filter="data")
        except Exception as exc:
            return {"bundle": tar_path.name, "error": str(exc)}

        # Find the actual bundle root (may be nested one level)
        candidates = list(tmpdir_path.iterdir())
        bundle_root = tmpdir_path
        if len(candidates) == 1 and candidates[0].is_dir():
            bundle_root = candidates[0]

        index = await BundleIndex.build(bundle_root)
        engine = TriageEngine()
        result = await engine.run(index)

        all_issues = _collect_all_issues(result)

        # Evidence analysis
        total = len(all_issues)
        with_source = sum(1 for i in all_issues if i["source_file"])
        with_evidence = sum(1 for i in all_issues if i["evidence_excerpt"])

        scanner_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "with_source": 0, "with_evidence": 0})
        for issue in all_issues:
            s = scanner_stats[issue["scanner"]]
            s["total"] += 1
            if issue["source_file"]:
                s["with_source"] += 1
            if issue["evidence_excerpt"]:
                s["with_evidence"] += 1

        confidences = [i["confidence"] for i in all_issues]
        conf_distribution = {}
        if confidences:
            conf_distribution = {
                "min": min(confidences),
                "max": max(confidences),
                "mean": round(sum(confidences) / len(confidences), 3),
                "all_1.0": all(c == 1.0 for c in confidences),
            }

        hyp_engine = HypothesisEngine()
        hypotheses = await hyp_engine.analyze(result)

        return {
            "bundle": tar_path.name,
            "namespaces": index.namespaces,
            "total_findings": total,
            "evidence": {
                "with_source_file": with_source,
                "with_evidence_excerpt": with_evidence,
                "source_file_rate": round(with_source / total, 3) if total else 1.0,
                "evidence_excerpt_rate": round(with_evidence / total, 3) if total else 1.0,
            },
            "confidence": conf_distribution,
            "per_scanner": dict(scanner_stats),
            "findings": all_issues[:50],  # Cap to avoid huge output
            "hypothesis_count": len(hypotheses),
            "hypotheses": [
                {"title": h.title, "confidence": h.confidence, "evidence": len(h.supporting_evidence)}
                for h in hypotheses
            ],
        }


async def main() -> None:
    """Run full system validation."""
    report: dict = {
        "timestamp": datetime.now().isoformat(),
        "fixture_results": [],
        "real_bundle_results": [],
        "summary": {},
    }

    # --- Fixture bundles ---
    fixtures_dir = PROJECT_ROOT / "tests" / "fixtures" / "bundles"
    if fixtures_dir.exists():
        fixture_dirs = sorted(
            d for d in fixtures_dir.iterdir()
            if d.is_dir() and (d / "expected.json").exists()
        )
        print(f"Validating {len(fixture_dirs)} fixture bundles...")
        for fd in fixture_dirs:
            print(f"  {fd.name}...", end=" ", flush=True)
            result = await validate_fixture_bundle(fd)
            report["fixture_results"].append(result)
            status = "PASS" if result["passed"] else "FAIL"
            ev_rate = result["evidence"]["source_file_rate"]
            print(f"{status} | {result['total_findings']} findings | evidence: {ev_rate:.0%} | hyp: {len(result['hypotheses'])}")

    # --- Real bundles ---
    real_bundles = sorted(PROJECT_ROOT.glob("support-bundle-*.tar.gz"))
    if real_bundles:
        print(f"\nValidating {len(real_bundles)} real support bundles...")
        for rb in real_bundles:
            print(f"  {rb.name}...", end=" ", flush=True)
            result = await validate_real_bundle(rb)
            report["real_bundle_results"].append(result)
            if "error" in result:
                print(f"ERROR: {result['error']}")
            else:
                ev_rate = result["evidence"]["source_file_rate"]
                print(f"{result['total_findings']} findings | evidence: {ev_rate:.0%} | hyp: {result['hypothesis_count']}")

    # --- Summary ---
    all_fixture = report["fixture_results"]
    total_findings = sum(r["total_findings"] for r in all_fixture)
    total_with_source = sum(r["evidence"]["with_source_file"] for r in all_fixture)
    total_with_evidence = sum(r["evidence"]["with_evidence_excerpt"] for r in all_fixture)
    passed = sum(1 for r in all_fixture if r["passed"])

    report["summary"] = {
        "fixtures_passed": f"{passed}/{len(all_fixture)}",
        "total_findings_across_fixtures": total_findings,
        "overall_source_file_rate": round(total_with_source / total_findings, 3) if total_findings else 1.0,
        "overall_evidence_rate": round(total_with_evidence / total_findings, 3) if total_findings else 1.0,
    }

    # Print summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Fixtures passed: {report['summary']['fixtures_passed']}")
    print(f"Total findings: {total_findings}")
    print(f"Source file population rate: {report['summary']['overall_source_file_rate']:.1%}")
    print(f"Evidence excerpt population rate: {report['summary']['overall_evidence_rate']:.1%}")

    # Per-scanner aggregation
    scanner_agg: dict[str, dict] = defaultdict(lambda: {"total": 0, "with_source": 0, "with_evidence": 0})
    for r in all_fixture:
        for scanner, stats in r.get("per_scanner", {}).items():
            scanner_agg[scanner]["total"] += stats["total"]
            scanner_agg[scanner]["with_source"] += stats["with_source"]
            scanner_agg[scanner]["with_evidence"] += stats["with_evidence"]

    if scanner_agg:
        print("\nPer-scanner evidence rates:")
        for scanner in sorted(scanner_agg.keys()):
            s = scanner_agg[scanner]
            src_rate = s["with_source"] / s["total"] if s["total"] else 1.0
            ev_rate = s["with_evidence"] / s["total"] if s["total"] else 1.0
            status = "OK" if src_rate == 1.0 and ev_rate == 1.0 else "GAP"
            print(f"  [{status}] {scanner}: {s['total']} findings, source={src_rate:.0%}, evidence={ev_rate:.0%}")

    # Save report
    output_path = PROJECT_ROOT / "validation_report.json"
    output_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nFull report saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
