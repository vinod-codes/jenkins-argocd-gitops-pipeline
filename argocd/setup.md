# ArgoCD setup notes

## Install ArgoCD on the cluster

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl wait --for=condition=available deployment/argocd-server -n argocd --timeout=300s
```

Get the initial admin password and open the UI:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo
kubectl port-forward svc/argocd-server -n argocd 8080:443
# Open https://localhost:8080 and sign in as admin with the password above.
# Change the password on first login.
```

## Register this application

```bash
kubectl apply -f argocd/application.yaml
```

ArgoCD then watches `helm/app-chart` in this repository and syncs it into
the `gitops-demo` namespace automatically (prune + self-heal enabled).

## Check sync status

```bash
kubectl get application gitops-demo -n argocd
argocd app get gitops-demo
argocd app sync gitops-demo   # manual sync, if automated sync is ever paused
```

## Using the plain manifests instead of Helm

If you prefer plain Kubernetes manifests, change `spec.source.path` in
`argocd/application.yaml` from `helm/app-chart` to `k8s` and re-apply.
Note that the Jenkins pipeline updates the image tag in
`helm/app-chart/values.yaml` only; with the `k8s` path you must update
`k8s/deployment.yaml` yourself (or adjust the Jenkinsfile).
