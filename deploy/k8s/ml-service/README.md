# Kubernetes Deployment for `ml-service` (FastAPI)

This directory defines the Kubernetes manifests for deploying the FastAPI `ml-service` to the `ml` namespace.

## Architecture & Configuration

- **Replicas & Rollout:** 2 initial replicas managed with `RollingUpdate` strategy (`maxSurge: 1`, `maxUnavailable: 0`).
- **Autoscaling (HPA):** `autoscaling/v2` targeting 70% CPU utilization, scaling between 2 and 5 pods.
- **High Availability & Resiliency:**
  - `PodDisruptionBudget` (`minAvailable: 1`).
  - `topologySpreadConstraints` across `kubernetes.io/hostname` to evenly distribute pods between worker nodes.
- **Resource Sizing (Aligned with P4 Platform Spec §6.3):**
  - CPU Requests / Limits: `250m` / `1000m`
  - Memory Requests / Limits: `384Mi` / `768Mi`
- **Model Cache Persistence:** Mounts a `hostPath` volume at `/tmp/model-cache` (§6.10). An unprivileged `initContainer` sets ownership to `UID 10001:10001` with `775` permissions so the non-root application container can persist downloaded models across pod restarts.
- **Probes & Graceful Shutdown:**
  - Startup & Liveness: `GET /health/live` (port 8000).
  - Readiness: `GET /health/ready` (port 8000).
  - `preStop` hook: `sleep 5` ensuring in-flight requests complete before termination.

---

## Local Deployment & Verification (kind)

### 1. Build & Load Container Image into kind
```bash
docker build -t fintech-ml-service:dev ml-service
kind load docker-image fintech-ml-service:dev --name fintech
```

### 2. Apply Manifests
```bash
kubectl apply -k deploy/k8s/ml-service
```

### 3. Verify Rollout & Health
```bash
# Wait for rollout
kubectl -n ml rollout status deploy/ml-service

# Check pods are distributed across workers
kubectl -n ml get pods -l app=ml-service -o wide

# Check HPA status
kubectl -n ml get hpa ml-service-hpa

# Check PDB status
kubectl -n ml get pdb ml-service-pdb
```

### 4. Test Endpoints & Cache Permissions
```bash
# Port-forward to local port 8000
kubectl -n ml port-forward svc/ml-service 8000:8000

# Probes and metrics
curl -s http://localhost:8000/health/live
curl -s http://localhost:8000/health/ready
curl -s http://localhost:8000/metrics | head -n 20

# Test cache directory write access inside pod
POD_NAME=$(kubectl -n ml get pods -l app=ml-service -o jsonpath='{.items[0].metadata.name}')
kubectl -n ml exec -it "$POD_NAME" -c ml-service -- touch /tmp/model-cache/.write-test
kubectl -n ml exec -it "$POD_NAME" -c ml-service -- ls -la /tmp/model-cache/
```

---

## Integration Notes (P4 Handover & Observability)

- **`servicemonitor.yaml` Caveat:**  
  `servicemonitor.yaml` targets Prometheus Operator (`monitoring.coreos.com/v1`). It is intentionally excluded from `kustomization.yaml` until P4 deploys the Prometheus CRDs (`kube-prometheus-stack`). Once available, add `- servicemonitor.yaml` to `resources:` in `kustomization.yaml`.
- **GitOps & Argo CD:**  
  This folder is structured for direct inclusion into Argo CD application definitions under `deploy/overlays/` or cluster app sets.
