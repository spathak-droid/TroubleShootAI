#!/usr/bin/env bash
# Scenario: Create PVC with nonexistent StorageClass.
# Expected: StorageIssue detected.
set -euo pipefail

echo "==> Creating PVC with nonexistent StorageClass..."
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: bad-pvc-test
  namespace: default
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: nonexistent-storage-class
  resources:
    requests:
      storage: 1Gi
---
apiVersion: v1
kind: Pod
metadata:
  name: pvc-pending-test
  namespace: default
  labels:
    test-scenario: pvc-pending
spec:
  containers:
  - name: main
    image: nginx:latest
    volumeMounts:
    - name: data
      mountPath: /data
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: bad-pvc-test
EOF

echo "==> Waiting 15s for Pending/FailedMount..."
sleep 15
echo "==> Scenario deployed. Collect bundle now."
