// k6 scenario for ml-service POST /predict (internal endpoint, never routed).
//
// /predict is not exposed through the api-gateway (contracts/gateway-routes.md),
// so this scenario must run inside the cluster: a Job in the `ml` namespace or
// `kubectl run` with `grafana/k6`. Port-forwarding is fine for a smoke test but
// must not be used for the reported numbers.
//
// Usage:
//   k6 run -e SCENARIO=smoke  -e BASE_URL=http://ml-service.ml.svc.cluster.local:8000 ml-predict.js
//   k6 run -e SCENARIO=target -e PAYLOADS=/scripts/payloads.json ml-predict.js
//
// See README.md in this directory for the full procedure.

import http from "k6/http";
import { check } from "k6";
import { randomBytes } from "k6/crypto";
import { SharedArray } from "k6/data";

const BASE_URL = (__ENV.BASE_URL || "http://ml-service.ml.svc.cluster.local:8000").replace(/\/+$/, "");
const PAYLOADS_PATH = __ENV.PAYLOADS || "/scripts/payloads.json";
const RESULTS_DIR = (__ENV.RESULTS_DIR || "").replace(/\/+$/, "");
const SCENARIO = __ENV.SCENARIO || "smoke";

// 200+ sustained TPS is the platform target; one /predict per transaction.
// The strict 50 ms figure is the *model* p95 (ml_inference_duration_seconds);
// the HTTP p95 below also contains FastAPI, JSON and the network hop.
const PROFILES = {
  smoke: {
    executor: "per-vu-iterations",
    vus: 1,
    iterations: 10,
    maxDuration: "1m",
  },
  baseline: {
    executor: "constant-arrival-rate",
    rate: 50,
    timeUnit: "1s",
    duration: "2m",
    preAllocatedVUs: 10,
    maxVUs: 60,
  },
  target: {
    executor: "constant-arrival-rate",
    rate: 200,
    timeUnit: "1s",
    duration: "5m",
    preAllocatedVUs: 50,
    maxVUs: 300,
  },
  stress: {
    executor: "ramping-arrival-rate",
    startRate: 50,
    timeUnit: "1s",
    stages: [
      { target: 200, duration: "1m" },
      { target: 400, duration: "2m" },
      { target: 400, duration: "2m" },
    ],
    preAllocatedVUs: 50,
    maxVUs: 400,
  },
  soak: {
    executor: "constant-arrival-rate",
    rate: 200,
    timeUnit: "1s",
    duration: "30m",
    preAllocatedVUs: 50,
    maxVUs: 300,
  },
};

function buildOptions(name) {
  if (!Object.prototype.hasOwnProperty.call(PROFILES, name)) {
    throw new Error(
      `SCENARIO inconnu: ${name} (attendu: ${Object.keys(PROFILES).join(", ")})`,
    );
  }
  const thresholds = {
    http_req_failed: ["rate<0.001"],
    checks: ["rate>0.999"],
  };
  if (name !== "smoke") {
    thresholds[`http_req_duration{scenario:${name}}`] = ["p(95)<50", "p(99)<150"];
  }
  return {
    scenarios: { [name]: PROFILES[name] },
    thresholds,
    summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max", "count"],
    tags: { suite: "ml-predict", profile: name },
  };
}

export const options = buildOptions(SCENARIO);

const payloads = new SharedArray("predict payloads", () => {
  const parsed = JSON.parse(open(PAYLOADS_PATH));
  if (!Array.isArray(parsed) || parsed.length === 0) {
    throw new Error(`PAYLOADS doit etre un tableau non vide: ${PAYLOADS_PATH}`);
  }
  return parsed;
});

function uuidv4() {
  const bytes = new Uint8Array(randomBytes(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10xx
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10, 16).join(""),
  ].join("-");
}

export default function () {
  const payload = payloads[Math.floor(Math.random() * payloads.length)];
  const body = JSON.stringify(payload);
  const response = http.post(`${BASE_URL}/predict`, body, {
    headers: {
      "Content-Type": "application/json",
      // Pydantic validates this header as a UUID: a non-UUID value returns 422.
      "X-Correlation-Id": uuidv4(),
    },
    tags: { endpoint: "/predict" },
  });

  let parsed = null;
  try {
    parsed = response.json();
  } catch (_) {
    parsed = null;
  }

  check(response, {
    "status is 200": (r) => r.status === 200,
    "body has a prediction_set": () => parsed !== null && Array.isArray(parsed.prediction_set),
    "prediction_set has 0..2 items": () =>
      parsed !== null &&
      Array.isArray(parsed.prediction_set) &&
      parsed.prediction_set.length <= 2,
    "alpha is a probability": () =>
      parsed !== null && typeof parsed.alpha === "number" && parsed.alpha > 0 && parsed.alpha < 1,
    "inference_ms is reported": () =>
      parsed !== null && typeof parsed.inference_ms === "number" && parsed.inference_ms >= 0,
  });
}

export function handleSummary(data) {
  const metrics = data.metrics;
  const p95 = metrics.http_req_duration?.values?.["p(95)"] ?? NaN;
  const p99 = metrics.http_req_duration?.values?.["p(99)"] ?? NaN;
  const failed = metrics.http_req_failed?.values?.rate ?? NaN;
  const checksRate = metrics.checks?.values?.rate ?? NaN;
  const count = metrics.http_reqs?.values?.count ?? 0;
  const rps = metrics.http_reqs?.values?.rate ?? 0;
  const checksPassed = metrics.checks?.values?.passes ?? 0;
  const checksFailed = metrics.checks?.values?.fails ?? 0;

  const summary = [
    `profile            ${SCENARIO}`,
    `requests           ${count} (${rps.toFixed(1)}/s)`,
    `http_req_failed    ${(failed * 100).toFixed(3)} %`,
    `checks             ${(checksRate * 100).toFixed(3)} % (${checksPassed} ok / ${checksFailed} ko)`,
    `http p95           ${p95.toFixed(2)} ms`,
    `http p99           ${p99.toFixed(2)} ms`,
    "",
    "model-only p95 must be read from Prometheus:",
    '  histogram_quantile(0.95, sum by (le) (rate(ml_inference_duration_seconds_bucket[1m])))',
  ].join("\n");

  const output = { stdout: `${summary}\n` };
  // A completed Job's pod cannot be `kubectl cp`-ed from, so the machine-readable
  // summary is also emitted on stdout, one line, prefixed for reliable grep.
  output.stdout += `K6_SUMMARY_JSON ${JSON.stringify(data)}\n`;
  if (RESULTS_DIR) {
    output[`${RESULTS_DIR}/summary.json`] = JSON.stringify(data, null, 2);
  }
  return output;
}
