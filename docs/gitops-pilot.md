# Isolated GitOps pilot (Refs #40)

The published frontend from GHCR run 42874954627, attempt 2, source e17a493,
is pinned by digest. This pilot serves the static frontend and its health probe;
its API upstream intentionally points to an unused loopback port. It does not
test login, real API calls, migrations or ML.

The AppProject allows one repository, one namespace, Deployments and Services.
The Application has no automated sync or cascading deletion finalizer.
Pruning is disabled and resources tracked by another Application are refused.
Project restrictions are not Kubernetes RBAC restrictions on the controllers.
Install the controllers only on a separate disposable cluster for this pilot.
Nothing in this procedure should target kind-fintech.

## Before Merge

Run from the repository root in CMD:

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_gitops_pilot.py
kubectl kustomize deploy/gitops/pilot/bootstrap
kubectl kustomize deploy/gitops/pilot/workload
```

Review the two renders. Bootstrap must contain only the AppProject and the
Application; workload must contain only the namespaced frontend and its
ClusterIP Service. No secrets or credentials are required for rendering.

## After Merge: Controllers

The Application reads the workload from main, so wait for this PR to be merged.
Check that Docker has sufficient free memory, and that `kind get clusters` does
not already contain `fintech-gitops-lab`. Use a fresh cluster, without host port
mappings. The following commands assume Windows CMD and Linux AMD64 kind nodes.
Stop at the first error.

```cmd
kind create cluster --name fintech-gitops-lab --image kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5 --wait 120s
helm install argocd oci://ghcr.io/argoproj/argo-helm/argo-cd --version 10.17.1 --kube-context kind-fintech-gitops-lab --namespace argocd --create-namespace --set server.service.type=ClusterIP --set server.ingress.enabled=false --wait --timeout 10m
kubectl --context kind-fintech-gitops-lab apply -f https://github.com/bitnami/sealed-secrets/releases/download/v0.41.2/controller.yaml
kubectl --context kind-fintech-gitops-lab -n kube-system rollout status deployment/sealed-secrets-controller --timeout=180s
kubectl --context kind-fintech-gitops-lab create namespace fintech-gitops-pilot
```

These pins are [Argo CD Helm chart 10.17.1](https://github.com/argoproj/argo-helm/releases/tag/argo-cd-10.17.1)
and [Sealed Secrets v0.41.2](https://github.com/bitnami/sealed-secrets/releases/tag/v0.41.2).
Keep the Argo CD server private. Use the upstream
[local access procedure](https://argo-cd.readthedocs.io/en/stable/getting_started/#3-access-the-argo-cd-api-server)
with context kind-fintech-gitops-lab and loopback port-forwarding only. Never
share the initial admin password, sealing keys, or kubeconfig.

## After Merge: Manual Synchronization

```cmd
kubectl --context kind-fintech-gitops-lab apply -k deploy/gitops/pilot/bootstrap
kubectl --context kind-fintech-gitops-lab -n argocd get application fintech-pilot
```

In the Argo CD UI, review the diff. If Argo reports a repository access error,
stop and arrange read-only repository access; do not reuse the deploy bot's
write key. Synchronize only fintech-pilot with Prune and Force unchecked.
Expect Synced and Healthy. Then run:

```cmd
kubectl --context kind-fintech-gitops-lab -n fintech-gitops-pilot rollout status deployment/pilot-frontend --timeout=180s
kubectl --context kind-fintech-gitops-lab -n fintech-gitops-pilot port-forward --address 127.0.0.1 service/pilot-frontend 18087:8080
```

In another CMD window, `curl.exe -i http://127.0.0.1:18087/healthz` and
`curl.exe -I http://127.0.0.1:18087/` should both return HTTP 200. Stop the
port-forward with Ctrl+C. If pulls fail on the new cluster, stop and check
package access; a successful pull on the original kind cluster is not evidence
that a fresh cluster has the same access.

## Test Sealed Secrets Separately

Install the matching kubeseal client from the pinned release above. Use only a
fictitious value. This manual check does not grant the Argo project permission
to manage Secrets or SealedSecrets.

```cmd
kubectl --context kind-fintech-gitops-lab -n fintech-gitops-pilot create secret generic pilot-sealing-check --from-literal=probe=synthetic-demo-only --dry-run=client -o json | kubeseal --context kind-fintech-gitops-lab --scope strict --format json | kubectl --context kind-fintech-gitops-lab -n fintech-gitops-pilot create -f -
kubectl --context kind-fintech-gitops-lab -n fintech-gitops-pilot wait --for=condition=Synced sealedsecret/pilot-sealing-check --timeout=90s
kubectl --context kind-fintech-gitops-lab -n fintech-gitops-pilot get secret pilot-sealing-check
```

The generated Secret should exist; do not display its values. The synthetic
fixture and key are disposable. Do not use these keys or ciphertext for the
shared stack. Before real credentials, design and test key backup/restoration
and existing Secret ownership, using a separate restoration lab.

After recording the evidence, stop port-forwards and verify the cluster name
with `kind get clusters`. Delete **only** this disposable lab when finished:
`kind delete cluster --name fintech-gitops-lab`. This removes the lab's
synthetic Secret and sealing keys, not resources in kind-fintech.

The shared stack, app-of-apps, continuous deployment and rollback are outside
this pilot. Do not close #40 on the strength of this test alone.
