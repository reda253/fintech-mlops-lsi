# Model promotion and rollback runbook

Owner: P3 (`@omar-aouichi`). Applies to `fraud-detector` in the `ml` namespace.

Promotion moves the `champion` alias to a version that has passed every quality
gate. Rollback moves it back. Both are registry operations; neither retrains,
re-registers or edits the model artifact. This document is also the rehearsal
script: it is exercised on a throwaway model name before it is used on
`fraud-detector`.

## Invariants

1. **Never rehearse on `fraud-detector`.** Use `--model-name fraud-detector-smoke`.
   `fraud-detector@champion` must be absent before *and* after a rehearsal.
2. **`--promote` requires a gate report** in which every `gate_*` entry is
   literally `true`. A missing gate is a refusal, not a default.
3. **Passing the gates is not permission to promote.** The production promotion
   additionally requires the single approved D48 measurement and the P4/P1
   sign-off (see `docs/decisions.md`, D48).
4. **Only the alias moves.** No code change, no new migration, no artifact
   rewrite. The deployment references `models:/fraud-detector@champion`, so the
   rollout is a registry operation.
5. **Capture the evidence.** An alias move without a recorded before/after is not
   auditable.

## Preconditions

```bash
kubectl -n ml get pods                      # mlflow 1/1, ml-service 2/2
kubectl -n ml port-forward svc/mlflow 5001:5000 &
export MLFLOW_TRACKING_URI=http://127.0.0.1:5001
export MLFLOW_DISABLE_AGENT_HINT=1
```

The registry is reachable when `curl -s $MLFLOW_TRACKING_URI/health` returns
`OK`. Set `PYTHONPATH=.` and use the project virtualenv.

## 1. The gate report

The report is the JSON produced by the pipeline's `6_quality_gates` stage. The
script reads the `gates` object (or the whole payload) and only inspects keys
starting with `gate_`:

```json
{
  "gates": {
    "gate_non_regression": true,
    "gate_coverage": true,
    "gate_coverage_legit": true,
    "gate_coverage_fraud": true,
    "gate_review_rate": true,
    "gate_latency": true
  }
}
```

The gate semantics (thresholds, D44/D45 references) are in `README.md` §3.3.

The only supported source is the `gate_*` metrics logged by the `6_quality_gates`
stage (in `--mode full` or `--mode evaluate`). `final_metrics.json` produced by
the D48 CLI is **not** a valid report: its keys are `coverage_by_class`,
`review_capacity` and `latency`. Export the logged metrics — see §3, step 2.

## 2. Rehearsal on a throwaway model

### 2.1 Seed two versions

```bash
python -m ml.scripts.register_champion \
  --artifact ~/d48/candidate_model.joblib \
  --metadata ~/d48/metadata.json \
  --tracking-uri "$MLFLOW_TRACKING_URI" \
  --experiment promotion-rehearsal \
  --model-name fraud-detector-smoke > /tmp/register-v1.log 2>&1
```

Repeat once to obtain a second version. Each call creates a provisional version
and moves `challenger` to it.

> `--model-version` is a **packaging label**, not the registry version: MLflow
> assigns `1`, `2`, `3`, … itself. Read it from the command output, never assume
> it.

### 2.2 Prove the gates are enforced

```bash
# one gate false -> refused
python -m ml.scripts.register_champion ... --model-name fraud-detector-smoke \
  --promote --gates ~/promotion-rehearsal/gates-fail.json
# ValueError: Portes non validees : gate_latency     (exit 1)

# no report at all -> refused
python -m ml.scripts.register_champion ... --model-name fraud-detector-smoke --promote
# ValueError: --promote exige --gates avec les portes de qualite.   (exit 1)
```

Neither call registers a version: validation happens before the artifact is
loaded.

### 2.3 Promote

```bash
python -m ml.scripts.register_champion \
  --artifact ~/d48/candidate_model.joblib \
  --metadata ~/d48/metadata.json \
  --tracking-uri "$MLFLOW_TRACKING_URI" \
  --experiment promotion-rehearsal \
  --model-name fraud-detector-smoke \
  --promote --gates ~/promotion-rehearsal/gates-pass.json \
  > /tmp/promote.log 2>&1
```

Expected tail of the output:

```
Created version '3' of model 'fraud-detector-smoke'.
  "version": "3",
  "alias": "champion",
  "aliases": { "champion": "3" },
```

### 2.4 Verify the alias and the served behaviour

```bash
python - <<'PY'
import numpy as np, joblib, mlflow
from mlflow import MlflowClient
from ml.src.pipeline.run import _load_python_model
from ml.src.evaluation.probe import identity_probe

mlflow.set_tracking_uri("http://127.0.0.1:5001")
c = MlflowClient()
print("champion ->", c.get_model_version_by_alias("fraud-detector-smoke", "champion").version)

frozen = joblib.load("/home/omar/d48/candidate_model.joblib")
ref = np.asarray(frozen.batch_probabilities(identity_probe()), dtype=float)
served = _load_python_model("models:/fraud-detector-smoke@champion")
probs = np.asarray(served.batch_probabilities(identity_probe()), dtype=float)
print(f"parity max|d|={np.max(np.abs(probs - ref)):.1e} alpha={served.alpha}")
PY
```

Parity must be `0.0e+00` on the eight-row probe, with `alpha=0.02` and the D44
thresholds. This is the same path the D48 binding uses
(`_load_python_model` + `batch_probabilities`, `atol=1e-9`).

### 2.5 Roll back

```bash
python - <<'PY'
from mlflow import MlflowClient
c = MlflowClient()
c.set_registered_model_alias("fraud-detector-smoke", "champion", "2")
print("champion ->", c.get_model_version_by_alias("fraud-detector-smoke", "champion").version)
PY
```

Re-run the parity block against `@champion`: rolling back to a **previous version
of the same candidate** keeps parity at `0.0e+00`.

Rolling back to a **different model** (the rehearsal's synthetic `version 1`)
legitimately fails parity against the D44 joblib (`2.0e-01`). That is the
expected signal that the alias changed which model is served, not a defect.

### 2.6 Restore and assert production is untouched

```bash
python - <<'PY'
from mlflow import MlflowClient
c = MlflowClient()
c.set_registered_model_alias("fraud-detector-smoke", "champion", "1")  # pre-rehearsal state
print("smoke champion ->", c.get_model_version_by_alias("fraud-detector-smoke", "champion").version)
try:
    print("fraud-detector champion ->", c.get_model_version_by_alias("fraud-detector", "champion").version)
except Exception:
    print("fraud-detector champion -> ABSENT (unchanged)")
print("fraud-detector challenger ->", c.get_model_version_by_alias("fraud-detector", "challenger").version)
print("status ->", c.get_model_version("fraud-detector", "1").tags.get("status"))
PY
```

### 2.7 Observed transcript (2026-11-21, kind `fintech`)

| Step | Result |
|---|---|
| Register candidate #1 | version `2`, alias `challenger`, `status=PROVISIONAL` |
| Promote with `gate_latency: false` | `ValueError: Portes non validees : gate_latency`, exit `1`, no version created |
| Promote without `--gates` | `ValueError: --promote exige --gates …`, exit `1` |
| Promote with all gates true | version `3`, `champion` → `3`, `challenger` → `2` |
| Parity `smoke/2`, `smoke/3`, `@champion`, `fraud-detector/1` | `max|d| = 0.0e+00`, `alpha=0.02`, `thresholds 0.004935831171766689 / 0.9905519026812524` |
| Rollback `champion` → `2` | alias `2`, parity `0.0e+00` |
| Rollback `champion` → `1` | alias `1`, parity `2.0e-01` (different model, expected) |
| Production at the end | `challenger` → `1`, `champion` absent, `status=PROVISIONAL` |

## 3. Production promotion (only after D48 and sign-off)

Prerequisites, all mandatory:

- [ ] the single approved D48 measurement is `completed` and its artifacts verified;
- [ ] the gate report from the verified evaluation has every `gate_*` true;
- [ ] P4/P1 sign-off recorded on the PR or issue;
- [ ] the code revision in `main` is the one the measurement was produced with.

```bash
# 1. Confirm the starting point
kubectl -n ml get cm ml-service-config -o jsonpath='{.data.MODEL_URI}{"\n"}'

# 2. Trust the verified evaluation, not a text file: export the gate_* metrics
#    logged by `run.py --mode evaluate` (step 6_quality_gates) into a report.
python - <<'PY'
import json
from mlflow import MlflowClient
c = MlflowClient()
run = c.get_run("<run id printed by run.py --mode evaluate>")
gates = {key: value == 1.0 for key, value in run.data.metrics.items() if key.startswith("gate_")}
print(gates)
assert gates and all(gates.values()), "a gate did not pass"
json.dump({"gates": gates}, open("/home/omar/d48/results/quality-gates.json", "w"), indent=2)
PY

# 3. Register the measured candidate and move the alias in one step
python -m ml.scripts.register_champion \
  --artifact ~/d48/candidate_model.joblib \
  --metadata ~/d48/metadata.json \
  --tracking-uri "$MLFLOW_TRACKING_URI" \
  --experiment fraud-detector-registry \
  --model-name fraud-detector \
  --promote --gates ~/d48/results/quality-gates.json \
  > /tmp/promotion-production.log 2>&1
```

> `final_metrics.json` is **not** a valid `--gates` file: its keys are
> `coverage_by_class`, `review_capacity`, `latency`, and the script requires
> `gate_*` keys. Exporting the logged metrics (step 2) is the supported path.

Then point the deployment at the alias (single PR, `deploy/k8s/ml-service/configmap.yaml`):

```yaml
MODEL_MODE: "real"
MODEL_URI: "models:/fraud-detector@champion"
```

and let the rollout happen, or force it:

```bash
kubectl -n ml rollout restart deployment/ml-service
kubectl -n ml rollout status deployment/ml-service --timeout=180s
```

Post-promotion checks (all four must pass). Run them inside the pod so the
in-cluster Service name is the one under test:

```bash
# 1. served model metadata
kubectl -n ml exec deploy/ml-service -- \
  python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/api/v1/ml/model').read().decode())"
# version = the promoted version, mode = real, alpha = 0.02

# 2. the exported gauge must match the alias
kubectl -n ml exec deploy/ml-service -- \
  python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/metrics').read().decode())" \
  | grep '^ml_model_info'
# ml_model_info{name="fraud-detector",version="<promoted>"} 1.0

# 3. one conformal prediction, inside the pod
kubectl -n ml exec -i deploy/ml-service -- python - <<'PY'
import json, urllib.request, uuid

payload = {
    "transaction_id": str(uuid.uuid4()),
    "trans_datetime": "2020-07-14T02:13:45",
    "amount": 150.0,
    "category": "shopping_net",
    "merch_lat": 40.71,
    "merch_long": -74.01,
    "customer": {"dob": "1962-05-18", "gender": "F", "city_pop": 1577385,
                 "lat": 40.65, "long": -73.95, "state": "NY"},
}
request = urllib.request.Request(
    "http://127.0.0.1:8000/predict",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "X-Correlation-Id": str(uuid.uuid4())},
)
print(urllib.request.urlopen(request).read().decode())
PY
# prediction_set must be one of [0], [1], [0,1], [] — unchanged by the promotion

# 4. visualisations (view is required: class, cluster, outlier, error, uncertainty)
kubectl -n ml exec deploy/ml-service -- \
  python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/api/v1/ml/viz/pca?view=class').status)"
```

The API surface through the gateway is checked separately (`/api/v1/ml/model`,
`/api/v1/ml/performance`, `/api/v1/ml/viz/{method}`); `/predict` is internal and
must still answer `404` through the ingress.

If `ml_model_info` still reports the old version, the pod is serving its cache:
check the rollout, then `kubectl -n ml logs deploy/ml-service | tail -40`.

## 4. Production rollback

The rollback target is the last version that was in production (here `1`).

```bash
python - <<'PY'
from mlflow import MlflowClient
c = MlflowClient()
c.set_registered_model_alias("fraud-detector", "champion", "1")
print("champion ->", c.get_model_version_by_alias("fraud-detector", "champion").version)
PY

kubectl -n ml rollout restart deployment/ml-service
kubectl -n ml rollout status deployment/ml-service --timeout=180s
```

Then repeat the four post-promotion checks. The rollback is complete when
`/api/v1/ml/model` reports the previous version and `ml_model_info` matches it.

Under GitOps, the equivalent is a `git revert` of the promotion PR; the alias is
still the object that moved, so both paths converge.

## 5. Failure modes

| Symptom | Cause | Action |
|---|---|---|
| `Portes non validees : gate_…` | a gate is false in the report | do not promote; investigate the gate, not the file |
| `--promote exige --gates …` | `--promote` without a report | pass the report |
| `Aucune porte 'gate_*' trouvee` | wrong JSON shape | the payload must contain the `gate_*` keys |
| `Registered model … not found` | wrong `--model-name`, or MLflow not reachable | check `$MLFLOW_TRACKING_URI/health` and the name |
| command exits `120` with no JSON | stdout was piped to `head`/`grep -m1` and closed early | redirect to a file; the run may have logged a model without moving the alias |
| alias moved but `/model` unchanged | pod serving its cache | `rollout restart`, then re-check `ml_model_info` |
| `challenger`/`champion` read as empty | `search_model_versions` does not populate `aliases` | use `get_model_version` or `get_model_version_by_alias` |

## 6. Evidence checklist

Record in the PR (and in the defence material):

- [ ] gate report path + SHA-256, and the six gate values;
- [ ] alias before → after, with the `MlflowClient` output;
- [ ] `/api/v1/ml/model` and `ml_model_info` after the rollout;
- [ ] the three `/predict` cases (`[0]`, `[1]`, `[]`) with their sets;
- [ ] probe parity (`max|d|`, `alpha`, thresholds);
- [ ] D48 approval and the P4/P1 sign-off reference;
- [ ] rollback rehearsal reference (this document, §2.7).

## 7. Known environment notes

- The local virtualenv may carry newer `numpy`/`pandas` than the pinned runtime
  (`numpy==2.4.6`, `pandas==3.0.6`). MLflow prints a dependency-mismatch warning;
  it does not affect the registry write, and the probe parity is still exact.
- Do not compare models through `pyfunc.load_model(...).predict(api_frame)` when
  the claim is "same model": that path goes through the signature adapter and
  shows a small difference (`4.2e-05`). Use `_load_python_model(...)` and
  `batch_probabilities(identity_probe())`, as the D48 binding does.
- The rehearsal model `fraud-detector-smoke` is intentionally left in the
  registry as evidence. It is not served and not referenced by any deployment.
