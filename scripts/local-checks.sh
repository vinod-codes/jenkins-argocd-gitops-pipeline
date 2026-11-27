#!/usr/bin/env bash
# Local checks that can run without a Jenkins server, a registry, or a
# Kubernetes cluster. Run from the repository root:
#   bash scripts/local-checks.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAVEN="${MAVEN:-$HOME/workspace/.tools/apache-maven-3.9.9/bin/mvn}"
HELM="${HELM:-$HOME/workspace/.tools/linux-amd64/helm}"

echo "== 1. Maven unit tests (offline: the local repo was populated by scripts/populate-maven-repo.py) =="
"$MAVEN" -o -s "$HOME/.m2/settings.xml" -Dmaven.repo.local="$HOME/workspace/.m2" \
  -f "$ROOT/app/pom.xml" clean test

echo "== 2. Helm chart render =="
"$HELM" template gitops-demo "$ROOT/helm/app-chart" > /tmp/gitops-demo-rendered.yaml
python3 -c "import yaml,sys; docs=list(yaml.safe_load_all(open('/tmp/gitops-demo-rendered.yaml'))); print(f'rendered {len(docs)} manifests: ' + ', '.join(d.get(\"kind\",\"?\") for d in docs if d))"

echo "== 3. Plain manifests parse check =="
python3 -c "
import yaml, glob
for f in sorted(glob.glob('$ROOT/k8s/*.yaml')):
    docs = list(yaml.safe_load_all(open(f)))
    print(f, '->', [d.get('kind') for d in docs if d])
"

echo "== 4. ArgoCD manifest parse check =="
python3 -c "import yaml; d=yaml.safe_load(open('$ROOT/argocd/application.yaml')); print('Application:', d['metadata']['name'], '| path:', d['spec']['source']['path'])"

echo "All local checks passed."
