# `load-tests/scenarios/` — ml-service `/predict` load scenarios

Owner: P3 (`@omar-aouichi`) for the ML scenario; the `load-tests/` directory
belongs to P4 (`@ASSIL-Dev1`).

`POST /predict` is **not routed by the api-gateway** (`contracts/gateway-routes.md`:
`/predict` returns 404 through the ingress, and e2e scenario 7 asserts it). The
scenario therefore runs **inside the cluster**, in the `ml` namespace. A
port-forward is acceptable for the smoke test only; numbers reported in the
report must come from an in-cluster run, otherwise the port-forward becomes the
bottleneck.

Files:

| File | Purpose |
|---|---|
| `ml-predict.js` | k6 scenario (5 profiles, thresholds, JSON summary) |
| `checks.mjs` | pure contract checks (allowed sets, alpha, model version), shared with the Node tests |
| `generate_payloads.py` | builds fixed `/predict` payloads from `fraudTrain.csv` (stdlib only) |
| `ml-predict-job.yaml` | Kubernetes Job that runs the scenario in-cluster |

## 1. Build the payloads

The payloads must look like real Sparkov transactions, so they come from the
**development** block of `fraudTrain.csv` — never from `fraudTest.csv`, which is
reserved for the D48 measurement (the script refuses it by name before opening
it).

```bash
python3 load-tests/scenarios/generate_payloads.py \
  --source ~/d48-data/data/raw/fraudTrain.csv \
  --output /tmp/k6/payloads.json --sample-size 500
```

Expected output:

```
source        .../fraudTrain.csv (1296675 lignes)
cutoff        2019-12-28 17:18:24 (70% development)
candidates    907672
payloads      500 -> /tmp/k6/payloads.json
date range    2019-01-01T12:46:43 .. 2019-12-28T15:09:56
```

Each payload is a complete `PredictRequest` (nested `customer`, ISO datetime,
category from the contract enum). `transaction_id` is a fixed UUID per payload:
`/predict` is stateless and idempotency is a transaction-service concern.

## 2. Run it in-cluster

```bash
kubectl -n ml create configmap k6-ml-predict \
  --from-file=ml-predict.js=load-tests/scenarios/ml-predict.js \
  --from-file=checks.mjs=load-tests/scenarios/checks.mjs \
  --from-file=payloads.json=/tmp/k6/payloads.json \
  --dry-run=client -o yaml | kubectl apply -f -

# edit SCENARIO in the manifest (or patch it), then:
kubectl -n ml delete job k6-ml-predict --ignore-not-found
kubectl -n ml apply -f load-tests/scenarios/ml-predict-job.yaml
kubectl -n ml wait --for=condition=complete job/k6-ml-predict --timeout=20m ||
  kubectl -n ml logs job/k6-ml-predict --tail=60
```

Collect the summary from the logs. A completed Job's pod cannot be
`kubectl cp`-ed from (the container has exited), so `handleSummary` prints the
machine-readable JSON on one `K6_SUMMARY_JSON` line:

```bash
kubectl -n ml logs job/k6-ml-predict \
  | grep '^K6_SUMMARY_JSON' | sed 's/^K6_SUMMARY_JSON //' \
  > "summary-$(date +%Y%m%dT%H%M).json"

# quick read
jq '{p95: .metrics.http_req_duration.values["p(95)"],
     failed: .metrics.http_req_failed.values.rate,
     checks: .metrics.checks.values.rate,
     count: .metrics.http_reqs.values.count}' summary-*.json
```

Local smoke test through a port-forward (validation only, never reported):

```bash
kubectl -n ml port-forward svc/ml-service 8000:8000 &
docker run --rm --network host \
  -v "$PWD/load-tests/scenarios":/scripts:ro,z \
  -v /tmp/k6:/data:z \
  grafana/k6:0.54.0 run \
  -e SCENARIO=smoke -e BASE_URL=http://127.0.0.1:8000 \
  -e PAYLOADS=/data/payloads.json -e EXPECTED_VERSION=1 \
  /scripts/ml-predict.js
```

On an SELinux host the `:z` suffix on the mounts is required, and the mounts
must be readable by the container user (uid `12345`).

## 3. Profiles

| Profile | Executor | Load | Purpose |
|---|---|---|---|
| `smoke` | `per-vu-iterations` | 10 iterations | contract sanity before any load |
| `baseline` | `constant-arrival-rate` | 50 rps, 2 min | reference latency at low load |
| `target` | `constant-arrival-rate` | **200 rps, 5 min** | the platform target (200+ TPS) |
| `stress` | `ramping-arrival-rate` | 50 → 400 rps | HPA ceiling and saturation point |
| `soak` | `constant-arrival-rate` | 200 rps, 30 min | memory leaks, cache drift |

Every response is checked against the real contract, not just for HTTP 200:

- `status is 200`;
- `prediction_set` is exactly `[]`, `[0]`, `[1]` or `[0,1]` (a `[9,9]`, `[0,0]` or `[1,0]` fails);
- `alpha` equals `EXPECTED_ALPHA` (default `0.02`, D44) — a mock service answering `0.05` fails;
- `model.name` equals `EXPECTED_MODEL` and `model.version` equals `EXPECTED_VERSION` (default `1`), and `mock` is refused;
- `inference_ms` is reported.

Set those three variables for a run against another version.

Thresholds: `http_req_failed < 0.1 %`, `checks > 99.9 %`, `dropped_iterations == 0` for
every fixed-rate profile, and for every profile except `smoke`,
`http_req_duration{scenario:<profile>} p(95) < 50 ms`, `p(99) < 150 ms`.

The run **aborts** as soon as the failure rate exceeds 1 % (after a 10 s
evaluation delay), instead of hammering a failing service. k6 exits **99** when a
threshold fails — a failed threshold is a result to report, not a reason to re-run
until it passes.

## 4. The two p95 numbers

* `http_req_duration` (k6) = FastAPI + JSON + network + queueing. This is what a
  caller sees.
* `ml_inference_duration_seconds` (Prometheus, in-process) = model-only latency,
  the 50 ms figure the quality gate refers to.

Report both, and never present one as the other:

```promql
histogram_quantile(0.95,
  sum by (le) (rate(ml_inference_duration_seconds_bucket{job="ml-service"}[1m])))
```

Cross-check that the request count agrees with the model's own counter:

```promql
sum(increase(ml_predictions_total[5m]))
```

A large gap means dropped or retried requests and makes the run unreportable.

## 5. HPA evidence

Run these alongside `target`:

```bash
kubectl -n ml get hpa ml-service -w &          # target, current, replicas
kubectl -n ml get pods -l app=ml-service -w &  # pod count timeline
kubectl -n ml top pods -l app=ml-service       # CPU per pod at peak
```

Capture the Grafana panels "ML Inference Latency (p95)", "Request Rate" and the
replica count at the start, at peak and after the run. Expected shape: 200 rps
over 2 pods ≈ 100 rps/pod; the HPA (70 % CPU target, 2–5 replicas) should add
pods, and the latency curve should come back down. Record the observed curve —
do not assert a target the cluster did not reach.

## 6. Guardrails

- Coordinate the run with P4: the kind cluster is shared, and `target`, `stress`
  and `soak` disturb every other service.
- Never point the generator at `fraudTest.csv`; only the dev block is used.
- Keep `maxVUs` bounded; an arrival-rate executor that cannot spawn enough VUs
  reports `dropped_iterations`, which is itself a finding.
- Abort on `http_req_failed > 1 %` instead of continuing to hammer a failing
  service (enforced by the `abortOnFail` threshold).

## 7. Tests

```bash
python -m pytest load-tests/tests -q          # payload generator
node --test load-tests/tests/checks.test.mjs  # contract checks
```

The Node suite covers the cases that a healthy service never produces: mock
mode, `alpha=0.05`, `[9,9]`, `[1,0]`, a missing body. Both suites run in the
Python CI workflow.
