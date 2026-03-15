# TroubleShootAI -- Implementation Plan

## Overview

Eight-phase plan for building the AI-powered Kubernetes support bundle forensics tool. Phases 1-4 are complete. Phases 5-8 cover ongoing improvements.

---

## Phase 1: Evidence Grounding and Bug Fixes -- COMPLETE

**Goal:** Ensure all triage output is structured, evidence-backed, and free of known bugs.

**Work completed:**
- Fixed the pending-pod wall-clock duration bug (incorrect time calculation for pods stuck in Pending).
- Added structured `Evidence` objects to all triage findings, replacing free-text descriptions with source-referenced citations.
- Added confidence scores (0.0-1.0) to every `TriageFinding`, enabling downstream consumers to filter by reliability.
- Standardized triage scanner output format across all existing scanners.

**Gate:** All existing scanners produce `TriageFinding` objects with evidence and confidence scores. No known correctness bugs in triage layer.

---

## Phase 2: Missing Detectors -- COMPLETE

**Goal:** Fill gaps in scanner coverage for Kubernetes failure domains that were not yet handled.

**Work completed:**
- Built DNS/CoreDNS scanner detecting resolution failures, CoreDNS pod errors, and DNS policy misconfigurations.
- Built TLS/certificate scanner checking expiry dates, chain validation errors, and TLS termination issues.
- Built scheduling scanner identifying taint/toleration mismatches, node affinity conflicts, and unschedulable conditions.
- All new scanners follow the established `TriageFinding` contract with evidence and confidence scores.

**Gate:** Scanner count at 18. All new scanners have unit tests. No Kubernetes failure domain left uncovered for common issues.

---

## Phase 3: Root-Cause Reasoning -- COMPLETE

**Goal:** Move beyond listing findings to proposing ranked root causes with causal chains.

**Work completed:**
- Built hypothesis engine in `bundle_analyzer/rca/` that generates root-cause hypotheses from triage findings.
- Implemented deterministic RCA rules covering common failure patterns (e.g., OOMKilled -> resource limits too low -> node memory pressure).
- Added evidence strength scoring to rank hypotheses by how well they are supported by bundle data.
- Added gap detection to identify where the bundle lacks data needed to confirm or deny a hypothesis.
- Integrated AI claim validation to check that analyst outputs are grounded in actual triage evidence.

**Gate:** Hypothesis engine produces ranked root causes for test fixtures. Deterministic rules cover the top 10 most common Kubernetes failure patterns.

---

## Phase 4: Testing Harness -- COMPLETE

**Goal:** Establish a testing foundation for regression prevention and confidence in refactoring.

**Work completed:**
- Created regression test fixtures using sample bundle JSON fragments in `tests/fixtures/`.
- Added unit tests for all 18 triage scanners.
- Added tests for the hypothesis engine and RCA rules.
- Set up pytest with pytest-asyncio for async test execution.

**Gate:** Test suite passes. Fixtures cover the major scanner paths. New code changes do not break existing scanner behavior.

---

## Phase 5: Web Application Improvements -- FUTURE

**Scope:** Enhance the Next.js frontend and FastAPI backend for production readiness.

**Planned work:**
- Improve analysis visualization with interactive resource graphs.
- Add bundle upload progress tracking and large-file handling in the UI.
- Implement result caching to avoid re-analyzing unchanged bundles.
- Add user session management and analysis history.
- Optimize WebSocket streaming for lower latency AI response delivery.
- Improve error handling and user feedback for failed analyses.

---

## Phase 6: Orchestration Refinements -- FUTURE

**Scope:** Make the AI orchestration layer smarter and more efficient.

**Planned work:**
- Tune dynamic work tree logic to better select which analysts to invoke.
- Add token budget tracking and enforcement per analysis run.
- Implement analyst result caching to avoid redundant API calls.
- Add cross-analyst correlation to surface findings that span multiple domains.
- Improve synthesis quality by providing analysts with each other's findings.

---

## Phase 7: Security Hardening -- FUTURE

**Scope:** Strengthen the 7-layer security architecture for production deployment.

**Planned work:**
- Expand pattern detector coverage with additional secret formats.
- Tune entropy detection thresholds to reduce false positives.
- Add automated security testing with adversarial prompt injection samples.
- Implement scrubbing audit reports for compliance review.
- Add configurable security policies per tenant/organization.
- Penetration test the full pipeline from bundle upload to AI response.

---

## Phase 8: Live Testing and Validation -- FUTURE

**Scope:** Validate the tool against real-world support bundles and production scenarios.

**Planned work:**
- Test against a corpus of real (sanitized) support bundles from production clusters.
- Measure triage scanner precision and recall against manually-labeled findings.
- Benchmark AI analyst accuracy with expert-reviewed root-cause assessments.
- Load test the pipeline with large bundles (500MB+) to verify streaming stability.
- Collect user feedback from SRE and support engineering teams.
- Iterate on scanner rules and AI prompts based on real-world false positives/negatives.
