# MLflow on Kubernetes — P3 draft (T17 / §5.2)

> **Owner of `deploy/` is P4.** These manifests are P3's draft for task **T17**
> ("MLflow on K8s") and must be integrated into P4's kustomize/Argo CD layout
> before being applied to a shared cluster.

Target: **1 replica**, namespace `ml`, PostgreSQL metadata (schema `mlflow`, D5),
artifacts on a **5 Gi `local-path` PVC**, exposed at `https://mlflow.fintech.local`.
This mirrors the Docker Compose service (`docker-compose.yml`), including the
`v3.17.2-full` image and `--serve-artifacts`.

## Files

| File | Purpose |
|---|---|
| `namespace.yaml` | Namespace `ml` |
| `pvc.yaml` | `mlflow-artifacts`, 5 Gi, `local-path`, `ReadWriteOnce` |
| `deployment.yaml` | MLflow server (`v3.17.2-full`), probes, resources, PVC mount |
| `service.yaml` | ClusterIP on port 5000 |
| `ingress.yaml` | `mlflow.fintech.local` (Traefik, TLS `fintech-local-tls`) |
| `kustomization.yaml` | Ties the above together |
| `secret.example.yaml` | Template only — **not** applied by kustomize |

## Prerequisites

1. P4's kind cluster is up (`kind get clusters`), with Traefik installed.
2. The `local-path` storage provisioner is available (`kubectl get storageclass`).
3. PostgreSQL is reachable from the `ml` namespace, with the `mlflow_user` role
   and `mlflow` schema created (`deploy/sql/00_schemas_users.sql`).

## Apply

Create the database Secret (never commit the real password):

```bash
kubectl -n ml create secret generic mlflow-db \
  --from-literal=backend-store-uri='postgresql://mlflow_user:<password>@postgres.data.svc.cluster.local:5432/fintech'
```

Provide the TLS secret in the `ml` namespace (copy P4's dev certificate):

```bash
kubectl get secret fintech-local-tls -n fintech -o yaml \
  | sed 's/namespace: fintech/namespace: ml/' \
  | kubectl apply -f -
```

Then deploy:

```bash
kubectl apply -k deploy/k8s/ml
kubectl -n ml rollout status deploy/mlflow --timeout=180s
```

## Verify

```bash
kubectl -n ml get pods,pvc,svc,ingress
kubectl -n ml port-forward svc/mlflow 5000:5000
curl -fsS http://localhost:5000/health

# Through Traefik (self-signed dev certificate)
curl -k --resolve mlflow.fintech.local:443:127.0.0.1 https://mlflow.fintech.local/health
```

## Notes

- **No authentication** (same as the Compose server): dev only. Do not expose it
  outside the cluster/VPN.
- The PVC is `ReadWriteOnce`; the Deployment uses `strategy: Recreate` so a
  rollout never runs two pods against the same volume.
- `local-path` binds the volume to one node; keep **1 replica**.
- First start runs MLflow's DB migrations on the existing `mlflow` schema.
  Patch upgrades are forward-only — back up the schema before a downgrade.
- Setting `MODEL_URI` / registry aliases (`champion`, `challenger`) is handled by
  the pipeline and `ml-service`; this Deployment only hosts the tracking server.
