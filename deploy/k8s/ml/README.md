# MLflow on Kubernetes — P3 draft (T17 / §5.2)

> **Owner of `deploy/` is P4.** These manifests are P3's draft for task **T17**
> ("MLflow on K8s") and must be integrated into P4's kustomize/Argo CD layout
> before being applied to a shared cluster.

Target: **1 replica**, namespace `ml`, PostgreSQL metadata (schema `mlflow`, D5),
artifacts on a **5 Gi default-StorageClass PVC** (kind: `standard`), exposed at `https://mlflow.fintech.local`.
This mirrors the Docker Compose service (`docker-compose.yml`), including the
`v3.17.2-full` image and `--serve-artifacts`.

## Files

| File | Purpose |
|---|---|
| `namespace.yaml` | Namespace `ml` |
| `pvc.yaml` | `mlflow-artifacts`, 5 Gi, default StorageClass, `ReadWriteOnce` |
| `deployment.yaml` | MLflow server (`v3.17.2-full`), probes, 3 Gi memory limit, PVC mount |
| `service.yaml` | ClusterIP on port 5000 |
| `ingress.yaml` | `mlflow.fintech.local` (Traefik, TLS `fintech-local-tls`) |
| `kustomization.yaml` | Ties the above together |
| `secret.example.yaml` | Template only — **not** applied by kustomize |

## Prerequisites

1. P4's kind cluster is up (`kind get clusters`), with Traefik installed.
2. A default StorageClass exists (`kubectl get storageclass`; kind provides `standard`).
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
- The local-path provisioner binds the volume to one node; keep **1 replica**.
- First start runs MLflow's DB migrations on the existing `mlflow` schema.
  Patch upgrades are forward-only — back up the schema before a downgrade.
- Setting `MODEL_URI` / registry aliases (`champion`, `challenger`) is handled by
  the pipeline and `ml-service`; this Deployment only hosts the tracking server.

## Validated on kind (2026-10-24)

Tested on kind **v1.37.0** (3 nodes) with Traefik **41.7.1** and a dev
PostgreSQL 17 in the `data` namespace:

- `/health`, experiment search/create, and artifact upload/download through
  `https://mlflow.fintech.local` all succeed.
- The `-full` image runs two Python processes (uvicorn parent + worker) and uses
  **~1.9 GiB** at idle, so the Deployment limits memory to **3 Gi** (1 Gi and
  2 Gi were OOM-killed).
- MLflow >= 3.17 enables a security middleware that only accepts localhost by
  default: it rejects non-localhost `Host` headers and cross-origin writes. The
  Deployment sets `MLFLOW_SERVER_ALLOWED_HOSTS` and
  `MLFLOW_SERVER_CORS_ALLOWED_ORIGINS` for the Ingress host and the in-cluster
  Service DNS names.
- kind names its default StorageClass **`standard`** (not `local-path`), so the
  PVC omits `storageClassName` and binds to the cluster default.
- The TLS secret used for this validation was a temporary self-signed
  certificate; replace it with P4's mkcert certificate for a browser-trusted UI.
