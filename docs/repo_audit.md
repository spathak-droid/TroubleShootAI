# TroubleShootAI -- Repository Architecture Audit

## 1. Architecture Summary

TroubleShootAI is an AI-powered Kubernetes support bundle forensics tool. It ingests support bundles (tar archives containing pod logs, node info, cluster resources, etc.), runs deterministic triage scanners to extract structured findings, then passes curated evidence to AI analysts for deeper synthesis and root-cause analysis.

- **Frontend**: Next.js web application with analysis visualization and WebSocket streaming for real-time AI responses.
- **Backend**: FastAPI serving REST endpoints and WebSocket connections, orchestrating triage and AI pipelines.
- **AI Layer**: Claude API integration with structured JSON output, claim validation, and multi-layer security scrubbing.
- **Core Engine**: Python 3.11+, Pydantic v2 data models, async I/O throughout, streaming tar extraction for large bundles.

---

## 2. Component Map

### `bundle_analyzer/bundle/` -- Bundle Extraction and Indexing

Handles ingestion of support bundle archives. Provides streaming tar extraction (bundles can exceed 500MB), builds a `BundleIndex` for resource discovery, and exposes safe read methods that prevent loading entire files into memory.

### `bundle_analyzer/triage/` -- Deterministic Scanners (18 total)

Pre-AI analysis using pattern matching, threshold checks, and structural validation. Each scanner returns structured `TriageFinding` objects with evidence, confidence scores, and severity ratings. Scanners:

| Scanner | Scope |
|---|---|
| Pod | CrashLoopBackOff, OOMKilled, pending pods, image pull errors |
| Node | NotReady, disk/memory/PID pressure, unschedulable |
| Deployment | Unavailable replicas, rollout stalls, mismatched selectors |
| Config | ConfigMap/Secret reference errors, missing mounts |
| Drift | Configuration drift between expected and actual state |
| Silence | Missing expected resources, absent log output |
| Probe | Liveness/readiness probe misconfigurations |
| Resource | CPU/memory requests vs limits, unbounded containers |
| Ingress | Ingress misconfigurations, missing backends |
| Storage | PVC binding failures, storage class issues |
| RBAC | Permission denied errors, missing role bindings |
| Quota | ResourceQuota violations, LimitRange conflicts |
| Network Policy | Network policy gaps, connectivity issues |
| Crashloop | Detailed crash loop analysis with restart pattern detection |
| DNS | CoreDNS errors, resolution failures, DNS policy issues |
| TLS | Certificate expiry, chain validation, TLS misconfigurations |
| Scheduling | Taint/toleration mismatches, affinity conflicts, unschedulable analysis |
| Troubleshoot | General troubleshoot collector analysis |

### `bundle_analyzer/ai/` -- AI Analysts and Orchestration

- **Pod Analyst** -- Analyzes pod failures with log context and event correlation.
- **Node Analyst** -- Evaluates node health, resource exhaustion, kernel issues.
- **Config Analyst** -- Detects configuration anti-patterns and mismatches.
- **Log Analyst** -- Parses log patterns for error signatures and anomalies.
- **Synthesis** -- Merges findings from all analysts into a unified report.
- **Orchestrator** -- Dynamic work tree that decides which analysts to invoke based on triage output (avoids spending tokens on irrelevant analysis).
- **Validation** -- AI claim validation ensuring analyst outputs are grounded in evidence.

### `bundle_analyzer/rca/` -- Root Cause Analysis

Hypothesis engine that builds causal chains from triage findings. Uses deterministic rules to propose root causes, rank hypotheses by evidence strength, and identify gaps where the bundle lacks sufficient data for a conclusion.

### `bundle_analyzer/security/` -- 7-Layer Security Scrubbing

1. **Pattern Detectors** -- Regex-based detection of known secret formats (API keys, tokens, passwords).
2. **Entropy Detection** -- Shannon entropy analysis to catch novel/unknown secret patterns.
3. **Kubernetes Structural Scrubbers** -- K8s-aware scrubbing that preserves resource names, namespaces, and labels while redacting env var values and secret data.
4. **Prompt Injection Guard** -- Wraps untrusted log content in boundary markers to defend against injection in LLM prompts.
5. **Audit Logger** -- Records all redaction actions for compliance (what was redacted, when, by which detector).
6. **Policy Engine** -- `SecurityPolicy` model controlling scrub behavior (standard/strict/allowlist modes).
7. **Pre-ingestion + Pre-LLM** -- Dual scrubbing at storage boundary and again before any API call.

### `bundle_analyzer/graph/` -- Resource Graph

Builds a dependency graph of Kubernetes resources from bundle data. Supports causal chain walking to trace failures from symptom to root cause across resource boundaries (e.g., Pod -> Deployment -> ConfigMap -> Secret).

### `bundle_analyzer/api/` -- FastAPI Backend

REST endpoints for bundle upload, analysis triggering, and result retrieval. WebSocket endpoint for streaming AI responses to the frontend in real time.

### `frontend/` -- Next.js Web UI

Web application providing analysis visualization, interactive exploration of findings, and real-time streaming of AI analyst output. Replaced the original Textual TUI for richer visualization capabilities.

---

## 3. Quality Assessment

**Strengths:**

- Clear separation of concerns between triage (deterministic) and AI (probabilistic) layers.
- Comprehensive scanner coverage across 18 Kubernetes failure domains.
- Proper security architecture with defense-in-depth scrubbing before data reaches any LLM.
- Structured output throughout -- all findings use Pydantic v2 models, no free-text returns.
- Streaming extraction handles large bundles without memory exhaustion.
- Evidence grounding requirement prevents AI hallucination by mandating citations.
- Dynamic orchestration avoids wasting API tokens on irrelevant analysis paths.

**Design Decisions:**

- Triage runs before AI to avoid spending tokens on what regex can find.
- `***HIDDEN***` redaction markers from upstream tools are recognized and not double-redacted.
- All bundle reads go through `BundleIndex` -- no direct file opens.
- Async throughout for I/O operations.
- Env var names preserved (diagnostic value) while values are always redacted.

---

## 4. Gap List

### Fixed / Addressed

| Item | Status | Details |
|---|---|---|
| Pending-pod wall-clock bug | FIXED | Pending duration calculation was incorrect, now uses proper wall-clock time |
| Triage findings lacked structured evidence | FIXED | All findings now include structured `Evidence` objects with source references |
| No confidence scores on triage findings | FIXED | Every `TriageFinding` includes a confidence score (0.0-1.0) |

### Added

| Item | Status | Details |
|---|---|---|
| AI claim validation | ADDED | Validator checks that AI analyst claims are grounded in triage evidence |
| DNS/CoreDNS scanner | ADDED | Detects DNS resolution failures, CoreDNS errors, DNS policy misconfigurations |
| TLS/certificate scanner | ADDED | Checks certificate expiry, chain validation errors, TLS configuration issues |
| Scheduling scanner | ADDED | Identifies taint/toleration mismatches, affinity conflicts, unschedulable nodes |
| Hypothesis engine | ADDED | Root-cause reasoning with ranked hypotheses and evidence strength scoring |
| Deterministic RCA rules | ADDED | Rule-based causal chains that do not require AI for common failure patterns |
| Regression test fixtures | ADDED | Sample bundle fragments in `tests/fixtures/` for repeatable testing |
