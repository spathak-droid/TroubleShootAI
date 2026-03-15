#!/usr/bin/env bash
# Scenario: Deploy a pod with a nonexistent image tag.
# Expected: ImagePullBackOff detected by PodScanner.
set -euo pipefail

NAMESPACE="${NAMESPACE:-default}"

echo "==> Deploying pod with bad image..."
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: bad-image-test
  namespace: default
  labels:
    test-scenario: bad-image
spec:
  containers:
  - name: main
    image: nginx:this-tag-does-not-exist-99999
    resources:
      limits:
        memory: "64Mi"
        cpu: "100m"
EOF

echo "==> Waiting 30s for ImagePullBackOff..."
sleep 30
echo "==> Scenario deployed. Collect bundle now."
