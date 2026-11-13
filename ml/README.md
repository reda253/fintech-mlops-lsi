# ml/ — owner P2 (data science) + P3 (pipeline)

Preprocessing, benchmark, statistical validation (`ml/stats/validate.py`), pipeline. Sparkov CSVs go in `ml/data/` (git-ignored).

## MLflow (local dev)

Tracking server = the `mlflow` service in `docker-compose.yml`. Backend store is PostgreSQL (`mlflow` schema, D5); artifacts are served by MLflow itself to the `mlflow_artifacts` volume (no MinIO, §5.2).

Start it:
```bash
# one-time: create the schemas/users (see deploy/sql/00_schemas_users.sql)
docker compose up -d postgres
docker compose exec -T postgres psql -U fintech -d fintech -v ON_ERROR_STOP=1 \
  -v auth_pwd=auth -v customer_pwd=customer -v transaction_pwd=transaction \
  -v risk_pwd=risk -v notification_pwd=notification -v audit_pwd=audit \
  -v audit_migrator_pwd=audit_migrator -v mlflow_pwd=mlflow \
  < deploy/sql/00_schemas_users.sql

docker compose up -d mlflow
```

- UI: http://localhost:5000
- Tracking URI (from another container): `http://mlflow:5000`
- Tracking URI (from the host): `http://localhost:5000`

Log a run (template for pipeline steps):
```bash
python -m venv ml/.venv && . ml/.venv/bin/activate
pip install -r ml/requirements-dev.txt
python ml/tracking_smoke.py --tracking-uri http://localhost:5000 --experiment smoke
```

The reusable helper is `ml/tracking_smoke.py::log_smoke_run(tracking_uri, experiment)`.

## Training pipeline (T21)

`ml/src/pipeline/run.py` runs the full lifecycle as nested MLflow runs:

1. `prepare` — chronological 70/15/15 split of `fraudTrain.csv`, independent `fraudTest.csv`.
2. `train` — preprocessing fitted on natural data, XGBoost fitted on a 1:10 undersampled block (`beta` logged).
3. `calibrate` — isotonic vs sigmoid fitted on 50 % and selected on the other 50 % (D46).
4. `conformal` — Mondrian class-conditional quantiles on 50 %, alpha chosen on 25 % by review capacity, last 25 % scored after freezing alpha (D46).
5. `evaluate` — PR-AUC, ROC-AUC, Brier, per-class coverage, review/automation rates, auto-error rate, p95 latency on 1 000 calls.
6. `quality_gates` — PR-AUC non-regression (champion − 0.01, or the logistic-regression baseline on the first run), per-class coverage `>= 1 - alpha - 0.02`, review rate `<= 2 %`, p95 `< 50 ms`.
7. `visualize` — PCA / t-SNE / UMAP projections for the 5 dashboard facets.
8. `package` — self-contained `FraudDetectorModel` pyfunc (calibration + conformal sets).
9. `register` — `fraud-detector` model version, tags and `challenger` alias; `champion` is moved only by an explicit promotion.

Run the synthetic smoke pipeline (no Sparkov CSVs needed); omit `--alpha` to let D46 select it:

```bash
PYTHONPATH=. python -m ml.src.pipeline.run \
  --tracking-uri http://localhost:5000 \
  --test-mode --model-name fraud-detector-smoke
```

Run on the real data (place `fraudTrain.csv` in `ml/data/raw/`). Training never reads `fraudTest.csv`:

```bash
PYTHONPATH=. python -m ml.src.pipeline.run \
  --mode full --tracking-uri http://localhost:5000 \
  --data-path ml/data/raw/fraudTrain.csv \
  --model-name fraud-detector --no-register
```

> A real training run cannot register without the verified D48 evaluation. Use `--no-register` for training only, or `--mode evaluate` below once the D48 artifact exists.

## Final evaluation (D48, option B)

`ml/scripts/evaluate_final_candidate.py` is the only reader of `fraudTest.csv`. It writes a new directory outside the repository (`final_metrics.json`, `predictions.csv`, `artifact_manifest.json`, etc.). The pipeline then consumes it and binds it to the frozen candidate:

```bash
PYTHONPATH=. python -m ml.src.pipeline.run \
  --mode evaluate \
  --evaluation-dir /outside/repo/d48-results \
  --candidate-model /outside/repo/d44/candidate.joblib \
  --model-uri models:/fraud-detector/1 \
  --baseline-pr-auc <reference-pr-auc> \
  --tracking-uri http://localhost:5000
```

`--candidate-model` is the frozen D44 joblib. The pipeline hashes it, requires the approved `aa1565ca…` digest, loads the MLflow-served model and requires identical calibrated probabilities on a fixed probe — a different model with the same alpha/thresholds is refused. `step_evaluate` then verifies the complete manifest, every SHA-256 (including `predictions.csv`), the D48 decision, the approved `source_sha256` (`7e50d0ce…`), the previous-measurement history, metric bounds/count consistency, and the alpha/thresholds of the served model. Any mismatch is refused before any evaluation metric is logged; the pipeline never reads the source. The evaluation mode never trains, registers or promotes; it only logs the verified metrics and gates.

## Model registry and P2 hand-off

The packaged artifact ships only the runtime modules (`ml/src/model/{fraud_detector,calibration}.py`, `ml/src/preprocessing/pipeline.py`) plus compatibility aliases, so the serving image does not need this repository.

The pyfunc signature is inferred from a **nested `customer`** input example. Serving requests must therefore include every schema-required field: `transaction_id`, `trans_datetime`, `amount`, `category`, `merch_lat`, `merch_long`, and `customer.{dob,gender,city_pop,lat,long,state}`. `dob` is serialized as an ISO date string.

`prediction_set` semantics:

| Set | Decision |
|---|---|
| `[0]` | `APPROUVER` |
| `[1]` | `BLOQUER` |
| `[0, 1]` or `[]` | `REVUE` |

An empty set is a valid conformal outcome and is preserved end-to-end (never rewritten to `[0]`).

When P2 delivers the candidate artifact (preprocessor, classifier, calibrator, beta, conformal thresholds/scores, metadata), register it without retraining:

```bash
PYTHONPATH=. python -m ml.scripts.register_champion \
  --artifact /path/to/candidate_model.joblib \
  --metadata /path/to/metadata.json \
  --tracking-uri http://localhost:5000 \
  --model-name fraud-detector --alpha 0.02
```

The script accepts a dict payload, P2's nested `FraudDetectorModel` (calibrator and beta inside `CalibratedPriorClassifier`) or a single estimator with `predict_proba`. It resolves thresholds or raw conformal scores, carries `run_id`/`git_commit`/`data_sha256`/`protocol_sha256` provenance tags, and registers a **provisional** version with the `challenger` alias. Promotion is explicit: `--promote --gates <report.json>` refuses unless every `gate_*` entry in the report is `true`.

Replay the handoff cases against the local wrapper, the registered pyfunc and the HTTP service:

```bash
PYTHONPATH=. python -m ml.scripts.verify_handoff \
  --zip /path/to/d44_handoff.zip \
  --tracking-uri http://localhost:5000 \
  --model-uri models:/fraud-detector/1 \
  --service-url http://localhost:8000
```

The script verifies the ZIP and joblib SHA-256, checks raw/rounded probabilities, sets and decisions, and covers `[0, 1]` with a fake-threshold model (the frozen D44 thresholds cannot produce it).

Models imported from the hand-off have no `viz/` artifacts, so `/api/v1/ml/viz/{method}` falls back to demo points. Attach the 15 projections to the version's existing run:

```bash
PYTHONPATH=. python -m ml.scripts.attach_viz \
  --model-name fraud-detector --version 1 \
  --tracking-uri http://localhost:5000 --samples 500
```

The script scores synthetic rows by default. With `--data-path` it expects the **full** `fraudTrain.csv` (any other filename is refused as unverifiable) and loads only its development zone (earliest 70 % by transaction date): the date pass identifies the development rows, then a second read parses only those lines, so calibration labels and features are never loaded. A pre-filtered extract cannot prove its provenance, so `--development-extract` is refused. The script also refuses `fraudTest.csv` before any read: the official final test stays reserved for the D48 measurement. It logs `viz/<method>_<view>.json` on the version's run, never registers a new version and never moves an alias.

## Serving against the registry

`ml-service` loads `models:/<name>/<version>` (or an alias) with `mlflow.pyfunc.load_model`; it never loads a raw `.joblib`. Set:

```yaml
MODEL_MODE: "real"
MODEL_URI: "models:/fraud-detector@champion"
MLFLOW_TRACKING_URI: "http://mlflow.ml.svc.cluster.local:5000"
```

`alpha` is read from the model metadata, and `/api/v1/ml/viz/{method}` downloads the version's `viz/*.json` artifact on a cache miss. `/api/v1/ml/performance` reads the served version's MLflow run: it returns `status: ready` with measured metrics, `status: unavailable` when the run has none, and `status: demo` in mock mode.
