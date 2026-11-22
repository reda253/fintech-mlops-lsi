// Pure helpers shared by the k6 scenario and its Node tests.
//
// No k6 imports here on purpose: this module is imported both by
// ml-predict.js (inside the k6 runtime) and by checks.test.mjs (plain Node).

export const ALLOWED_SETS = Object.freeze([[], [0], [1], [0, 1]]);

export const DEFAULT_ALPHA = 0.02;
export const DEFAULT_MODEL_NAME = "fraud-detector";
export const DEFAULT_MODEL_VERSION = "1";

function setKey(value) {
  return JSON.stringify(value);
}

export function isAllowedSet(value) {
  if (!Array.isArray(value)) return false;
  return ALLOWED_SETS.some((allowed) => setKey(allowed) === setKey(value));
}

export function expectedValues(options = {}) {
  const alpha = options.alpha === undefined || options.alpha === "" ? DEFAULT_ALPHA : Number(options.alpha);
  return {
    alpha,
    modelName: options.modelName || DEFAULT_MODEL_NAME,
    modelVersion: String(options.modelVersion || DEFAULT_MODEL_VERSION),
  };
}

// Returns the list of contract violations for one /predict response body.
// An empty list means the response is a real conformal prediction from the
// expected model: any other outcome (mock mode, another alpha, an impossible
// set such as [9, 9]) is reported.
export function contractIssues(body, expected) {
  if (!body || typeof body !== "object") return ["corps non JSON"];

  const problems = [];
  const { alpha, modelName, modelVersion } = expected;

  if (!isAllowedSet(body.prediction_set)) {
    problems.push(`ensemble non conforme: ${setKey(body.prediction_set)}`);
  }
  if (body.alpha !== alpha) {
    problems.push(`alpha ${body.alpha} != ${alpha}`);
  }
  if (!body.model || body.model.name !== modelName) {
    problems.push(`modele ${body.model && body.model.name} != ${modelName}`);
  }
  if (body.model && body.model.version === "mock") {
    problems.push("mode mock");
  }
  if (!body.model || String(body.model.version) !== modelVersion) {
    problems.push(`version ${body.model && body.model.version} != ${modelVersion}`);
  }
  if (
    typeof body.fraud_probability !== "number" ||
    body.fraud_probability < 0 ||
    body.fraud_probability > 1
  ) {
    problems.push("fraud_probability hors [0,1]");
  }
  if (typeof body.inference_ms !== "number" || body.inference_ms < 0) {
    problems.push("inference_ms absent");
  }
  return problems;
}
