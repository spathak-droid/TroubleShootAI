# Bundle Analyzer — Complete Architecture Plan
> Forensic Reconstruction Engine for Kubernetes Support Bundles

---

## 1. SYSTEM OVERVIEW

```
                         ┌─────────────────────────────────────────┐
                         │           USER ENTRY POINTS             │
                         │                                         │
                         │  $ bundle-analyzer ./bundle.tar.gz      │
                         │  $ bundle-analyzer diff a.tar b.tar     │
                         │  $ bundle-analyzer --no-tui ./bundle    │
                         └───────────────┬─────────────────────────┘
                                         │
                         ┌───────────────▼─────────────────────────┐
                         │           TUI LAYER (Textual)           │
                         │   Screen 1: File Select / Drop          │
                         │   Screen 2: Live Analysis Dashboard     │
                         │   Screen 3: Findings Explorer           │
                         │   Screen 4: Timeline View               │
                         │   Screen 5: Forensic Interview          │
                         └───────────────┬─────────────────────────┘
                                         │ calls
                         ┌───────────────▼─────────────────────────┐
                         │         ORCHESTRATOR ENGINE             │
                         │   Reads triage → builds work tree →     │
                         │   dispatches analysts → synthesizes     │
                         └──┬────────────┬──────────────┬──────────┘
                            │            │              │
              ┌─────────────▼──┐  ┌──────▼──────┐ ┌───▼──────────┐
              │ PARSE + TRIAGE │  │ AI ANALYSTS │ │  NOVEL       │
              │ Layer 1        │  │ Layer 2     │ │  ENGINES     │
              └────────────────┘  └─────────────┘ └──────────────┘
```

---

## 2. TUI ARCHITECTURE (Textual Framework)

### Why Textual
- <50ms startup, no browser needed
- Runs over SSH — evaluators can run it on any machine
- asyncio-native — AI streaming responses update in real time
- Can serve as web app too via `textual serve` (bonus)
- 16.7M colors, mouse support, smooth animations

### Screen Flow

```
┌─────────────────────────────────────────────────────────┐
│  Screen 1: WELCOME + FILE INPUT                         │
│                                                         │
│  ╔═══════════════════════════════════════════════════╗  │
│  ║  BUNDLE ANALYZER  —  Kubernetes Forensics Engine  ║  │
│  ╚═══════════════════════════════════════════════════╝  │
│                                                         │
│   Path to bundle:  [________________________] [ANALYZE] │
│                                                         │
│   Or diff two bundles:                                  │
│   Before: [__________________]                          │
│   After:  [__________________]  [DIFF]                  │
│                                                         │
│   Optional: Paste app context (Helm values / README)    │
│   [                                              ]      │
│   [                                              ]      │
│                                                         │
│   ─────────────────────────────────────────────         │
│   Recent: support-bundle-2024-11-20.tar.gz    [open]   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Screen 2: LIVE ANALYSIS DASHBOARD (streaming)          │
│                                                         │
│  ╔═══════════════════════════════════════════════════╗  │
│  ║  Analyzing: support-bundle-2024-11-20.tar.gz      ║  │
│  ╚═══════════════════════════════════════════════════╝  │
│                                                         │
│  EXTRACTION          ████████████████████ 100%  ✓      │
│  INDEX (247 files)   ████████████████████ 100%  ✓      │
│  TRIAGE              ████████████████████ 100%  ✓ 3🔴  │
│  ARCHAEOLOGY         ████████████░░░░░░░░  62%  …      │
│  POD ANALYST         ██████░░░░░░░░░░░░░░  31%  …      │
│  INFRA ANALYST       ░░░░░░░░░░░░░░░░░░░░   0%  ⏳     │
│  CONFIG ANALYST      ░░░░░░░░░░░░░░░░░░░░   0%  ⏳     │
│  SYNTHESIS           ░░░░░░░░░░░░░░░░░░░░   0%  ⏳     │
│                                                         │
│  LIVE LOG ─────────────────────────────────────────     │
│  [14:03:17] ⚡ Triage: postgres-0 CrashLoopBackOff      │
│  [14:03:18] ⚡ Triage: api-server 0/3 replicas          │
│  [14:03:19] 🔍 Archaeology: cluster born 47 days ago    │
│  [14:03:20] 🔍 Archaeology: ConfigMap modified 7h ago   │
│  [14:03:21] 🤖 Pod Analyst: analyzing previous logs...  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Screen 3: FINDINGS EXPLORER                            │
│                                                         │
│  ╔═══════════════════════════════════════════════╗      │
│  ║  3 CRITICAL  ·  2 WARNING  ·  1 INFO  ·  91% conf ║  │
│  ╚═══════════════════════════════════════════════╝      │
│                                                         │
│  ROOT CAUSE: ConfigMap 'db-config' missing DB_NAME key  │
│  CHAIN: ConfigMap edit → postgres crash → api cascade   │
│                                                         │
│  ┌─ FINDINGS ──────────────────────── [Filter: ALL ▼] ─┐│
│  │ ▼ 🔴 CRITICAL  postgres-0 CrashLoopBackOff           ││
│  │   Cause: permission denied /var/lib/postgresql/data  ││
│  │   Confidence: 94%  [Evidence]  [YAML Fix]  [Simulate]││
│  │                                                       ││
│  │ ▶ 🔴 CRITICAL  api-server 0/3 replicas (cascade)     ││
│  │ ▶ 🔴 CRITICAL  worker-1 MemoryPressure (87%)         ││
│  │ ▶ 🟡 WARNING   PVC usage 78% growing 0.8GB/day       ││
│  │ ▶ 🟡 WARNING   TLS cert expires in 3 days            ││
│  │ ▶ 🔵 INFO      Deployment rollout stuck (RS v1→v2)   ││
│  └───────────────────────────────────────────────────── ┘│
│                                                          │
│  ⚡ PREDICTION: worker-1 OOMKill in ~1.4 hours           │
│  [q]uit [t]imeline [i]nterview [Tab] expand/collapse     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Screen 4: TIMELINE VIEW                                │
│                                                         │
│  Cluster History ─ 47 days reconstructed from metadata │
│                                                         │
│  47d ago ──● Cluster created                            │
│  23d ago ──● api-server v1 deployed                     │
│  14d ago ──● api-server updated to v2 (RS rollout)      │
│   7d ago ──● ConfigMap 'db-config' MODIFIED ← TRIGGER   │
│            │                                            │
│   6h ago ──●─── postgres-0 first crash (14:03:17)       │
│   5h58m ──●─── api-server DB connection lost            │
│   5h52m ──●─── CrashLoopBackOff began                   │
│   5h30m ──●─── worker-1 memory pressure (87%)           │
│     NOW  ──●─── Bundle captured                         │
│            │                                            │
│  PREDICTED:│                                            │
│   +1.4h ───●... worker-1 OOMKill (if no intervention)   │
│   +6.1d ───●... PVC full                                │
│                                                         │
│  [←/→] scroll  [Enter] expand event  [b]ack to findings │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Screen 5: FORENSIC INTERVIEW                           │
│                                                         │
│  Ask anything about this bundle. Every answer is        │
│  grounded in evidence — no hallucination.               │
│                                                         │
│  ┌─ HISTORY ──────────────────────────────────────────┐ │
│  │ You: When did this problem start?                   │ │
│  │                                                     │ │
│  │ AI: The cascade began ~6 hours ago.                 │ │
│  │     Evidence: events/default.json shows first       │ │
│  │     Warning for postgres-0 at 14:03:17. Prior       │ │
│  │     to that, no warnings exist for 23 days.         │ │
│  │     ConfigMap modified ~7h ago — likely trigger.    │ │
│  │     Confidence: 87%                                 │ │
│  │     ⚠ Cannot determine if change was intentional.  │ │
│  └────────────────────────────────────────────────── ─┘ │
│                                                         │
│  > [________________________________________] [ENTER]   │
│                                                         │
│  [b]ack  [c]lear history  [e]xport transcript           │
└─────────────────────────────────────────────────────────┘
```

### TUI Component Tree

```python
BundleAnalyzerApp(App)
├── WelcomeScreen(Screen)
│   ├── Header
│   ├── BundlePathInput(Input)
│   ├── DiffModeToggle(Switch)
│   ├── ContextTextArea(TextArea)       # ISV app context injection
│   └── RecentBundlesList(ListView)
│
├── AnalysisScreen(Screen)
│   ├── Header
│   ├── ProgressTable(DataTable)        # live updating progress rows
│   ├── LiveLogView(RichLog)            # streaming events
│   └── Footer
│
├── FindingsScreen(Screen)
│   ├── Header
│   ├── SummaryPanel(Static)            # counts + root cause
│   ├── PredictionBanner(Static)        # forward prediction
│   ├── FindingsTree(Tree)              # collapsible findings
│   └── Footer with keybinds
│
├── TimelineScreen(Screen)
│   ├── Header
│   ├── TimelineWidget(ScrollableContainer)
│   │   └── TimelineEvent(Static) × N
│   └── Footer
│
└── InterviewScreen(Screen)
    ├── Header
    ├── ChatHistory(RichLog)
    ├── QuestionInput(Input)
    └── Footer
```

---

## 3. CORE ENGINE ARCHITECTURE

### 3.1 The Orchestrator (Central Brain)

The orchestrator reads triage output and builds a **dynamic work tree** — it decides which analysts to run, in what order, and with what context.

```python
class Orchestrator:
    """
    Reads triage result, builds analysis plan, executes it.
    Emits progress events that TUI subscribes to.
    """

    async def analyze(self, bundle_path: str, context: AppContext | None) -> AnalysisResult:
        # Phase 1: Extract + Index (always runs)
        bundle = await self.extractor.extract(bundle_path)
        index = await self.indexer.index(bundle)

        # Phase 2: Read metadata (always first)
        metadata = self.read_bundle_metadata(index)
        existing_analysis = self.read_existing_analysis(index)  # if present

        # Phase 3: Deterministic triage (always runs, no AI)
        triage = await self.triage_engine.run(index)
        self.emit("triage_complete", triage)

        # Phase 4: Build work tree based on what triage found
        work_tree = self.build_work_tree(triage, index)
        # work_tree decides: which analysts, which novel engines, what order

        # Phase 5: Execute work tree (parallel where possible)
        results = await self.execute_work_tree(work_tree, bundle, context)

        # Phase 6: Synthesis
        final = await self.synthesizer.synthesize(results, existing_analysis)
        return final


class WorkTree:
    """
    Dynamic execution plan built from triage findings.

    Example: if triage finds OOMKilled pods + node memory pressure:
      → MUST run: InfraAnalyst, PodAnalyst
      → SKIP: ConfigAnalyst (no config issues found)
      → ORDER: InfraAnalyst first (context feeds PodAnalyst)

    If triage finds nothing:
      → Run all analysts anyway (absence of obvious issues
        doesn't mean no issues — this is the silence detection case)
    """
    nodes: list[WorkNode]
    edges: list[tuple[WorkNode, WorkNode]]  # dependencies
```

### 3.2 Bundle Parser — Adaptive, Resilient

```python
class BundleIndex:
    """
    Walks extracted bundle directory, discovers what exists.
    Never assumes a file is present — always checks.
    """

    def __init__(self, root: Path):
        self.root = root
        self.manifest = {}      # path → file type
        self.namespaces = []    # discovered namespaces
        self.has = {}           # "pods": True, "node_metrics": False, etc.

    def read(self, path: str, required=False) -> dict | list | str | None:
        """
        Safe reader. Returns None if file missing.
        Never raises on missing files.
        Records RBAC errors if present.
        Handles ***HIDDEN*** markers in content.
        """

    def stream_log(self, pod: str, container: str, previous=False) -> Iterator[str]:
        """
        Stream log file line by line — never loads full log into memory.
        Reads LAST N lines for current logs (crashes at end).
        Reads FIRST + LAST N lines for previous logs (context + crash).
        """
```

### 3.3 Triage Engine (Layer 1 — Deterministic, No AI)

```python
# Each scanner is independent, fast, zero AI cost

class PodScanner:
    """
    Scans all pods/[namespace]/[pod].json files.
    Detects: CrashLoopBackOff, OOMKilled, ImagePullBackOff,
             Pending, Evicted, Terminating (stuck),
             High restart counts, Failed init containers
    """

class NodeScanner:
    """
    Scans cluster-resources/nodes.json + node-metrics/
    Detects: MemoryPressure, DiskPressure, PIDPressure,
             NotReady, Unschedulable, Resource exhaustion,
             Allocatable vs requested ratio > 90%
    """

class DeploymentScanner:
    """
    Scans deployments + replicasets.
    Detects: desired != ready, stuck rollouts (multiple RS exist),
             unavailable replicas, paused deployments
    """

class EventScanner:
    """
    Scans events/[namespace].json across ALL namespaces.
    Sorts by timestamp globally.
    Separates Warning events from Normal events.
    Builds pre-sorted event timeline for archaeology engine.
    """

class ConfigScanner:
    """
    Scans pod specs for referenced ConfigMaps and Secrets.
    Cross-references against actual ConfigMap/Secret files.
    Detects: broken references, missing keys, wrong namespaces.
    Also detects: Services with no matching Endpoints (broken selectors)
    """

class DriftScanner:
    """
    NEW: Systematic spec vs status comparison across all resource types.
    For every resource: compare spec (intent) vs status (reality).
    Any divergence is a finding.
    """

class SilenceScanner:
    """
    NEW: Detects pods that SHOULD have logs but don't.
    Logic: if pod has been Running for >5min and log file
    is empty or missing → flag as suspicious silence.
    Also: RBAC errors that prevented data collection.
    """
```

---

## 4. NOVEL FEATURE ARCHITECTURES

### 4.1 TEMPORAL ARCHAEOLOGY ENGINE

**What it does**: Reconstructs weeks of cluster history from a single snapshot using resource metadata timestamps.

**Input**: All JSON files in cluster-resources/
**Output**: Ordered list of `HistoricalEvent` objects spanning cluster lifetime

```python
class TemporalArchaeologyEngine:
    """
    Mines timestamps from every resource's metadata to reconstruct
    cluster history without any live access.
    """

    TIMESTAMP_SOURCES = [
        # (resource_type, json_path_to_timestamp, event_description_template)
        ("namespace",    "metadata.creationTimestamp",     "Namespace {name} created"),
        ("deployment",   "metadata.creationTimestamp",     "Deployment {name} first deployed"),
        ("replicaset",   "metadata.creationTimestamp",     "Deployment {owner} updated (new RS)"),
        ("configmap",    "metadata.resourceVersion",       "ConfigMap {name} last modified"),
        # resourceVersion is monotonic — higher = more recent
        # delta between versions indicates relative recency
        ("pod",          "status.startTime",               "Pod {name} started"),
        ("pod",          "status.containerStatuses[].lastState.terminated.finishedAt",
                                                           "Pod {name} last crashed"),
        ("event",        "firstTimestamp",                 "{reason} on {involvedObject}"),
        ("event",        "lastTimestamp",                  "{reason} last seen on {involvedObject}"),
        ("certificate",  "notAfter",                       "TLS cert {name} expires"),
    ]

    def reconstruct(self, index: BundleIndex) -> Timeline:
        events = []
        for source in self.TIMESTAMP_SOURCES:
            events.extend(self._extract_events(index, source))

        # Sort all events globally by timestamp
        events.sort(key=lambda e: e.timestamp)

        # Identify clusters of activity (things that happened together)
        # and annotate with causal links
        return Timeline(events=events, causal_chains=self._find_chains(events))

    def _find_chains(self, events: list[HistoricalEvent]) -> list[CausalChain]:
        """
        Identify event sequences that are causally linked.
        Heuristic: events within a 5-minute window on related objects
        are likely causally connected.

        Example chain:
          14:01 ConfigMap modified
          14:03 Pod restarts (same namespace, references that ConfigMap)
          14:05 Deployment unhealthy
          → These 3 form a causal chain
        """
```

**AI prompt for archaeology context**:
```
You are analyzing a Kubernetes cluster's history reconstructed from
resource metadata timestamps. The following timeline was extracted
from a single support bundle snapshot.

Timeline (sorted chronologically):
{timeline_json}

Bundle metadata: collected at {collection_time}
Cluster age: {cluster_age}
Most recent modification to a resource: {most_recent_change}

Identify:
1. The "trigger event" — the earliest event that started the current
   failure chain. What was modified/changed that kicked this off?
2. How long has the cluster been in its current broken state?
3. What was the last "known good" state? When was it?
4. Are there recurring patterns (same pod crashing periodically)?

Every claim must cite specific timestamps and resource names from the data.
```

---

### 4.2 FORWARD PREDICTION ENGINE

**What it does**: Uses current state + rate-of-change signals to predict future failures.

**Input**: TriageResult + NodeMetrics + pod restart history
**Output**: List of `PredictedFailure` with estimated time-to-failure

```python
@dataclass
class PredictedFailure:
    resource: str               # "worker-1 node"
    failure_type: str           # "OOMKill"
    estimated_eta: timedelta    # ~1.4 hours
    confidence: float           # 0.73
    evidence: list[str]         # ["memory at 87%", "growing 2.3MB/min"]
    prevention: str             # "Increase memory limit or add node"


class ForwardPredictionEngine:

    def predict(self, triage: TriageResult, index: BundleIndex) -> list[PredictedFailure]:
        predictions = []
        predictions.extend(self._predict_oom(triage, index))
        predictions.extend(self._predict_storage_full(index))
        predictions.extend(self._predict_crashloop_permanent(triage))
        predictions.extend(self._predict_cert_expiry(index))
        predictions.extend(self._predict_replica_exhaustion(triage))
        return sorted(predictions, key=lambda p: p.estimated_eta)

    def _predict_oom(self, triage, index) -> list[PredictedFailure]:
        """
        For each node with memory pressure:
          1. Read current memory usage from node-metrics
          2. Look at pod restartCounts + timestamps to estimate growth rate
             (each OOMKill = memory was at 100% at that time)
          3. Linear extrapolation to 100%

        Formula:
          current_usage_pct = allocatedMi / allocatableMi
          growth_rate = estimate from restart frequency
          time_to_oom = (1.0 - current_usage_pct) / growth_rate
        """

    def _predict_crashloop_permanent(self, triage) -> list[PredictedFailure]:
        """
        CrashLoopBackOff uses exponential backoff capped at 5 minutes.
        Once at cap, pod is effectively permanently broken.
        
        restartCount >= 10 → at 5min cap → flag as "permanently stuck
        without intervention" with ETA = NOW (already stuck)
        """

    def _predict_storage_full(self, index) -> list[PredictedFailure]:
        """
        If node-metrics includes disk usage over time snapshots:
          compute growth rate → extrapolate to 100%
        If only single snapshot:
          use current% as signal, flag if >80% with warning
        """

    def _predict_cert_expiry(self, index) -> list[PredictedFailure]:
        """
        Parse TLS certificate data from cluster-resources.
        Calculate days until notAfter.
        """
```

---

### 4.3 FIX SIMULATION ENGINE

**What it does**: After a fix is proposed, reasons about the cascade effects of applying it.

**Input**: ProposedFix + full AnalysisResult
**Output**: SimulationResult with impacts, risks, recovery timeline

```python
class FixSimulationEngine:
    """
    Uses Claude to reason about the counterfactual:
    "If we apply fix X, what changes across the whole system?"
    """

    async def simulate(
        self,
        fix: ProposedFix,
        analysis: AnalysisResult,
        index: BundleIndex
    ) -> SimulationResult:

        prompt = self._build_simulation_prompt(fix, analysis, index)
        response = await self.claude.complete(prompt)
        return self._parse_simulation_result(response)

    def _build_simulation_prompt(self, fix, analysis, index) -> str:
        return f"""
You are simulating the effect of applying a fix to a broken Kubernetes cluster.
You have full knowledge of the cluster state from the support bundle.

PROPOSED FIX:
{fix.description}

YAML CHANGE:
{fix.yaml_patch}

CURRENT CLUSTER STATE (from bundle):
{analysis.cluster_summary}

KNOWN BROKEN COMPONENTS:
{analysis.findings_summary}

Simulate applying this fix. For EACH component in the cluster:
1. Would this fix resolve its issue? (yes/no/partial)
2. Could this fix cause new issues? (cascade effects)
3. Are there residual problems that would remain?
4. Estimated time to healthy state after applying fix?

Also identify:
- Any components that would need manual intervention AFTER this fix
- Any queue backlogs, connection pools, or state that accumulated
  during the outage that need to drain/recover
- Any UNRELATED issues this fix does NOT address

Format as structured JSON. Every claim needs evidence from the bundle data.
"""
```

**Output structure**:
```python
@dataclass
class SimulationResult:
    fix_resolves: list[str]         # components that would recover
    fix_creates: list[str]          # new issues the fix might cause
    residual_issues: list[str]      # unrelated issues remaining
    recovery_timeline: str          # "~8 minutes to full health"
    manual_steps_after: list[str]   # things human must do post-fix
    confidence: float
```

---

### 4.4 SILENCE DETECTION ENGINE

**What it does**: Flags pods that should be producing logs but aren't — absence as signal.

```python
class SilenceDetectionEngine:

    def detect(self, index: BundleIndex, triage: TriageResult) -> list[SilenceSignal]:
        signals = []

        for pod in self._get_all_pods(index):
            for container in pod.containers:
                log_path = index.get_log_path(pod.namespace, pod.name, container.name)

                # Case 1: Log file completely absent
                if not log_path:
                    if self._should_have_logs(pod, container):
                        signals.append(SilenceSignal(
                            pod=pod.name,
                            container=container.name,
                            type="LOG_FILE_MISSING",
                            # Could be: RBAC prevented collection,
                            # container never started, log rotated
                            possible_causes=self._diagnose_missing_log(pod, index)
                        ))

                # Case 2: Log file exists but is empty
                elif index.get_file_size(log_path) == 0:
                    if pod.age_minutes > 5 and pod.status == "Running":
                        signals.append(SilenceSignal(
                            pod=pod.name,
                            container=container.name,
                            type="EMPTY_LOG_RUNNING_POD",
                            # Strong signal: app started, running, but silent
                            # → deadlock, waiting on dependency, logging misconfigured
                            severity="WARNING"
                        ))

                # Case 3: Log has data but previous log is missing
                # (pod has restarted but previous logs weren't captured)
                elif not index.get_previous_log_path(pod.namespace, pod.name, container.name):
                    if container.restart_count > 0:
                        signals.append(SilenceSignal(
                            pod=pod.name,
                            type="PREVIOUS_LOG_MISSING_DESPITE_RESTARTS",
                            note="Cannot analyze pre-crash state"
                        ))

        # Also check RBAC errors in bundle
        for rbac_error in index.rbac_errors:
            signals.append(SilenceSignal(
                type="RBAC_COLLECTION_BLOCKED",
                namespace=rbac_error.namespace,
                note=f"Bundle collector couldn't access {rbac_error.namespace}: "
                     f"analysis of this namespace is INCOMPLETE"
            ))

        return signals
```

---

### 4.5 MULTI-BUNDLE DIFF ENGINE

**What it does**: Compares two bundles (before/after) and identifies what changed.

**CLI**: `bundle-analyzer diff before.tar.gz after.tar.gz`
**TUI**: second file input field on welcome screen

```python
class MultiBundleDiffEngine:
    """
    Answers: "What changed between these two bundle snapshots?"
    This is the most powerful feature for ISV engineers who receive
    repeated bundles from the same customer.
    """

    def diff(self, bundle_a: BundleIndex, bundle_b: BundleIndex) -> DiffResult:
        return DiffResult(
            # Structural changes
            added_resources=self._find_added(bundle_a, bundle_b),
            removed_resources=self._find_removed(bundle_a, bundle_b),

            # Config changes (the most important — usually the root cause)
            configmap_diffs=self._diff_configmaps(bundle_a, bundle_b),
            secret_diffs=self._diff_secrets(bundle_a, bundle_b),   # keys only, not values

            # Health changes
            pod_status_changes=self._diff_pod_statuses(bundle_a, bundle_b),
            deployment_changes=self._diff_deployments(bundle_a, bundle_b),
            node_changes=self._diff_nodes(bundle_a, bundle_b),

            # Metric changes
            memory_delta=self._diff_memory(bundle_a, bundle_b),
            restart_count_delta=self._diff_restarts(bundle_a, bundle_b),

            # New errors not in bundle_a
            new_error_patterns=self._diff_log_errors(bundle_a, bundle_b),
        )

    def _diff_configmaps(self, a, b) -> list[ConfigMapDiff]:
        """
        For each ConfigMap present in both bundles:
        - Which keys were added/removed/modified?
        - This is the #1 signal for "what was changed that broke things"
        """

    def _diff_log_errors(self, a, b) -> list[str]:
        """
        Find error patterns in bundle_b logs that don't appear in bundle_a.
        These are new errors introduced between the two snapshots.
        """
```

**AI prompt for diff analysis**:
```
You are analyzing the DIFFERENCE between two Kubernetes support bundles
from the same cluster, captured at different times.

BUNDLE A (earlier/healthy):  {bundle_a_time}
BUNDLE B (later/broken):     {bundle_b_time}

CHANGES DETECTED:
{diff_json}

Your task:
1. Identify the most likely ROOT CAUSE of the change in cluster health.
   Look specifically for: ConfigMap/Secret changes, image tag changes,
   resource limit changes, new deployments.
2. Build the causal chain: "X was changed, which caused Y, which caused Z"
3. Verify: do the new log errors in bundle B align with the config changes?
4. Generate: the specific undo/rollback that would restore bundle A's state.

Every claim must cite the specific diff evidence.
```

---

### 4.6 ISV CONTEXT INJECTION

**What it does**: Lets the vendor paste their app's context (Helm values schema, README, known issues) to make analysis app-aware.

```python
@dataclass
class AppContext:
    raw_text: str   # whatever the ISV pasted

    # parsed from raw_text by Claude in a preprocessing step:
    known_config_keys: list[str]   # env vars / config keys this app uses
    services: list[str]            # named services this app expects
    known_issues: list[str]        # documented known problems
    version: str | None            # app version if mentioned


class ContextInjector:
    """
    Takes raw ISV context text, extracts structured info,
    injects it into all subsequent AI prompts.
    """

    async def process(self, raw_context: str) -> AppContext:
        """Pre-process context text with Claude to extract structure."""

    def inject_into_prompt(self, prompt: str, context: AppContext) -> str:
        """
        Prepends app-specific context to analyst prompts.
        This transforms generic K8s analysis into app-aware diagnosis.

        Example injection:
        "VENDOR APP CONTEXT:
         This is [AppName]. It expects these env vars: DB_HOST, DB_PORT,
         DB_NAME, REDIS_URL. Known issue: DB_NAME cannot be empty string.
         The 'api' service depends on 'postgres' and 'redis' services."
        """
```

---

### 4.7 DESIRED vs ACTUAL DRIFT SCANNER

**What it does**: Systematic comparison of every resource's spec (intent) vs status (reality).

```python
class DriftScanner:
    """
    For each resource type, compares spec vs status.
    Any divergence that K8s hasn't automatically resolved
    is a potential issue.
    """

    DRIFT_CHECKS = {
        "Deployment": [
            ("spec.replicas", "status.readyReplicas",
             "Replica count mismatch: wanted {spec}, have {status}"),
            ("spec.template.spec.containers[].image",
             "status...containerStatuses[].image",
             "Image mismatch: spec says {spec}, running {status}"),
        ],
        "Service": [
            ("spec.selector", "→ matching_pods",
             "Service selector matches {n} pods (expected >0)"),
        ],
        "StatefulSet": [
            ("spec.replicas", "status.readyReplicas", "..."),
            ("spec.volumeClaimTemplates", "→ bound_pvcs", "..."),
        ],
        "ConfigMap": [
            ("data.keys", "→ referenced_keys_from_pods",
             "Pod references key {key} which is missing from ConfigMap"),
        ],
        "Node": [
            ("status.allocatable.memory", "→ total_requested",
             "Memory over-committed: {pct}% allocated"),
        ],
    }
```

---

### 4.8 "WHAT I CAN'T TELL YOU" — UNCERTAINTY ENGINE

**What it does**: Explicit uncertainty declaration — every analysis report ends with what the AI couldn't determine and why.

```python
class UncertaintyEngine:
    """
    After all analysis is complete, audits what data was
    unavailable and what questions therefore remain unanswered.
    """

    def audit(self, index: BundleIndex, analysis: AnalysisResult) -> UncertaintyReport:
        gaps = []

        # 1. Check for redacted data that might affect conclusions
        if analysis.mentions_connection_errors and index.has_redacted_secrets:
            gaps.append(UncertaintyGap(
                question="Are the database credentials correct?",
                reason="Secrets are redacted in this bundle",
                to_investigate="Ask customer to verify credentials manually",
                impact="HIGH — could be the actual root cause"
            ))

        # 2. Check for missing collectors
        if not index.has("node_metrics"):
            gaps.append(UncertaintyGap(
                question="Is resource pressure causing the failures?",
                reason="node-metrics collector was not included in this bundle",
                to_investigate="Re-collect with node metrics enabled",
                collect_command="kubectl support-bundle --add-collectors node-metrics.yaml"
            ))

        # 3. Check for RBAC-blocked namespaces
        for blocked in index.rbac_errors:
            gaps.append(UncertaintyGap(
                question=f"What is the state of namespace {blocked.namespace}?",
                reason="RBAC prevented collection",
            ))

        # 4. Single-point-in-time metrics limitation
        if analysis.has_resource_pressure_findings:
            gaps.append(UncertaintyGap(
                question="Is the memory issue a leak or a traffic spike?",
                reason="Bundle contains only one metrics snapshot — no trend data",
                to_investigate="Compare with older bundle or enable continuous metrics"
            ))

        return UncertaintyReport(gaps=gaps)
```

---

### 4.9 FORENSIC INTERVIEW MODE

**What it does**: Replaces generic Q&A with a structured forensic interview where every answer requires evidence citation from the bundle.

```python
class ForensicInterviewEngine:
    """
    Grounded Q&A — every answer must cite specific evidence from the bundle.
    The AI is instructed to say "I don't know" rather than hallucinate.
    """

    SYSTEM_PROMPT = """
You are a Kubernetes forensics expert analyzing a support bundle.
You have access to the following data from the bundle:
{bundle_context}

STRICT RULES:
1. Every factual claim MUST cite the specific file and data that supports it.
   Format: "Evidence: [filename] shows [specific data]"
2. If you cannot find evidence in the bundle data, say explicitly:
   "I cannot determine this from the available bundle data"
3. Always end answers with a confidence score (0-100%)
4. Always state what ADDITIONAL data would be needed to answer with more certainty
5. Never infer beyond what the data supports

You are not a general K8s assistant. You only know what is in this specific bundle.
"""

    async def ask(
        self,
        question: str,
        history: list[Message],
        bundle_context: BundleContext
    ) -> ForensicAnswer:
        """
        Builds a prompt with relevant bundle files as context.
        Uses semantic search to find the most relevant files for the question.
        Enforces evidence citation in the response.
        """

        # Find relevant context for this specific question
        relevant_files = self._find_relevant_context(question, bundle_context)

        response = await self.claude.complete(
            system=self.SYSTEM_PROMPT.format(bundle_context=relevant_files),
            messages=history + [{"role": "user", "content": question}]
        )

        return ForensicAnswer(
            answer=response.text,
            evidence_citations=self._extract_citations(response.text),
            confidence=self._extract_confidence(response.text),
            data_gaps=self._extract_gaps(response.text)
        )
```

---

## 5. AI PROMPT ARCHITECTURE

### Token Budget Management

```
Total Claude context window: 200K tokens

Budget allocation per analysis:
  Bundle metadata + version.yaml:          ~500 tokens
  Existing analysis.json (if present):   ~2,000 tokens
  Triage result (structured):            ~3,000 tokens
  Archaeology timeline:                  ~2,000 tokens
  Pod analyst context (per pod):         ~8,000 tokens × N failing pods
  Node analyst context:                  ~5,000 tokens
  Config analyst context:                ~4,000 tokens
  ISV app context (if provided):         ~2,000 tokens
  Synthesis (all findings):              ~6,000 tokens

Log truncation strategy:
  Current logs:  last 200 lines (crash is at the end)
  Previous logs: first 50 + last 150 lines (startup context + crash)
  Max per container: 500 lines total
```

### Structured Output Schema

Every AI analyst returns structured JSON — never free-form text:

```python
@dataclass
class AnalystOutput:
    findings: list[Finding]
    root_cause: RootCause | None
    confidence: float          # 0.0–1.0
    evidence: list[Evidence]   # specific file + data citations
    remediation: list[Fix]
    uncertainty: list[str]     # things analyst couldn't determine

@dataclass
class Finding:
    id: str
    severity: Literal["critical", "warning", "info"]
    type: str                  # "CrashLoopBackOff", "OOMKill", etc.
    resource: str              # "pod/default/postgres-0"
    symptom: str               # observable effect
    root_cause: str            # underlying reason
    evidence: list[Evidence]
    fix: Fix | None
    confidence: float

@dataclass
class Fix:
    description: str
    yaml_patch: str | None     # exact YAML to apply
    commands: list[str]        # exact kubectl commands
    risk: str                  # "safe" | "disruptive" | "needs-verification"
```

---

## 6. DATA FLOW DIAGRAM

```
bundle.tar.gz
     │
     ▼
┌─────────────────┐
│   EXTRACTOR     │ → /tmp/bundle-{id}/ (streamed, never full RAM)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    INDEXER      │ → BundleIndex (manifest of all files + what exists)
│                 │   reads: version.yaml, analysis.json, RBAC errors
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│              TRIAGE ENGINE (parallel)               │
│  PodScanner ──┐                                     │
│  NodeScanner ─┤                                     │
│  DeployScanner┤→ TriageResult (structured, fast)    │
│  EventScanner ┤                                     │
│  ConfigScanner┤                                     │
│  DriftScanner ┤                                     │
│  SilenceDetect┘                                     │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  ORCHESTRATOR   │ → builds WorkTree from TriageResult
│  (work tree)    │   decides which analysts run + order
└────────┬────────┘
         │
    ┌────┴─────────────────┐
    │                      │
    ▼                      ▼
┌──────────┐        ┌──────────────────┐
│ARCHAEOLOGY│        │ PARALLEL AI CALLS│
│ENGINE     │        │                  │
│           │        │  PodAnalyst      │
│timeline + │        │  NodeAnalyst     │
│causal     │        │  ConfigAnalyst   │
│chains     │        │                  │
└─────┬─────┘        └──────┬───────────┘
      │                     │
      └──────────┬──────────┘
                 │
                 ▼
    ┌────────────────────────┐
    │  PREDICTION ENGINE     │ → PredictedFailures
    │  FIX SIMULATION        │ → SimulationResults
    │  UNCERTAINTY AUDIT     │ → UncertaintyReport
    └────────────┬───────────┘
                 │
                 ▼
    ┌────────────────────────┐
    │  SYNTHESIS PASS        │ → final AnalysisResult
    │  (cross-correlation)   │   (root cause, ranked findings,
    │                        │    timeline, predictions, fixes,
    │                        │    uncertainty, what changed)
    └────────────────────────┘
                 │
                 ▼
         TUI RENDERS REPORT
```

---

## 7. PROJECT FILE STRUCTURE

```
bundle-analyzer/
│
├── README.md                          ← 5-min setup instructions
├── MY_APPROACH_AND_THOUGHTS.md        ← 500-word approach doc
├── ARCHITECTURE.md                    ← this file
├── docker-compose.yml                 ← optional: runs as web service
├── Makefile                           ← make run / make test / make bundle
├── .env.example                       ← ANTHROPIC_API_KEY=your_key_here
├── requirements.txt
│
├── bundle_analyzer/                   ← main Python package
│   ├── __init__.py
│   ├── cli.py                         ← entry point: bundle-analyzer command
│   │
│   ├── tui/                           ← Textual TUI
│   │   ├── app.py                     ← BundleAnalyzerApp(App)
│   │   ├── screens/
│   │   │   ├── welcome.py
│   │   │   ├── analysis.py
│   │   │   ├── findings.py
│   │   │   ├── timeline.py
│   │   │   └── interview.py
│   │   ├── widgets/
│   │   │   ├── findings_tree.py
│   │   │   ├── timeline_view.py
│   │   │   ├── progress_table.py
│   │   │   └── yaml_viewer.py
│   │   └── app.tcss                   ← Textual CSS stylesheet
│   │
│   ├── bundle/                        ← parsing layer
│   │   ├── extractor.py               ← tar.gz → temp dir (streaming)
│   │   ├── indexer.py                 ← walk dir → BundleIndex
│   │   └── reader.py                  ← typed safe readers
│   │
│   ├── triage/                        ← layer 1: deterministic
│   │   ├── engine.py                  ← runs all scanners
│   │   ├── pod_scanner.py
│   │   ├── node_scanner.py
│   │   ├── deployment_scanner.py
│   │   ├── event_scanner.py
│   │   ├── config_scanner.py
│   │   ├── drift_scanner.py
│   │   └── silence_scanner.py
│   │
│   ├── ai/                            ← layer 2: AI analysis
│   │   ├── orchestrator.py            ← work tree builder + executor
│   │   ├── analysts/
│   │   │   ├── pod_analyst.py
│   │   │   ├── node_analyst.py
│   │   │   └── config_analyst.py
│   │   ├── engines/
│   │   │   ├── archaeology.py         ← temporal reconstruction
│   │   │   ├── prediction.py          ← forward failure prediction
│   │   │   ├── simulation.py          ← fix simulation
│   │   │   ├── diff.py                ← multi-bundle diff
│   │   │   ├── silence.py             ← silence detection
│   │   │   ├── drift.py               ← spec vs actual
│   │   │   └── uncertainty.py         ← "what I can't tell you"
│   │   ├── synthesis.py               ← cross-correlation + final report
│   │   ├── interview.py               ← forensic interview mode
│   │   ├── context_injector.py        ← ISV app context
│   │   ├── prompts/                   ← all prompts as .py files
│   │   │   ├── pod_analyst.py
│   │   │   ├── archaeology.py
│   │   │   ├── synthesis.py
│   │   │   ├── interview.py
│   │   │   └── simulation.py
│   │   └── client.py                  ← Claude API wrapper w/ retry
│   │
│   └── models.py                      ← all Pydantic models
│
├── tests/
│   ├── test_extractor.py
│   ├── test_triage.py
│   ├── test_archaeology.py
│   ├── test_prediction.py
│   └── fixtures/                      ← sample bundle fragments for testing
│
└── demo-cluster/
    ├── setup.sh                       ← one-shot: install everything
    ├── kind-config.yaml
    ├── support-bundle-spec.yaml       ← custom collection spec
    ├── workloads/
    │   ├── 00-namespace.yaml
    │   ├── 01-postgres.yaml
    │   ├── 02-api-server.yaml
    │   ├── 03-frontend.yaml
    │   └── 04-redis.yaml
    └── failures/
        ├── break-oom.yaml
        ├── break-image.yaml
        ├── break-configmap.yaml
        ├── break-crashloop.yaml
        ├── break-pending.yaml
        └── break-probe.yaml
```

---

## 8. IMPLEMENTATION PHASES

```
PHASE 0 — Infrastructure (Day 1, ~3hrs)
  □ kind cluster setup
  □ Deploy workloads
  □ Introduce 6 failures
  □ Generate support bundle

PHASE 1 — Backend Core (Day 1-2, ~5hrs)
  □ Extractor (streaming tar)
  □ Indexer (adaptive, resilient)
  □ All 7 triage scanners
  □ Data models (Pydantic)

PHASE 2 — AI Pipeline (Day 2-3, ~6hrs)
  □ Claude API client (with retry/error handling)
  □ 3 parallel analysts
  □ Archaeology engine
  □ Prediction engine
  □ Synthesis pass
  □ Uncertainty audit
  □ Forensic interview

PHASE 3 — TUI (Day 3-4, ~5hrs)
  □ Textual app skeleton
  □ All 5 screens
  □ Streaming progress updates
  □ Findings tree widget
  □ Timeline widget

PHASE 4 — Novel Features (Day 4, ~4hrs)
  □ Multi-bundle diff
  □ Fix simulation
  □ Silence detection
  □ ISV context injection
  □ "What I can't tell you"

PHASE 5 — Delivery (Day 5, ~3hrs)
  □ Tests (5 minimum)
  □ README + .env.example + Makefile
  □ MY_APPROACH_AND_THOUGHTS.md
  □ docker-compose.yml
  □ Demo video recording
```

---

## 9. KEY DESIGN DECISIONS & RATIONALE

| Decision | Why |
|---|---|
| Textual TUI over web app | Engineers live in terminals. Runs over SSH. Signals you know the audience. |
| Deterministic triage before AI | Never waste tokens on things a regex can find. AI handles what rules can't. |
| Dynamic work tree | Smarter than always running all analysts. Shows AI orchestration thinking. |
| Streaming tar extraction | Bundles can be 500MB+. Loading into RAM would crash on large bundles. |
| Evidence citations required | Forces the AI to stay grounded. Every finding must have a "why". |
| Explicit uncertainty report | Trust. ISV engineers need to know what they DON'T know from the bundle. |
| Previous logs as first-class | Pre-crash logs are the most valuable data. Most tools ignore them. |
| Temporal archaeology | Unique insight: history is embedded in metadata. Nobody mines it this way. |
| Forward prediction | Transforms reactive debugging into proactive warning. Nobody does this offline. |