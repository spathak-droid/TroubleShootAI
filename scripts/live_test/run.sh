#!/bin/bash
# =============================================================================
# Live End-to-End Test for TroubleShootAI
#
# Creates a Kind cluster, deploys broken workloads, collects a support bundle,
# and runs the analyzer against it.
#
# Usage:
#   ./scripts/live_test/run.sh           # full run (create cluster + test)
#   ./scripts/live_test/run.sh --skip-cluster  # reuse existing cluster
#   ./scripts/live_test/run.sh --cleanup  # just delete the cluster
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLUSTER_NAME="troubleshoot-test"
BUNDLE_DIR="$PROJECT_DIR/test-bundle-output"
KUBECONFIG_FILE=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }

# ── Handle flags ─────────────────────────────────────────────────────────────

if [[ "${1:-}" == "--cleanup" ]]; then
    log "Deleting Kind cluster '$CLUSTER_NAME'..."
    kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || true
    ok "Cluster deleted"
    exit 0
fi

SKIP_CLUSTER=false
if [[ "${1:-}" == "--skip-cluster" ]]; then
    SKIP_CLUSTER=true
fi

# ── Prerequisites ────────────────────────────────────────────────────────────

log "Checking prerequisites..."
for cmd in docker kind kubectl; do
    if ! command -v "$cmd" &>/dev/null; then
        fail "$cmd not found. Please install it first."
        exit 1
    fi
done

# Check Docker is running
if ! docker info &>/dev/null; then
    fail "Docker is not running. Please start Docker Desktop."
    exit 1
fi
ok "Prerequisites OK (docker, kind, kubectl)"

# ── Step 1: Create Kind cluster ──────────────────────────────────────────────

if [[ "$SKIP_CLUSTER" == "false" ]]; then
    log "Creating Kind cluster '$CLUSTER_NAME'..."

    # Delete existing cluster if any
    kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || true

    kind create cluster \
        --name "$CLUSTER_NAME" \
        --config "$SCRIPT_DIR/kind-config.yaml" \
        --wait 60s

    ok "Kind cluster created"
else
    log "Skipping cluster creation (--skip-cluster)"
fi

# Wait for nodes to be ready
log "Waiting for nodes to be Ready..."
kubectl wait --for=condition=Ready nodes --all --timeout=120s
ok "All nodes ready"

echo ""
kubectl get nodes -o wide
echo ""

# ── Step 2: Deploy broken workloads ──────────────────────────────────────────

log "Deploying broken workloads (5 failure scenarios)..."
kubectl apply -f "$SCRIPT_DIR/broken-workloads.yaml"
ok "Workloads deployed"

# Wait for failures to manifest
log "Waiting 30s for failures to manifest (crashloops, image pulls, OOMs)..."
sleep 10
echo -ne "  ${CYAN}10s...${NC}"
sleep 10
echo -ne " ${CYAN}20s...${NC}"
sleep 10
echo -e " ${CYAN}30s${NC}"

echo ""
log "Current pod status:"
kubectl get pods -o wide --show-labels
echo ""

log "Warning events:"
kubectl get events --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | tail -20
echo ""

# ── Step 3: Collect support bundle ───────────────────────────────────────────

log "Collecting support bundle..."

# Check if kubectl support-bundle plugin is installed
if kubectl support-bundle version &>/dev/null 2>&1; then
    log "Using Troubleshoot kubectl plugin..."
    mkdir -p "$BUNDLE_DIR"
    kubectl support-bundle "$SCRIPT_DIR/support-bundle.yaml" \
        --output "$BUNDLE_DIR/bundle.tar.gz" \
        --interactive=false 2>&1 || true

    if [[ -f "$BUNDLE_DIR/bundle.tar.gz" ]]; then
        ok "Bundle collected at $BUNDLE_DIR/bundle.tar.gz"
    else
        warn "Troubleshoot plugin failed, falling back to manual collection"
    fi
fi

# Fall back to manual collection if plugin unavailable or failed
if [[ ! -f "$BUNDLE_DIR/bundle.tar.gz" ]]; then
    log "Collecting bundle manually (kubectl get + logs)..."
    MANUAL_DIR="$BUNDLE_DIR/manual-bundle"
    rm -rf "$MANUAL_DIR"
    CR="$MANUAL_DIR/cluster-resources"

    # Nodes
    mkdir -p "$CR"
    kubectl get nodes -o json > "$CR/nodes.json"

    # Namespaces
    kubectl get namespaces -o json > "$CR/namespaces.json"

    # Pods per namespace
    for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}'); do
        mkdir -p "$CR/pods/$ns"
        # Get individual pod JSONs
        for pod in $(kubectl get pods -n "$ns" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
            kubectl get pod "$pod" -n "$ns" -o json > "$CR/pods/$ns/$pod.json" 2>/dev/null || true
        done

        # Collect logs
        for pod in $(kubectl get pods -n "$ns" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
            for container in $(kubectl get pod "$pod" -n "$ns" -o jsonpath='{.spec.containers[*].name}' 2>/dev/null); do
                log_dir="$CR/pods/logs/$ns/$pod"
                mkdir -p "$log_dir"
                kubectl logs "$pod" -n "$ns" -c "$container" --tail=500 > "$log_dir/$container.log" 2>/dev/null || true
                kubectl logs "$pod" -n "$ns" -c "$container" --previous --tail=500 > "$log_dir/$container-previous.log" 2>/dev/null || true
                # Remove empty files
                find "$log_dir" -empty -delete 2>/dev/null || true
            done
        done
    done

    # Events
    mkdir -p "$CR/events"
    for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}'); do
        kubectl get events -n "$ns" -o json > "$CR/events/$ns.json" 2>/dev/null || true
    done

    # Deployments
    mkdir -p "$CR/deployments"
    for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}'); do
        kubectl get deployments -n "$ns" -o json > "$CR/deployments/$ns.json" 2>/dev/null || true
    done

    # ConfigMaps (non-system)
    mkdir -p "$CR/configmaps"
    for ns in default; do
        kubectl get configmaps -n "$ns" -o json > "$CR/configmaps/$ns.json" 2>/dev/null || true
    done

    # Services
    mkdir -p "$CR/services"
    for ns in default kube-system; do
        kubectl get services -n "$ns" -o json > "$CR/services/$ns.json" 2>/dev/null || true
    done

    # ReplicaSets
    mkdir -p "$CR/replicasets"
    for ns in default; do
        kubectl get replicasets -n "$ns" -o json > "$CR/replicasets/$ns.json" 2>/dev/null || true
    done

    # Secrets (just names, not data)
    mkdir -p "$CR/secrets"
    for ns in default; do
        kubectl get secrets -n "$ns" -o json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data.get('items', []):
    item.pop('data', None)
    item.pop('stringData', None)
json.dump(data, sys.stdout, indent=2)
" > "$CR/secrets/$ns.json" 2>/dev/null || true
    done

    # Version info
    kubectl version -o json > "$MANUAL_DIR/version.json" 2>/dev/null || true
    echo "collectedAt: $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$MANUAL_DIR/version.yaml"

    ok "Manual bundle collected at $MANUAL_DIR"

    BUNDLE_PATH="$MANUAL_DIR"
fi

# ── Step 4: Run the analyzer ─────────────────────────────────────────────────

echo ""
echo "============================================================"
log "Running TroubleShootAI analyzer..."
echo "============================================================"
echo ""

cd "$PROJECT_DIR"

if [[ -f "$BUNDLE_DIR/bundle.tar.gz" ]]; then
    BUNDLE_PATH="$BUNDLE_DIR/bundle.tar.gz"
else
    BUNDLE_PATH="$MANUAL_DIR"
fi

# Run triage (no AI key needed)
python3 -c "
import asyncio
import json
import sys
from pathlib import Path

async def main():
    from bundle_analyzer.bundle.indexer import BundleIndex
    from bundle_analyzer.triage.engine import TriageEngine

    bundle_path = Path('$BUNDLE_PATH')
    print(f'Analyzing bundle: {bundle_path}')
    print()

    # Build index
    index = await BundleIndex.build(bundle_path)
    print(f'Indexed: {len(index.namespaces)} namespaces')
    print(f'Data types: {sum(1 for v in index.has_data.values() if v)}')
    if index.metadata and index.metadata.collected_at:
        print(f'Collected at: {index.metadata.collected_at}')
    print()

    # Run triage
    engine = TriageEngine()
    triage = await engine.run(index)

    # Report results
    print('=' * 60)
    print('TRIAGE RESULTS')
    print('=' * 60)
    print()

    # Critical pods
    if triage.critical_pods:
        print(f'CRITICAL PODS ({len(triage.critical_pods)}):')
        for p in triage.critical_pods:
            print(f'  {p.namespace}/{p.pod_name}')
            print(f'    Issue: {p.issue_type}')
            print(f'    Restarts: {p.restart_count}')
            if p.exit_code is not None:
                print(f'    Exit code: {p.exit_code}')
            if p.message:
                print(f'    Message: {p.message[:100]}')
            if p.source_file:
                print(f'    Source: {p.source_file}')
            print()

    # Warning pods
    if triage.warning_pods:
        print(f'WARNING PODS ({len(triage.warning_pods)}):')
        for p in triage.warning_pods:
            print(f'  {p.namespace}/{p.pod_name}: {p.issue_type}')
            if p.message:
                print(f'    {p.message[:100]}')
        print()

    # Node issues
    if triage.node_issues:
        print(f'NODE ISSUES ({len(triage.node_issues)}):')
        for n in triage.node_issues:
            print(f'  {n.node_name}: {n.condition_type} = {n.condition_status}')
        print()

    # Deployment issues
    if triage.deployment_issues:
        print(f'DEPLOYMENT ISSUES ({len(triage.deployment_issues)}):')
        for d in triage.deployment_issues:
            print(f'  {d.namespace}/{d.name}: {d.issue}')
        print()

    # Config issues
    if triage.config_issues:
        print(f'CONFIG ISSUES ({len(triage.config_issues)}):')
        for c in triage.config_issues:
            print(f'  Missing {c.resource_type}/{c.resource_name} (ref by {c.referenced_by})')
        print()

    # Warning events
    if triage.warning_events:
        print(f'WARNING EVENTS ({len(triage.warning_events)}):')
        for e in triage.warning_events[:10]:
            print(f'  [{e.reason}] {e.involved_object_kind}/{e.involved_object_name}: {e.message[:80]}')
        print()

    # Scheduling issues
    if triage.scheduling_issues:
        print(f'SCHEDULING ISSUES ({len(triage.scheduling_issues)}):')
        for s in triage.scheduling_issues:
            print(f'  {s.namespace}/{s.pod_name}: {s.issue_type} — {s.message[:80]}')
        print()

    # DNS issues
    if triage.dns_issues:
        print(f'DNS ISSUES ({len(triage.dns_issues)}):')
        for d in triage.dns_issues:
            print(f'  {d.issue_type}: {d.description[:80]}')
        print()

    # Summary
    total = (len(triage.critical_pods) + len(triage.warning_pods) +
             len(triage.node_issues) + len(triage.deployment_issues) +
             len(triage.config_issues) + len(triage.scheduling_issues))
    print('=' * 60)
    print(f'TOTAL: {total} issues found')
    print(f'  Critical pods: {len(triage.critical_pods)}')
    print(f'  Warning pods:  {len(triage.warning_pods)}')
    print(f'  Node issues:   {len(triage.node_issues)}')
    print(f'  Deployments:   {len(triage.deployment_issues)}')
    print(f'  Config issues: {len(triage.config_issues)}')
    print(f'  Events:        {len(triage.warning_events)}')
    print(f'  Scheduling:    {len(triage.scheduling_issues)}')
    print('=' * 60)

    # Run full orchestrator (triage-only if no AI key)
    print()
    print('Running full analysis orchestrator...')
    from bundle_analyzer.ai.orchestrator import AnalysisOrchestrator
    from bundle_analyzer.ai.context_injector import ContextInjector

    orchestrator = AnalysisOrchestrator()
    result = await orchestrator.run(
        triage=triage,
        index=index,
        context_injector=ContextInjector(),
    )

    print(f'Analysis quality: {result.analysis_quality}')
    print(f'Duration: {result.analysis_duration_seconds:.1f}s')
    print(f'AI findings: {len(result.findings)}')
    print(f'Predictions: {len(result.predictions)}')
    print(f'Timeline events: {len(result.timeline)}')
    print(f'Hypotheses: {len(result.hypotheses)}')
    print(f'Summary: {result.summary}')

    # Save full result as JSON
    output_file = Path('$BUNDLE_DIR/analysis-result.json')
    output_file.write_text(json.dumps(
        result.model_dump(mode='json'), indent=2, default=str
    ))
    print(f'Full result saved to: {output_file}')

asyncio.run(main())
"

echo ""
echo "============================================================"
ok "Live test complete!"
echo "============================================================"
echo ""
echo "Bundle data:     $BUNDLE_PATH"
echo "Analysis result: $BUNDLE_DIR/analysis-result.json"
echo ""
echo "To clean up:"
echo "  ./scripts/live_test/run.sh --cleanup"
