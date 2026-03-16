#!/usr/bin/env bash
# Demo cluster 2 — different failure scenarios
# Creates a new kind cluster with production-like failures:
#   1. Service → wrong port (silent networking failure)
#   2. Missing Secret reference (CreateContainerConfigError)
#   3. Readiness probe deadlock (Running but never Ready)
#   4. ResourceQuota exceeded (pods fail to create)
#   5. PVC with non-existent StorageClass (Pending volume)
#   6. Init container stuck waiting for missing dependency
#   7. Service selector label mismatch (0 endpoints)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="bundle-analyzer-demo-2"

echo "=== Bundle Analyzer Demo Cluster 2 ==="

# Step 1: Create kind cluster
echo "[1/4] Creating kind cluster '${CLUSTER_NAME}'..."
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "  Cluster already exists, skipping creation."
else
    kind create cluster --name "${CLUSTER_NAME}" --config "${SCRIPT_DIR}/kind-config.yaml"
fi

# Step 2: Deploy healthy workloads
echo "[2/4] Deploying healthy workloads..."
kubectl apply -f "${SCRIPT_DIR}/workloads/healthy-api.yaml"

# Step 3: Deploy failure scenarios
echo "[3/4] Deploying failure scenarios..."
for f in "${SCRIPT_DIR}"/failures/fail-*.yaml; do
    echo "  Applying $(basename "$f")..."
    kubectl apply -f "$f"
done

# Step 4: Wait for failures to manifest
echo "[4/4] Waiting 90 seconds for failures to manifest..."
sleep 90

echo ""
echo "=== Cluster ready! ==="
echo ""
echo "Quick status:"
kubectl get pods -n production -o wide
echo ""
echo "To collect a support bundle:"
echo "  kubectl support-bundle ${SCRIPT_DIR}/support-bundle-spec.yaml"
echo ""
echo "To tear down:"
echo "  kind delete cluster --name ${CLUSTER_NAME}"
