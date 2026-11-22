# Model promotion and rollback runbook

Owner: P3 (`@omar-aouichi`). Applies to `fraud-detector` in the `ml` namespace.

Promotion moves the `champion` alias to the version that was measured. Rollback
moves it back. Both are registry operations; neither retrains, re-registers nor
edits a model artifact.

## Invariants

1. **Never rehearse on `fraud-detector`.** Use `--model-name fraud-detector-smoke`.
   `fraud-detector@champion` must be absent before *and* after a rehearsal.
2. **Promotion needs an attributed report**, not six booleans: the six §5.4 gates
   plus the provenance of the D48 evaluation that produced them (parent run,
   `6_quality_gates` child run, candidate/source/protocol fingerprints). The
   script re-reads the MLflow runs to confirm it.
3. **Promote the measured version**, with `--promote-version`. A fresh
   `--artifact … --promote` registers a *new* version, which is not the object
   D48 evaluated; use it only when re-packaging is unavoidable, and redo the
   parity checks.
4. **Passing the gates is not permission to promote.** Production promotion also
   requires the single approved D48 measurement and the P4/P1 sign-off
   (`docs/decisions.md`, D48).
5. **The alias alone changes nothing in a running pod.** `ml-service` caches the
   model at startup; a rollout restart is what makes the new version served.
6. **Capture the evidence.** An alias move without a recorded before/after is not
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

The report is built from the runs of the D48 evaluation, never typed by hand:

```json
{
  "gates": {
    "gate_non_regression": true,
    "gate_coverage": true,
    "gate_coverage_legit": true,
    "gate_coverage_fraud": true,
    "gate_review_rate": true,
    "gate_latency": true
  },
  "provenance": {
    "decision_id": "D48",
    "parent_run_id": "<pipeline-evaluate run>",
    "gates_run_id": "<6_quality_gates child run>",
    "candidate_sha256": "aa1565ca…da33",
    "source_sha256": "7e50d0ce…e3b3",
    "protocol_sha256": "b0bfaf9b…adc24",
    "model_uri": "models:/fraud-detector/1"
  }
}
```

The validator requires **exactly** the six gates (a subset — e.g. only
`gate_latency` — is refused, and so is an unknown `gate_*`), each explicitly
`true`. It then checks, in this order:

- `decision_id` is `D48`; the three fingerprints are 64-hex and equal to the
  approved constants (D44 model, D48 source, D48 protocol);
- `candidate_sha256` equals the artifact being registered (or the
  `source_model_sha256` tag of the version being promoted);
- the parent run carries `decision_id=D48`,
  `evaluation_source=final_evaluation_artifacts`, the same `candidate_sha256`,
  and — for `--promote-version` — the same `model_uri`;
- the child run is named `6_quality_gates`, its `mlflow.parentRunId` is the
  parent, its six `gate_*` metrics are all `1.0`, and its
  `quality_gates_passed` param is `True`;
- the parent has **exactly one** `5_evaluate` child, and that child's
  `evaluation_model_sha256`, `evaluation_source_sha256` and
  `evaluation_protocol_sha256` tags exist and equal the report's three
  fingerprints. This is what ties the report to the run that actually consumed
  the artifacts: without it, a report could declare the approved source and
  protocol while the run that produced the metrics verified another one.

A training run has a `6_quality_gates` child too, but no
`evaluation_source=final_evaluation_artifacts` tag: it is refused. That is the
point of the provenance check.

Export the report from the runs (see §3, step 2). `final_metrics.json` produced
by the D48 CLI is **not** a valid report: its keys are `coverage_by_class`,
`review_capacity` and `latency`.

## 2. Rehearsal on a throwaway model

The alias mechanics below were rehearsed on 2026-11-21, before the provenance
rule existed. The gate/provenance refusals are now covered by
`ml/tests/test_register_champion.py`; the first promotion that exercises them
end to end is the production one, after D48.

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

### 2.2 Prove the refusals

```bash
# one gate false
python -m ml.scripts.register_champion --artifact … --model-name fraud-detector-smoke \
  --promote --gates ~/promotion-rehearsal/gates-fail.json
# ValueError: Portes non validees : gate_latency             (exit 1)

# no report at all
python -m ml.scripts.register_champion --artifact … --model-name fraud-detector-smoke --promote
# ValueError: --promote exige --gates avec les portes de qualite.   (exit 1)

# six gates but no provenance
# TypeError: Provenance absente : rapport de portes non attribuable.

# provenance pointing at another candidate/source/protocol
# ValueError: Provenance : source differente de la source approuvee pour D48
```

Validation happens before the artifact is loaded: no version is created by a
refused call.

### 2.3 Promote (alias mechanics)

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

Expected tail: `Created version '3'…`, `"alias": "champion"`.

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

Parity must be `0.0e+00`, with `alpha=0.02` and the D44 thresholds. This is the
path the D48 binding uses (`_load_python_model` + `batch_probabilities`,
`atol=1e-9`). Do **not** compare through `pyfunc.load_model(...).predict(frame)`:
the signature adapter introduces a `4.2e-05` difference that has nothing to do
with the model.

### 2.5 Roll back

```bash
python - <<'PY'
from mlflow import MlflowClient
c = MlflowClient()
c.set_registered_model_alias("fraud-detector-smoke", "champion", "2")
print("champion ->", c.get_model_version_by_alias("fraud-detector-smoke", "champion").version)
PY
```

Rolling back to a **previous version of the same candidate** keeps parity at
`0.0e+00`. Rolling back to a **different model** (the synthetic `version 1`)
legitimately fails parity against the D44 joblib (`2.0e-01`) — that is the
expected signal that the alias changed which model is served.

### 2.6 Restore and assert production is untouched

```bash
python - <<'PY'
from mlflow import MlflowClient
c = MlflowClient()
c.set_registered_model_alias("fraud-detector-smoke", "champion", "1")
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
| Promote with `gate_latency: false` | `Portes non validees : gate_latency`, exit `1`, no version created |
| Promote without `--gates` | `--promote exige --gates …`, exit `1` |
| Promote with all gates true | version `3`, `champion` → `3`, `challenger` → `2` |
| Parity `smoke/2`, `smoke/3`, `@champion`, `fraud-detector/1` | `max|d| = 0.0e+00`, `alpha=0.02` |
| Rollback `champion` → `2` | alias `2`, parity `0.0e+00` |
| Rollback `champion` → `1` | alias `1`, parity `2.0e-01` (different model, expected) |
| Production at the end | `challenger` → `1`, `champion` absent, `status=PROVISIONAL` |

## 3. Production promotion (only after D48 and sign-off)

Prerequisites, all mandatory:

- [ ] the single approved D48 measurement is `completed` and its artifacts verified;
- [ ] P4/P1 sign-off recorded on the PR or issue;
- [ ] the code revision in `main` is the one the measurement was produced with.

### 3.1 Confirm what was measured

```bash
python - <<'PY'
from mlflow import MlflowClient
c = MlflowClient()
for mv in c.search_model_versions("name='fraud-detector'"):
    fresh = c.get_model_version("fraud-detector", mv.version)
    print(fresh.version, fresh.aliases, fresh.tags.get("status"),
          fresh.tags.get("source_model_sha256"))
PY
```

The version whose `source_model_sha256` is `aa1565ca…da33` is the measured one
(`1` today). The D48 parent run must have `model_uri=models:/fraud-detector/1`.

### 3.2 Build the report from the runs

```bash
python - <<'PY'
import json
from mlflow import MlflowClient

REQUIRED = (
    "gate_non_regression", "gate_coverage", "gate_coverage_legit",
    "gate_coverage_fraud", "gate_review_rate", "gate_latency",
)
c = MlflowClient()
parent_id = input("run id of `pipeline-evaluate`: ").strip()
parent = c.get_run(parent_id)
if parent.data.tags.get("decision_id") != "D48":
    raise SystemExit("ce run n'est pas une evaluation D48")

experiment_id = parent.info.experiment_id
children = c.search_runs(
    [experiment_id], filter_string=f"tags.`mlflow.parentRunId` = '{parent_id}'"
)
gates_run = next(
    r for r in children
    if r.data.tags.get("mlflow.runName", "").startswith("6_quality_gates")
)
gates = {name: gates_run.data.metrics.get(name) == 1.0 for name in REQUIRED}
if not all(gates.values()):
    raise SystemExit(f"portes non validees : {gates}")

report = {
    "gates": gates,
    "provenance": {
        "decision_id": "D48",
        "parent_run_id": parent_id,
        "gates_run_id": gates_run.info.run_id,
        "candidate_sha256": parent.data.tags["candidate_sha256"],
        "source_sha256": "7e50d0ce13f08b45ed1740127fe56f9c90c8eeec37a11288a372afcc61efe3b3",
        "protocol_sha256": "b0bfaf9ba5b9c3b40dc91c52d34281227846fce4d11b24ff6bf9a166550adc24",
        "model_uri": parent.data.tags["model_uri"],
    },
}
path = "/home/omar/d48/results/quality-gates.json"
json.dump(report, open(path, "w"), indent=2)
print("wrote", path)
PY
```

The two pinned fingerprints are the approved ones; copy them from
`final_metrics.json` and compare — a typo is refused, not silently accepted.

### 3.3 Move the alias

```bash
python -m ml.scripts.register_champion \
  --promote-version 1 \
  --model-name fraud-detector \
  --tracking-uri "$MLFLOW_TRACKING_URI" \
  --gates /home/omar/d48/results/quality-gates.json \
  > /tmp/promotion-production.log 2>&1
```

`--promote-version` promotes the **already registered, already measured**
version: it checks the version's `source_model_sha256`, the parent run's
`model_uri`, then moves the alias and sets `status=CHAMPION`. It does not create
a version.

#### Alternative: re-packaging

Only if the served artifact must differ from the measured one (dependency
change, pyfunc rebuild):

```bash
python -m ml.scripts.register_champion \
  --artifact ~/d48/candidate_model.joblib --metadata ~/d48/metadata.json \
  --model-name fraud-detector --promote --gates …/quality-gates.json
```

This creates a new version. The measured object is still the old one, so before
serving it: re-run the probe parity of §2.4 against the new version, compare its
`threshold_legit`/`threshold_fraud`/`alpha` tags with the previous version, and
record why the re-packaging was necessary.

### 3.4 Point the deployment at the alias

One PR on `deploy/k8s/ml-service/configmap.yaml`:

```yaml
MODEL_MODE: "real"
MODEL_URI: "models:/fraud-detector@champion"
```

Then roll the pods — the alias is not observed by a running pod:

```bash
kubectl -n ml rollout restart deployment/ml-service
kubectl -n ml rollout status deployment/ml-service --timeout=180s
```

### 3.5 Post-promotion checks (all four must pass)

```bash
kubectl -n ml exec deploy/ml-service -- \
  python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/api/v1/ml/model').read().decode())"
# version = the promoted version, mode = real, alpha = 0.02

kubectl -n ml exec deploy/ml-service -- \
  python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/metrics').read().decode())" \
  | grep '^ml_model_info'
# ml_model_info{name="fraud-detector",version="<promoted>"} 1.0

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

kubectl -n ml exec deploy/ml-service -- \
  python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/api/v1/ml/viz/pca?view=class').status)"
```

If `ml_model_info` still reports the old version, the pod is serving its cache:
check the rollout, then `kubectl -n ml logs deploy/ml-service | tail -40`.

## 4. Production rollback

The target is the version that was served before the promotion (`1` today).

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

Then repeat the four checks of §3.5. The rollback is complete when
`/api/v1/ml/model` reports the previous version and `ml_model_info` matches it.

**GitOps does not roll this back by itself.** Reverting the promotion PR reverts
the *ConfigMap*; once `MODEL_URI` is `models:/fraud-detector@champion`, the
ConfigMap is unchanged by a promotion, so a `git revert` restores nothing about
the served model. The alias is the object that moved. If the revert matters for
the record, do both: move the alias back **and** revert the PR that introduced
the alias reference.

## 5. Failure modes

| Symptom | Cause | Action |
|---|---|---|
| `Portes manquantes : …` | a gate is absent from the report | rebuild the report from the run, do not edit it by hand |
| `Portes non validees : …` | a gate is false | do not promote; investigate the gate |
| `Portes inconnues : …` | an extra `gate_*` key | remove it; the six are fixed |
| `Provenance absente` | a bare `{"gate_…": true}` file | rebuild it from §3.2 |
| `Provenance : source/protocole different …` | wrong or edited fingerprint | copy the approved constants; the D48 protocol text is frozen |
| `Provenance : run MLflow introuvable` | wrong run id, or MLflow not reachable | check `$MLFLOW_TRACKING_URI/health` |
| `Provenance : le run parent n'est pas une evaluation D48` | a training run's gates | only `run.py --mode evaluate` produces a promotable report |
| `Provenance : modele evalue … different` | the run measured another version | promote the version that was measured |
| `Provenance : run enfant 5_evaluate introuvable ou multiple` | the report is not tied to an evaluation run of that parent | rebuild it from the `pipeline-evaluate` run |
| `Provenance : tag evaluation_… absent du run 5_evaluate` | the run predates the fingerprint tags, or is not the D48 path | re-run the evaluation from merged code; do not invent the tag |
| `Provenance : evaluation_… du run 5_evaluate different du rapport` | the report declares a source/protocol the run did not verify | rebuild the report from the run, never edit it |
| `Version sans tag source_model_sha256` | an imported version with no provenance | re-register it with `register_champion` |
| `porte deja l'alias champion` | already promoted | nothing to do |
| command exits `120` with no JSON | stdout piped to `head`/`grep -m1` | redirect to a file; the run may have logged a model before dying |
| alias moved but `/model` unchanged | pod serving its cache | `rollout restart`, then re-check `ml_model_info` |
| `challenger`/`champion` read as empty | `search_model_versions` does not populate `aliases` | use `get_model_version` or `get_model_version_by_alias` |

## 6. Evidence checklist

- [ ] gate report path + SHA-256, the six gate values, and both run ids;
- [ ] alias before → after, with the `MlflowClient` output;
- [ ] `/api/v1/ml/model` and `ml_model_info` after the rollout;
- [ ] the `/predict` case with its `prediction_set`;
- [ ] probe parity (`max|d|`, `alpha`, thresholds);
- [ ] D48 approval and the P4/P1 sign-off reference;
- [ ] rollback rehearsal reference (§2.7) and the reason, if a re-packaging was used.

## 7. Known environment notes

- The local virtualenv may carry newer `numpy`/`pandas` than the pinned runtime
  (`numpy==2.4.6`, `pandas==3.0.6`). MLflow prints a dependency-mismatch warning;
  it does not affect the registry write, and the probe parity is still exact.
- The rehearsal model `fraud-detector-smoke` is intentionally left in the
  registry as evidence. It is not served and not referenced by any deployment.
