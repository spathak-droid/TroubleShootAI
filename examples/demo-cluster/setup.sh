#!/usr/bin/env bash
# Demo cluster setup script for Bundle Analyzer
# Creates a kind cluster, deploys healthy workloads and intentional failures,
# then provides instructions to collect a support bundle.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="bundle-analyzer-demo"

echo "=== Bundle Analyzer Demo Cluster Setup ==="

# Step 1: Create kind cluster
echo "[1/4] Creating kind cluster '${CLUSTER_NAME}'..."
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "  Cluster already exists, skipping creation."
else
    kind create cluster --name "${CLUSTER_NAME}" --config "${SCRIPT_DIR}/kind-config.yaml"
fi

# Step 2: Deploy healthy workloads
echo "[2/4] Deploying healthy workloads..."
kubectl apply -f "${SCRIPT_DIR}/workloads/healthy-nginx.yaml"
kubectl apply -f "${SCRIPT_DIR}/workloads/healthy-redis.yaml"

# Step 3: Deploy intentional failures
echo "[3/4] Deploying intentional failure workloads..."
for f in "${SCRIPT_DIR}"/failures/break-*.yaml; do
    echo "  Applying $(basename "$f")..."
    kubectl apply -f "$f"
done

# Step 4: Wait for failures to manifest
echo "[4/4] Waiting 60 seconds for failures to manifest..."
sleep 60

echo ""
echo "=== Cluster ready! ==="
echo ""
echo "To collect a support bundle, run:"
echo "  kubectl support-bundle ${SCRIPT_DIR}/support-bundle-spec.yaml"
echo ""
echo "Or if using the support-bundle CLI directly:"
echo "  support-bundle ${SCRIPT_DIR}/support-bundle-spec.yaml"
echo ""
echo "To tear down the cluster:"
echo "  kind delete cluster --name ${CLUSTER_NAME}"
