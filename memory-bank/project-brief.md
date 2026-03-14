# Project Brief

## What
AI-powered Kubernetes support bundle forensics tool. Analyzes support bundles (tar.gz collections of cluster state) to diagnose issues, reconstruct incident timelines, and predict future problems.

## Why
Support bundles contain rich diagnostic data but are tedious to analyze manually. Current tools (Troubleshoot.sh analyzers) only do basic checks. This tool adds temporal archaeology, forward prediction, silence detection, and AI-driven root cause analysis.

## Key Differentiators
1. **Temporal archaeology** — mines metadata timestamps to reconstruct incident timelines
2. **Forward prediction** — extrapolates trends (OOM ETAs, disk growth)
3. **Silence detection** — flags absence of expected data as diagnostic signal
4. **Explicit uncertainty** — reports what the bundle can't tell you
5. **Evidence-grounded AI** — every finding cites source files
6. **7-layer security** — enterprise-grade data protection for bundle contents

## Interfaces
1. **Web app** (primary) — Next.js frontend + FastAPI backend
2. **CLI fallback** — `bundle-analyzer ./bundle.tar.gz` outputs HTML report

## Target Users
Kubernetes engineers, SREs, support teams analyzing customer bundles
