#!/usr/bin/env bash
# Remove everything this project created in the cluster and the registry.
# MANUAL ONLY: read it before running. Nothing here runs automatically.
# Run from the repository root:
#   bash scripts/cleanup.sh
set -euo pipefail

read -rp "Delete the gitops-demo application from the cluster? (type YES to continue) " CONFIRM
if [ "$CONFIRM" != "YES" ]; then
  echo "Aborted."
  exit 0
fi

# ArgoCD application (deleting the Application also deletes the managed
# resources because prune is enabled).
kubectl delete -f argocd/application.yaml --ignore-not-found

# Helm release, if it was installed directly instead of through ArgoCD.
helm uninstall gitops-demo -n gitops-demo --ignore-not-found 2>/dev/null || true

# Plain manifests, if they were applied directly.
kubectl delete -f k8s/ --ignore-not-found

# Namespace (only after the resources above are gone).
kubectl delete namespace gitops-demo --ignore-not-found

# Local Docker image (only if Docker is installed and the image exists).
if command -v docker >/dev/null 2>&1; then
  docker rmi docker.io/vinodg/gitops-demo:1.0.0 2>/dev/null || true
fi

echo "Cleanup done. Check the cluster billing/console to confirm nothing is left."
