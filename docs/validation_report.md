# Bundle Analyzer Validation Report

**Generated from**: `validation_report.json`
**Timestamp**: 2026-03-15T10:27:02
**Methodology**: Automated triage pipeline run against 7 fixture bundles (synthetic scenarios with known-expected finding types) and 3 real Kubernetes support bundles. Each finding is checked for source file citation, evidence excerpt, and confidence score.

---

## 1. Overview

The validation suite tests the deterministic triage scanners (PodScanner, ConfigScanner, ProbeScanner, ResourceScanner, EventScanner, SchedulingScanner, DNSScanner, NetworkPolicyScanner, QuotaScanner) across two categories:

- **Fixture bundles** (7 total): Synthetic bundles targeting specific failure modes (OOMKilled, CrashLoopBackOff, ImagePullBackOff, missing secret, insufficient CPU, PVC pending, healthy pod). Each fixture declares expected finding types; the test passes if all expected types are found.
- **Real bundles** (3 total): Actual support bundles collected from Kind clusters with intentionally broken workloads. No expected-type assertions -- these measure coverage, evidence grounding, and scanner distribution.

**Top-line result**: 7/7 fixture tests passed. 100% evidence grounding across all bundles.

---

## 2. Fixture Bundle Results

| Fixture | Pass/Fail | Total Findings | Expected Types Found | Missing Types | Unexpected Types | Evidence Rate | Confidence (mean) |
|---|---|---|---|---|---|---|---|
| crashloop_oom | PASS | 2 | OOMKilled | -- | no_policies | 100% | 1.000 |
| dns_failure | PASS | 2 | CrashLoopBackOff, coredns_pod_failure | -- | -- | 100% | 1.000 |
| image_pull_fail | PASS | 3 | ImagePullBackOff | -- | Pending, no_policies | 100% | 0.850 |
| missing_secret | PASS | 3 | CreateContainerConfigError | -- | Pending, no_policies | 100% | 0.867 |
| pending_insufficient_cpu | PASS | 4 | Pending, insufficient_cpu | -- | no_policies, sustained | 100% | 0.963 |
| pvc_pending | PASS | 2 | Pending | -- | no_policies | 100% | 0.800 |
| tls_expired | PASS | 1 | (none expected) | -- | -- | 100% | 1.000 |

**Summary**: 7/7 passed. 17 total findings across fixtures. Zero missing expected types. All "unexpected" types are legitimate secondary findings (e.g., NetworkPolicyScanner flagging missing policies, EventScanner flagging sustained events).

---

## 3. Real Bundle Results

| Bundle | Namespaces | Total Findings | Source File Rate | Evidence Excerpt Rate | Confidence (min/mean/max) | Scanners Active |
|---|---|---|---|---|---|---|
| support-bundle-2026-03-13T12_54_09 | cluster-resources, kots, logs | 49 | 100% | 100% | 0.90 / 0.995 / 1.00 | PodScanner(6), ConfigScanner(18), ProbeScanner(7), ResourceScanner(14), EventScanner(4) |
| support-bundle-2026-03-13T14_20_00 | cluster-resources, kots, logs | 49 | 100% | 100% | 0.90 / 0.995 / 1.00 | PodScanner(6), ConfigScanner(18), ProbeScanner(7), ResourceScanner(14), EventScanner(4) |
| support-bundle-2026-03-14T01_49_29 | cluster-resources, logs | 68 | 100% | 100% | 0.90 / 0.991 / 1.00 | PodScanner(2), ConfigScanner(24), ProbeScanner(5), ResourceScanner(16), SchedulingScanner(10), EventScanner(8), QuotaScanner(3) |

**Finding type breakdown across real bundles**:

| Finding Type | Bundle 1 | Bundle 2 | Bundle 3 |
|---|---|---|---|
| CrashLoopBackOff | 2 | 2 | 0 |
| CreateContainerConfigError | 1 | 1 | 1 |
| ImagePullBackOff | 1 | 1 | 0 |
| Pending | 2 | 2 | 1 |
| ConfigMap missing | 18 | 18 | 24 |
| Secret missing | 0 | 0 | 2 |
| bad_path (probe) | 3 | 3 | 4 |
| no_readiness_probe | 2 | 2 | 1 |
| missing_startup | 2 | 2 | 0 |
| no_limits | 10 | 10 | 12 |
| no_requests | 2 | 2 | 4 |
| BestEffort QoS | 2 | 2 | 4 |
| Event cascading | 1 | 1 | 0 |
| Event sustained | 3 | 3 | 0 |
| taint_not_tolerated | 0 | 0 | 3 |
| insufficient_cpu | 0 | 0 | 4 |
| insufficient_memory | 0 | 0 | 3 |
| QuotaScanner findings | 0 | 0 | 3 |

---

## 4. Evidence Grounding

Every finding across all bundles has both a `source_file` and an `evidence_excerpt` populated.

### Per-scanner evidence population rates

| Scanner | Total Findings (all bundles) | Source File Rate | Evidence Excerpt Rate |
|---|---|---|---|
| PodScanner | 14 (fixture) + 14 (real) | 100% | 100% |
| ConfigScanner | 0 (fixture) + 60 (real) | 100% | 100% |
| ProbeScanner | 0 (fixture) + 19 (real) | 100% | 100% |
| ResourceScanner | 0 (fixture) + 44 (real) | 100% | 100% |
| EventScanner | 1 (fixture) + 16 (real) | 100% | 100% |
| SchedulingScanner | 1 (fixture) + 10 (real) | 100% | 100% |
| DNSScanner | 1 (fixture) | 100% | 100% |
| NetworkPolicyScanner | 7 (fixture) | 100% | 100% |
| QuotaScanner | 0 (fixture) + 3 (real) | 100% | 100% |

**Overall source file rate**: 100%
**Overall evidence excerpt rate**: 100%

This is a strong result. Every finding can be traced back to a specific file in the bundle with a human-readable evidence excerpt.

---

## 5. Confidence Score Distribution

| Bundle Category | Min | Mean | Max | All 1.0? |
|---|---|---|---|---|
| crashloop_oom | 1.0 | 1.000 | 1.0 | Yes |
| dns_failure | 1.0 | 1.000 | 1.0 | Yes |
| image_pull_fail | 0.6 | 0.850 | 1.0 | No |
| missing_secret | 0.6 | 0.867 | 1.0 | No |
| pending_insufficient_cpu | 0.9 | 0.963 | 1.0 | No |
| pvc_pending | 0.6 | 0.800 | 1.0 | No |
| tls_expired | 1.0 | 1.000 | 1.0 | Yes |
| Real bundle 1 | 0.9 | 0.995 | 1.0 | No |
| Real bundle 2 | 0.9 | 0.995 | 1.0 | No |
| Real bundle 3 | 0.9 | 0.991 | 1.0 | No |

**Assessment**: Confidence scores are mostly well-calibrated but skew high. The 0.6 scores appear only on generic "Pending" findings where the pod phase is Pending but the root cause may be ambiguous. Specific failure types (OOMKilled, CrashLoopBackOff, ImagePullBackOff, missing config/secret) correctly get 0.95-1.0. Real bundles never drop below 0.9.

**Concern**: 3 of 7 fixtures have all scores at 1.0, and real bundles are 0.99+ mean. The system could benefit from more granular confidence differentiation, especially for ConfigScanner findings where a "missing" ConfigMap like `kube-root-ca.crt` is almost certainly a bundle collection artifact rather than a real cluster issue.

---

## 6. RCA Hypothesis Quality

**Hypotheses generated**: 0 across all bundles.

Every fixture and real bundle reports `"hypotheses": []`. The RCA hypothesis engine is not producing output in the current validation run.

**Possible causes**:
1. The RCA / hypothesis generation is part of the AI pipeline (Phase 2) and the validation only exercises the deterministic triage scanners (Phase 1).
2. The orchestrator that generates hypotheses may not have been invoked during validation.
3. The hypothesis model may require multiple correlated findings before synthesizing a root cause.

**Action needed**: This is the single biggest gap in the current validation. The triage layer finds symptoms effectively, but without hypotheses, the user must manually correlate findings. The AI orchestrator should be validated separately to confirm it generates meaningful RCA hypotheses from scanner output.

---

## 7. Known Gaps

### 7.1 No RCA hypotheses generated
As noted above, zero hypotheses across all bundles. The correlation and root-cause reasoning layer needs its own validation.

### 7.2 ConfigScanner false positives on `kube-root-ca.crt`
The ConfigScanner reports `kube-root-ca.crt` as "missing" for nearly every pod in every bundle. This is a bundle collection artifact -- the support bundle tool does not collect auto-injected ConfigMaps. This inflates finding counts significantly (18-24 per real bundle). The scanner should allowlist well-known auto-projected ConfigMaps.

### 7.3 No TLS/certificate scanning
The `tls_expired` fixture is described as "Normal running pod" and correctly finds no issues, but the fixture name suggests TLS expiry detection was intended. No scanner currently detects expired or soon-to-expire certificates.

### 7.4 No PVC-specific scanner
The `pvc_pending` fixture only produces a generic "Pending" finding from PodScanner. There is no dedicated PVC/volume scanner that would identify the specific volume mount failure, unbound PVC, or missing StorageClass.

### 7.5 NetworkPolicyScanner only in fixtures
The NetworkPolicyScanner fires on every fixture (all use `default` namespace with no policies) but does not appear in any real bundle results. This may indicate the real bundles have NetworkPolicies, or the scanner does not handle the real bundle directory structure.

### 7.6 Confidence scores lack granularity
Most scores are 1.0 or 0.9-0.95. The system would benefit from a wider distribution to help users prioritize findings. Infrastructure-level findings (missing limits on kube-system pods) could reasonably be scored lower than application-level failures.

### 7.7 DNSScanner limited to fixture coverage
The DNSScanner only appears in the `dns_failure` fixture. None of the real bundles trigger it, so real-world DNS detection remains unvalidated.

---

## 8. What the System Gets Right

### 8.1 Perfect evidence grounding
100% of findings across all bundles have both a source file path and an evidence excerpt. This is the foundation of trustworthy diagnostics -- every claim can be verified by the engineer.

### 8.2 Correct failure detection with zero false negatives
All 7 fixture scenarios detected their expected failure types. No expected finding was missed.

### 8.3 Good secondary finding discovery
The scanners discover related issues beyond the primary failure: EventScanner identifies sustained/cascading event patterns, SchedulingScanner catches taint issues, ResourceScanner flags missing limits. These are genuinely useful for holistic cluster assessment.

### 8.4 Multi-scanner correlation on real bundles
Real bundles activate 5-7 scanners simultaneously, producing a comprehensive cross-cutting view. Bundle 3 (the most complex, with a 3-node cluster and production namespace) activated 7 scanners including SchedulingScanner and QuotaScanner.

### 8.5 Reasonable confidence calibration for critical findings
Critical findings (OOMKilled, CrashLoopBackOff, missing secrets, image pull failures) consistently score 0.95-1.0. The lower 0.6 score for generic "Pending" is appropriate since Pending alone is ambiguous.

### 8.6 Actionable evidence excerpts
Evidence excerpts contain the actual Kubernetes status messages (e.g., `"secret \"payment-credentials\" not found"`, `"0/3 nodes are available: 3 Insufficient cpu."`). These are immediately actionable for an engineer without needing to dig into the bundle.

### 8.7 Consistent results across bundle snapshots
Bundles 1 and 2 (taken ~1.5 hours apart from the same cluster) produce identical finding counts and types, confirming deterministic scanner behavior.

---

## Appendix: Scanner Coverage Matrix

| Scanner | Fixture Scenarios Covered | Real Bundle Coverage | Finding Types |
|---|---|---|---|
| PodScanner | crashloop_oom, dns_failure, image_pull_fail, missing_secret, pending_insufficient_cpu, pvc_pending | All 3 | OOMKilled, CrashLoopBackOff, ImagePullBackOff, CreateContainerConfigError, Pending |
| DNSScanner | dns_failure | None | coredns_pod_failure |
| NetworkPolicyScanner | All fixtures | None | no_policies |
| SchedulingScanner | pending_insufficient_cpu | Bundle 3 | insufficient_cpu, taint_not_tolerated |
| EventScanner | pending_insufficient_cpu | Bundles 1-3 | sustained, cascading |
| ConfigScanner | None | All 3 | missing (ConfigMap/Secret) |
| ProbeScanner | None | All 3 | bad_path, no_readiness_probe, missing_startup |
| ResourceScanner | None | All 3 | no_limits, no_requests, BestEffort QoS |
| QuotaScanner | None | Bundle 3 | quota findings |
