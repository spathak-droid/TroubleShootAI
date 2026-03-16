# My Approach and Thoughts

## The Problem Nobody Has Solved Well

Kubernetes support bundles are forensic snapshots from incidents you can never revisit. By the time an engineer opens one, the pods have restarted, the node has been drained, the OOM condition is gone. Yet the evidence is preserved — in metadata timestamps, restart counts, condition transitions, and gaps between log entries. Every existing tool treats a bundle as a flat bag of YAML to keyword-search through. That's like handing a detective a crime scene and telling them to grep for clues.

My core insight: **a static bundle snapshot encodes weeks of cluster history if you know where to look.** `lastTransitionTime`, `startedAt`/`finishedAt`, event timestamps, and restart counts together reconstruct an incident timeline no human would manually piece together at 2am.

## Architecture: Triage Before Tokens

The system enforces a strict two-phase pipeline — deterministic triage first, AI second — because the most expensive mistake in AI tooling is spending tokens on what regex finds in milliseconds.

**Phase 1 (Triage)** runs 12 specialized scanners across fault domains: pods, nodes, events, jobs, storage, ingress, network policies, TLS, crashloops, silence detection, and change correlation. These catch CrashLoopBackOff, OOMKilled, image pull failures, pending pods, certificate expiry, and misconfigured policies — all in under a second at zero API cost, covering ~80% of actionable findings.

**Phase 2 (AI Analysis)** receives only distilled findings, never raw logs. Three parallel analysts (pod, node, configuration) run concurrently. A synthesis layer cross-correlates outputs to detect cascade failures — node memory pressure → evictions → deployment unavailability. The orchestrator dynamically skips irrelevant analysts: no storage issues means no storage tokens spent.

**Root Cause Analysis** generates hypotheses from correlated evidence, validates claims against bundle data, and produces confidence-scored diagnoses with explicit evidence citations. Every conclusion must be grounded.

## What Makes This Different

**Temporal archaeology.** We reconstruct timelines from metadata every other tool ignores. A node transitioning NotReady 47 seconds before an OOMKill isn't coincidence — it's causation.

**Silence detection.** Absence is signal. A pod with 5 restarts but no previous logs means missing pre-crash evidence. A namespace with deployments but no events means the event buffer rolled. We diagnose what's *missing*.

**Dependency graph walking.** We build resource graphs and walk causal chains (Deployment → ReplicaSet → Pod → Node), correlating failures across ownership boundaries humans trace manually.

**7-layer security.** Bundles contain secrets and infrastructure details. Our pipeline runs pattern detection, entropy-based secret detection, structural Kubernetes scrubbers (preserving diagnostic keys while redacting values), and prompt injection guards treating all log content as untrusted. Every redaction is audit-logged.

## Honest Limitations and What's Next

The tool is exactly as good as the bundle it receives. Missing collectors mean missing data — and we say so through an uncertainty report stating what the bundle *cannot* tell you. I chose honesty about analysis boundaries over hallucinated confidence.

Next: streaming AI reasoning, plugin system for ISV-specific heuristics, historical bundle comparison for degradation tracking, and webhooks for incident response integration.
