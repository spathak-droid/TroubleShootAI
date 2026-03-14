# Automated Support Bundle Analysis - Execution Roadmap

## Goal
Build a production-grade AI system that analyzes Troubleshoot support bundles and returns:
- what failed
- likely root cause(s)
- risk level and blast radius
- concrete remediation steps
- explicit uncertainty gaps

## North-Star Success Criteria
- High-signal triage on common Kubernetes failure modes.
- Root-cause suggestions are evidence-grounded and actionable.
- False positives are controlled enough for support engineers to trust output.
- Domain knowledge (vendor/application specific) improves quality measurably.

## Milestones (8-10 weeks)

### Milestone 1: Baseline + Instrumentation (Week 1)
- Freeze current baseline on the existing sample bundle set.
- Add metrics logging per run:
  - bundle size, file count, scan duration, AI duration
  - finding counts by severity and category
  - tokens and estimated cost by analyst
- Deliverable:
  - `reports/baseline_metrics.jsonl`
  - single-page baseline summary markdown

### Milestone 2: Evaluation Harness (Week 2)
- Create a labeled benchmark set of support bundles:
  - synthetic bundles (known injected failures)
  - anonymized real bundles (where available)
- Add `ground_truth.json` per bundle with:
  - primary root cause
  - secondary contributing factors
  - expected evidence files
  - expected remediation class
- Compute metrics:
  - triage precision/recall/F1 by failure class
  - top-1 and top-3 root-cause hit rate
  - evidence precision (did cited file actually support claim)
  - remediation correctness (binary human-verified label)
- Deliverable:
  - reproducible evaluator command (single CLI entrypoint)

### Milestone 3: Domain Knowledge Layer (Week 3)
- Replace single context blob with retrieval-backed knowledge:
  - runbooks
  - known-issues
  - architecture map
  - error signature library
- Add source-scoped retrieval:
  - Kubernetes generic
  - vendor product docs
  - environment-specific playbooks
- Require every non-trivial recommendation to cite at least one retrieved artifact.
- Deliverable:
  - `knowledge/` structure + retrieval module + citation linking

### Milestone 4: Signal Quality Improvements (Weeks 4-5)
- Reduce scanner noise with:
  - namespace-aware suppressions
  - optional-resource handling
  - bootstrapping/transient-state heuristics
- Add confidence calibration:
  - map raw model confidence + deterministic evidence weight -> calibrated score
- Add "finding validity checks":
  - forbid critical findings without strong evidence anchors
  - deduplicate semantically equivalent findings
- Deliverable:
  - measurable false-positive reduction vs Milestone 2 baseline

### Milestone 5: Causal Graph + Risk Scoring (Week 6)
- Build a causal graph from events/resources:
  - node pressure -> pod eviction -> service degradation
  - config deletion -> pod startup failure -> deployment unavailable
- Add risk scoring model:
  - impact (blast radius)
  - likelihood
  - time-to-failure (when available)
- Deliverable:
  - machine-readable `risk_graph.json`
  - top-risks section in report/API

### Milestone 6: Safety + Governance (Week 7)
- Expand scrubber policy profiles:
  - strict enterprise mode
  - balanced mode
  - local/offline mode
- Add outbound data guardrails:
  - max payload per AI request
  - redaction audit trail per finding
  - denylist for protected namespaces/keys
- Deliverable:
  - security controls matrix + test coverage

### Milestone 7: Productization (Weeks 8-9)
- UX improvements:
  - incident narrative (what happened first, next, now)
  - "do this first" remediation ordering
  - diff-first mode for before/after bundles
- API hardening:
  - stable response schemas
  - versioned endpoint contract
  - paginated findings/events for large bundles
- Deliverable:
  - release candidate with benchmark report

## Dataset and Labeling Spec

### Bundle Dataset Layout
```text
datasets/
  bundle_001/
    bundle.tar.gz
    metadata.json
    ground_truth.json
  bundle_002/
    ...
```

### `metadata.json` (example)
```json
{
  "bundle_id": "bundle_001",
  "source": "synthetic_kind",
  "k8s_version": "1.30",
  "workload_type": "web+db",
  "notes": "Injected ConfigMap deletion + ImagePull failure"
}
```

### `ground_truth.json` (example)
```json
{
  "primary_root_cause": "missing_configmap",
  "secondary_causes": ["image_pull_backoff"],
  "expected_findings": [
    {
      "type": "CreateContainerConfigError",
      "resource": "pod/default/api-xxxxx",
      "severity": "critical"
    }
  ],
  "expected_evidence_files": [
    "cluster-resources/events/default.json",
    "cluster-resources/pods/default/api-xxxxx.json"
  ],
  "expected_remediation_class": "restore_config"
}
```

## Evaluation Metrics (Report Card)
- Triage F1 by class:
  - CrashLoopBackOff
  - OOMKilled
  - ImagePullBackOff
  - Pending/Unschedulable
  - Config reference failures
  - Node pressure/not-ready
- Root-cause quality:
  - Top-1 hit rate
  - Top-3 hit rate
  - Human-rated usefulness (1-5)
- Evidence quality:
  - citation precision
  - unsupported-claim rate (target near zero)
- Ops quality:
  - p50/p95 analysis time
  - p50/p95 cost per bundle
  - % analyses completed without fatal errors

## Architecture Upgrades (Concrete)

### 1) Knowledge Retrieval Service
- Inputs: finding candidate + resource context.
- Outputs: top-k snippets + provenance.
- Backends:
  - local markdown/JSONL index first
  - optional vector DB later

### 2) Finding Validator
- Checks each candidate finding for:
  - evidence presence
  - contradictory signals
  - severity policy compliance
- Drops or downgrades weak findings.

### 3) Causal Correlator
- Build cross-resource temporal links.
- Emit:
  - trigger event
  - intermediate failures
  - final impact node

### 4) Offline/Disconnected Mode
- Deterministic triage only + optional local model.
- No external API requirement.
- Required for customer environments with strict data controls.

## Immediate Next Sprint (5 tasks)
1. Build evaluator CLI and dataset schema validation.
2. Add ground-truth labels for current demo bundle + at least 5 synthetic bundles.
3. Implement finding validator with evidence hard-requirement for critical severity.
4. Replace flat context injection with scoped retrieval over `knowledge/`.
5. Generate first benchmark report and identify top 3 false-positive sources.

## Risks and Mitigations
- Risk: noisy scanner output reduces trust.
  - Mitigation: suppressions + calibrated confidence + validator gate.
- Risk: hallucinated recommendations.
  - Mitigation: citation requirement + unsupported-claim tests.
- Risk: domain mismatch across vendors.
  - Mitigation: pluggable knowledge packs and per-vendor policies.
- Risk: bundle incompleteness.
  - Mitigation: strong uncertainty reporting and collector recommendations.

## Definition of "Competition-Ready"
- Demonstrates improvement on benchmark metrics across at least 10 labeled bundles.
- Produces deterministic + AI findings with clear evidence and ranked remediation.
- Handles at least one multi-cause incident chain.
- Includes safety controls (scrubbing/audit) and explicit uncertainty output.
