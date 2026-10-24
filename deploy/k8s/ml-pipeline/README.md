# Kubernetes Batch Job & CronJob for ML Pipeline (§5.1, §5.6)

This directory defines the Kubernetes manifests for running the modular ML training, evaluation, and quality gate pipeline as a batch `Job` and `CronJob` in the `ml` namespace.

## Architecture & Configuration

- **Execution Mode:** Runs `ml.src.pipeline.run` as an unprivileged batch process (`mlrunner:10002`).
- **Parent/Child Tracking:** Connects to the in-cluster MLflow Tracking Server (`http://mlflow.ml.svc.cluster.local:5000`) and logs:
  1. `1_prepare`: Data partitioning (70/15/15) and checksum logging.
  2. `2_train`: Model training and feature scaling.
  3. `3_evaluate`: PR-AUC, ROC-AUC, Brier score, and p95 inference latency.
  4. `4_quality_gates`: Enforces non-regression, conformal coverage, review rate, and latency gates.
- **Resource Sizing:**
  - CPU Requests / Limits: `500m` / `2000m`
  - Memory Requests / Limits: `1Gi` / `2Gi`
- **Fault Tolerance & Cleanup:**
  - `backoffLimit: 2` (infrastructure retries).
  - `activeDeadlineSeconds: 3600` (1-hour execution timeout).
  - `ttlSecondsAfterFinished: 3600` (automatic garbage collection of completed pods).
- **Periodic Retraining:**
  - `cronjob.yaml` defines a weekly retraining template (`0 2 * * 0`, Sundays at 02:00 UTC).
  - Suspended by default (`suspend: true`) until scheduled retraining is formally enabled.

---

## Local Build & Verification (kind)

### 1. Build & Load Container Image
```bash
docker build -t fintech-ml-pipeline:dev ml
kind load docker-image fintech-ml-pipeline:dev --name fintech
```

### 2. Apply Manifests
```bash
kubectl apply -k deploy/k8s/ml-pipeline
```

### 3. Monitor Job Execution & Logs
```bash
# Watch job status
kubectl -n ml get jobs -w

# Stream pipeline execution logs
kubectl -n ml logs job/ml-pipeline -f
```

### 4. Verify Tracking in MLflow
```bash
# Verify parent and nested child runs recorded in MLflow
kubectl -n ml exec deploy/mlflow -- python -c "
import mlflow
mlflow.set_tracking_uri('http://localhost:5000')
runs = mlflow.search_runs(experiment_names=['fraud-detector-pipeline'])
print(f'Total runs logged: {len(runs)}')
print(runs[['run_id', 'tags.mlflow.runName', 'metrics.pr_auc', 'metrics.gate_non_regression']].dropna(how='all'))
"
```

### 5. Check CronJob Status
```bash
kubectl -n ml get cronjob ml-pipeline-cron
```

---

## Running on Real Dataset (Volume Mount)

To run the pipeline against the real Sparkov CSV dataset:
1. Ensure the dataset is present on the worker node at `/data/sparkov/fraudTrain.csv`.
2. Add a `hostPath` volume mount in `job.yaml` targeting `/data/sparkov`.
3. Update `configmap.yaml` with `--data-path=/data/sparkov/fraudTrain.csv` and set `PIPELINE_TEST_MODE: "false"`.
