# Plateforme FinTech MLOps haute disponibilité

Real-time card-fraud risk platform: every transaction is scored by a calibrated ML model with conformal prediction and is **approved**, **blocked**, or sent to **human review** when the model is uncertain. Built with Spring Boot microservices, FastAPI, MLflow, React, Kubernetes (kind), Argo CD, Prometheus/Grafana.

> Full report — sections are filled by each member before J8 (03/01/2027). Architecture reference: [`docs/specs/Architecture_Plateforme_FinTech_MLOps_1.pdf`](docs/specs/Architecture_Plateforme_FinTech_MLOps_1.pdf).

## Table of contents
1. [Architecture microservices](#1-architecture-microservices) — P1
2. [Machine learning, statistical validation, uncertainty](#2-machine-learning) — P2
3. [MLOps and model serving](#3-mlops-and-model-serving) — P3
4. [Docker, Kubernetes, CI/CD, experiments](#4-devops) — P4
5. [Frontend and observability](#5-frontend-and-observability) — P5
6. [How to run](#6-how-to-run)
7. [Limits and future work](#7-limits-and-future-work)

## 1. Architecture microservices
_TODO (P1)_

## 2. Machine learning
_TODO (P2)_

## 3. MLOps and model serving

### 3.1 MLflow topology

One MLflow server in the `ml` namespace is the source of truth for experiments, artifacts and the model registry. The pipeline, the final-evaluation CLI and `ml-service` are all clients of `http://mlflow.ml.svc.cluster.local:5000`.

| Component | Setting |
|---|---|
| Server | `ghcr.io/mlflow/mlflow:v3.17.2-full`, **1 replica**, `strategy: Recreate` |
| Backend store | PostgreSQL, URI read from Secret `mlflow-db` (never in the manifest) |
| Artifact store | PVC `mlflow-artifacts`, **5 Gi**, served by MLflow itself (`--serve-artifacts`) |
| In-cluster endpoint | `http://mlflow.ml.svc.cluster.local:5000` |
| Browser endpoint | `https://mlflow.fintech.local` — its own Traefik ingress and TLS secret, separate from the api-gateway |
| Manifests | [`deploy/k8s/ml/`](deploy/k8s/ml/) |

```
pipeline / final-evaluation CLI ─┐
                                 ├─→ mlflow.ml.svc:5000 ─→ PostgreSQL   (runs, metrics, registry metadata)
ml-service ──────────────────────┘                      └─→ PVC          (model files, viz/*.json)
```

Four constraints shaped this deployment:

- **One replica, `Recreate`.** The artifacts PVC is `ReadWriteOnce`, so a rolling update would try to mount it in two pods at once. The pod is briefly unavailable during an update; runs and registry stay reachable because the backend is PostgreSQL.
- **PostgreSQL rather than the file backend.** Runs, metrics, tags and model versions survive a pod restart, and logging a version is transactional.
- **`MLFLOW_SERVER_ALLOWED_HOSTS` / CORS.** MLflow 3.17 added a DNS-rebinding middleware that only accepts `localhost` by default. The ingress host and the in-cluster service names are allow-listed explicitly; without them the pipeline and `ml-service` receive a `403`.
- **Default StorageClass, never `local-path`.** On kind the class is named `standard`; hard-coding the provisioner name would silently fail on another cluster.

### 3.2 The training pipeline

`python -m ml.src.pipeline.run --mode full` (locally, or as the `ml-pipeline` Kubernetes Job) runs the pipeline as nested runs under one parent run, so every metric keeps its stage of origin.

| Run | Stage | Output |
|---|---|---|
| `1_prepare` | Chronological split of the development block, preprocessing fitted on train only | feature matrix, split boundaries |
| `2_train` | XGBoost with the frozen hyper-parameters (`configs/best_params.json`), β-correction undersampling | classifier, `beta` |
| `3_calibrate` | Isotonic/sigmoid fit on 50 %, selection on the other 50 % (D46) | calibrator |
| `4_conformal` | Mondrian quantiles: fit 50 %, α choice 25 %, evaluation 25 % (D46) | `threshold_legit`, `threshold_fraud` |
| `5_evaluate` | PR-AUC, ROC-AUC, Brier, per-class coverage, review/automation rate, p95 latency | metrics |
| `5b_logreg_baseline` | Logistic-regression non-regression baseline for the first run | reference PR-AUC |
| `6_quality_gates` | The six gates below, logged as `1.0`/`0.0` | gate report |
| `7_visualize` | Projections of the evaluation sample for the frontend; PCA fallback when `umap-learn` is absent | `viz/*.json` |
| `8_package` | Self-contained pyfunc with explicit signature and nested `customer` example | model artifact |
| `9_register` | Provisional model version with the `challenger` alias | registry version |

`--alpha` forces α; otherwise the smallest α in the approved grid whose review rate stays under capacity is selected (D44).

### 3.3 Quality gates

Every gate is logged as a metric, and promotion refuses unless **all** of them are literally `true` — a missing gate is a refusal, never a default.

| Gate | Rule | Constant |
|---|---|---|
| `gate_non_regression` | PR-AUC ≥ incumbent − **0.01** (D45); on the first run, ≥ logistic baseline. No reference → `UNVERIFIED`, which cannot pass | `champion_pr_auc` / `baseline_pr_auc` |
| `gate_coverage_legit` | coverage of class 0 ≥ (1 − α) − **0.02** | `COVERAGE_SLACK = 0.02` |
| `gate_coverage_fraud` | coverage of class 1 ≥ (1 − α) − **0.02** | `COVERAGE_SLACK = 0.02` |
| `gate_coverage` | both classes | — |
| `gate_review_rate` | human review ≤ **2 %** of transactions | `REVIEW_RATE_GATE = 0.02` |
| `gate_latency` | inference p95 < **50 ms** over 1 000 calls | `LATENCY_GATE_SECONDS = 0.050` |

Conformal coverage is measured per class, not on the pooled set: an aggregate that hides a failing class is exactly the failure mode the gate exists to catch.

### 3.4 Packaging and serving contract

The registered artifact is a `pyfunc` wrapper around `CalibratedPriorClassifier` + `SparkovPreprocessingPipeline`, so the serving image needs no repository code. Its signature is inferred from a nested `customer` example, and every request must carry the full schema (`transaction_id`, `trans_datetime`, `amount`, `category`, `merch_lat`, `merch_long`, `customer.{dob,gender,city_pop,lat,long,state}`).

- **α and thresholds come from the registry metadata**, not from code: α `0.02` (D44), `threshold_legit` `0.004935831171766689`, `threshold_fraud` `0.9905519026812524` for `fraud-detector/1`.
- **`prediction_set` is returned verbatim.** An empty set is a legitimate conformal outcome and is preserved end-to-end — it is never rewritten to `[0]`.
- **`ml-service` never decides.** `risk-service` maps the set: `[0]` → `APPROUVER`, `[1]` → `BLOQUER`, `[0,1]` or `[]` → `REVUE`.

### 3.5 Metrics catalog

`/metrics` is scraped from inside the cluster (`monitoring/prometheus.yml`) and is never routed by the gateway.

| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `http_requests_total` | counter | `method`, `endpoint`, `status` | traffic and error rate |
| `http_request_duration_seconds` | histogram | `method`, `endpoint` | end-to-end HTTP latency; buckets 5 ms … 5 s |
| `ml_inference_duration_seconds` | histogram | `model_version` | model-only latency; buckets 1 ms … 500 ms — the number the 50 ms gate refers to |
| `ml_predictions_total` | counter | `model_version`, `prediction_set` | decision distribution, including `[]` |
| `ml_fraud_probability` | histogram | — | calibrated score distribution (drift) |
| `ml_uncertainty` | histogram | — | uncertainty distribution |
| `ml_input_validation_errors_total` | counter | — | `422` rejections |
| `ml_model_info` | gauge | `name`, `version` | which version is actually served |
| `ml_model_loaded_timestamp_seconds` | gauge | — | last successful load |

`ml_model_info` is how a deployment is verified after a promotion: the alias can point at a new version while a pod still serves the cached old one.

Three read-only endpoints expose the model to the platform: `/api/v1/ml/model` (name, version, α, mode), `/api/v1/ml/performance` (the served run's offline metrics, with `status: ready`, `unavailable` or `demo`) and `/api/v1/ml/viz/{method}` (the version's `viz/*.json`).

### 3.6 Promotion and rollback

Registration is challenger-first: a new version is always `PROVISIONAL` and receives the `challenger` alias. The `champion` alias only moves on an explicit call:

```bash
python -m ml.scripts.register_champion --artifact … --metadata … \
  --promote --gates gate-report.json
```

`--promote` refuses unless every `gate_*` entry in the report is `true`. While no champion exists, the live ConfigMap pins `models:/fraud-detector/<version>`; the promotion PR switches it to `models:/fraud-detector@champion`, after which promotion and rollback are registry-only operations — **rollback is the same mechanism in reverse**, moving the alias back to the previous version. Both are rehearsed on a throwaway model name, never on `fraud-detector`. The full procedure, failure modes and evidence checklist are in [`docs/model-promotion-runbook.md`](docs/model-promotion-runbook.md).

### 3.7 Governance: why version 1 is still `PROVISIONAL`

Passing the gates is necessary, not sufficient. `fraud-detector/1` stays provisional because two conditions are still open: the single approved final measurement (D48) and the P4/P1 sign-off.

| Decision | Effect |
|---|---|
| **D44** | α grid `{0.01, 0.02, 0.03, 0.05, 0.10}`, review capacity ≤ 2 %, smallest eligible α. Forced to `0.02` for the frozen candidate |
| **D45** | Non-negligible PR-AUC effect set to **0.01**; selection stays provisional, no automatic promotion |
| **D46** | Internal chronological splits: 50/50 calibrator fit/selection, 50/25/25 conformal fit/α choice/evaluation |
| **D48** | Authorises **one** second post-hoc, non-independent measurement of the frozen D44 candidate (bootstrap CIs and fairness audit missing on 10 November). One `completed` entry consumes it; no rerun under another reason or revision label |

The final test set is read by exactly one program (`evaluate_final_candidate.py`), the prediction journal is reserved before the source is opened, and the measurement never promotes anything. Details and the approved protocol fingerprint are in [`docs/decisions.md`](docs/decisions.md) and [`ml/README.md`](ml/README.md).

### 3.8 Verified state

- Model registry: `fraud-detector` version `1`, run `f20ac523af6745c1bc1a3bfbbc81d07c`, `status=PROVISIONAL`, alias `challenger`, 15 `viz/` artifacts, `source_model_sha256=aa1565ca…`, no `champion` alias.
- Serving: `ml-service` 2/2 pods, live ConfigMap `MODEL_MODE=real` and `MODEL_URI=models:/fraud-detector/1`; `/api/v1/ml/model` reports `version=1`, `algorithm=xgboost-calibrated`, `alpha=0.02`, `mode=real`.
- Tests: `ml/tests` 486, `ml-service/tests` 36, `ruff check` clean.

## 4. DevOps
_TODO (P4)_

## 5. Frontend and observability
_TODO (P5)_

## 6. How to run
_TODO_ — prerequisites: JDK 21, Docker, kind, kubectl.

## 7. Limits and future work
_TODO_
