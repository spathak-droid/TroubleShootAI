#!/usr/bin/env bash
# Create a kind cluster for live testing.
# Prerequisites: kind, kubectl, kubectl-support-bundle (or sbctl)
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-bundle-test}"

echo "==> Creating kind cluster: $CLUSTER_NAME"
kind create cluster --name "$CLUSTER_NAME" --wait 120s 2>/dev/null || {
  echo "Cluster $CLUSTER_NAME already exists or kind is not installed."
  echo "Install kind: https://kind.sigs.k8s.io/docs/user/quick-start/"
  exit 1
}

echo "==> Waiting for cluster to be ready..."
kubectl wait --for=condition=Ready nodes --all --timeout=120s
echo "==> Cluster $CLUSTER_NAME is ready."
