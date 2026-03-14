# My Approach and Thoughts

## The Core Insight

A support bundle is forensic evidence from a crime scene you can never visit. By the time an engineer opens it, the pods have restarted, the node has been drained, the OOM condition is gone. But the evidence is still there — in metadata timestamps, restart counts, condition transitions, and gaps between log entries. Most tools treat a bundle as a flat bag of YAML. Bundle Analyzer treats it as a temporal record: we reconstruct weeks of cluster history from a single snapshot by mining `lastTransitionTime`, `startedAt`, `finishedAt`, and event timestamps. This is temporal archaeology — turning a static dump into an incident timeline.

## Architecture Decisions

The system uses a strict two-layer design: deterministic triage first, AI second. Triage runs regex, threshold checks, and structural validation across pods, nodes, events, jobs, storage, and ingress. It catches CrashLoopBackOff, OOMKilled, image pull failures, pending pods, and failed probes in under a second at zero API cost. The AI layer only sees distilled findings, not raw logs. Triage catches 80% of what an engineer finds. AI catches the rest — cascade failures, subtle misconfigurations, the "why did this node go NotReady 47 seconds before that pod got OOMKilled."

The AI pipeline runs parallel analysts across fault domains: pod failures, node health, and configuration issues analyzed concurrently. Synthesis cross-correlates outputs to detect cascades — node memory pressure causing evictions causing deployment unavailability. The orchestrator builds its work tree from triage output, so if no storage issues exist, the storage analyst never runs.

We chose Textual because bundle analysis is an SSH-first workflow. On a 2am call, you are in a terminal on a jump box. You do not want port forwarding for a web dashboard. The TUI gives you findings, timeline, and forensic interview directly where you are working.

## Novel Features

Silence detection treats absence of expected data as a finding — a pod with 5 restarts but no previous container logs means missing pre-crash evidence, which is itself diagnostic. Forward predictions extrapolate trends: memory growth rates yield OOM ETAs, disk usage slopes yield time-to-full, restart intervals reveal crashloop trajectory. The uncertainty report states what the bundle cannot tell you — no metrics collector means no CPU history, no previous logs means no pre-crash state. Engineers need analysis boundaries, not just conclusions.

## Honest Limitations

Bundle Analyzer requires an actual support bundle; it cannot query a live cluster. Missing collectors mean missing data, and we say so. AI analysis adds roughly 30 seconds of latency — streaming is not yet implemented. Multi-bundle diff requires both bundles from the same cluster. The tool is as good as the bundle it receives.

## What I'd Build Next

Streaming AI responses into the TUI so reasoning appears in real time. A plugin system for ISV-specific heuristics — a Postgres operator needs different scanners than a message queue. Slack integration to post findings with one keybinding. A historical bundle store to track cluster health across deployments.
