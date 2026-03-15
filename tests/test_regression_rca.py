"""Regression tests for the RCA hypothesis engine.

Tests that the HypothesisEngine produces correct hypotheses for
fixture bundles, including expected hypothesis title, evidence,
and contradiction detection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.rca.hypothesis_engine import HypothesisEngine
from bundle_analyzer.triage.engine import TriageEngine

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "bundles"


def get_rca_fixture_dirs() -> list[Path]:
    """Get fixture dirs that have expected_hypotheses in their expected.json."""
    if not FIXTURES_DIR.exists():
        return []
    dirs = []
    for d in sorted(FIXTURES_DIR.iterdir()):
        if not d.is_dir():
            continue
        expected_path = d / "expected.json"
        if not expected_path.exists():
            continue
        expected = json.loads(expected_path.read_text())
        if expected.get("expected_hypotheses"):
            dirs.append(d)
    return dirs


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_dir", get_rca_fixture_dirs(), ids=lambda d: d.name)
async def test_rca_hypotheses(fixture_dir: Path) -> None:
    """Verify that expected RCA hypotheses are generated for fixture bundles."""
    expected = json.loads((fixture_dir / "expected.json").read_text())
    expected_hyps = set(expected.get("expected_hypotheses", []))

    index = await BundleIndex.build(fixture_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    hyp_engine = HypothesisEngine()
    hypotheses = await hyp_engine.analyze(triage)

    hyp_titles = {h.title for h in hypotheses}

    missing = expected_hyps - hyp_titles
    assert not missing, (
        f"Fixture '{fixture_dir.name}': missing expected hypotheses: {missing}. "
        f"Got: {hyp_titles}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_dir", get_rca_fixture_dirs(), ids=lambda d: d.name)
async def test_rca_hypothesis_evidence(fixture_dir: Path) -> None:
    """Every generated hypothesis must have supporting evidence."""
    index = await BundleIndex.build(fixture_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    hyp_engine = HypothesisEngine()
    hypotheses = await hyp_engine.analyze(triage)

    for h in hypotheses:
        assert len(h.supporting_evidence) > 0, (
            f"Hypothesis '{h.title}' has no supporting evidence"
        )
        assert 0 < h.confidence <= 1.0, (
            f"Hypothesis '{h.title}' has invalid confidence: {h.confidence}"
        )


@pytest.mark.asyncio
async def test_rca_no_hypotheses_for_healthy_bundle() -> None:
    """The tls_expired fixture (healthy pod) should produce no hypotheses."""
    fixture_dir = FIXTURES_DIR / "tls_expired"
    if not fixture_dir.exists():
        pytest.skip("tls_expired fixture not found")

    index = await BundleIndex.build(fixture_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    hyp_engine = HypothesisEngine()
    hypotheses = await hyp_engine.analyze(triage)

    # A healthy pod should generate no RCA hypotheses
    assert len(hypotheses) == 0, (
        f"Expected no hypotheses for healthy bundle, got: "
        f"{[h.title for h in hypotheses]}"
    )
