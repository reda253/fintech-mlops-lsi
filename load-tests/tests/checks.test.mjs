// Node tests for the contract checks used by the k6 scenario.
// Run with: node --test load-tests/tests

import test from "node:test";
import assert from "node:assert/strict";

import {
  ALLOWED_SETS,
  contractIssues,
  expectedValues,
  isAllowedSet,
} from "../scenarios/checks.mjs";

const EXPECTED = { alpha: 0.02, modelName: "fraud-detector", modelVersion: "1" };

function body(overrides = {}) {
  return {
    transaction_id: "0d6a0d54-8b0f-4a4e-9b0f-4f9f0d4b5a11",
    prediction: 0,
    fraud_probability: 0.0123,
    prediction_set: [0],
    uncertainty: 0.01,
    uncertainty_level: "FAIBLE",
    alpha: 0.02,
    model: { name: "fraud-detector", version: "1" },
    inference_ms: 3.4,
    ...overrides,
  };
}

test("the four conformal outcomes are the only allowed sets", () => {
  assert.deepEqual(ALLOWED_SETS, [[], [0], [1], [0, 1]]);
  for (const allowed of ALLOWED_SETS) {
    assert.equal(isAllowedSet(allowed), true, JSON.stringify(allowed));
  }
});

test("impossible or reordered sets are refused", () => {
  for (const value of [[9, 9], [0, 0], [1, 1], [1, 0], "[]", [0, 1, 2], null]) {
    assert.equal(isAllowedSet(value), false, JSON.stringify(value));
  }
});

test("a real conformal response has no contract issue", () => {
  assert.deepEqual(contractIssues(body(), EXPECTED), []);
  for (const allowed of ALLOWED_SETS) {
    assert.deepEqual(contractIssues(body({ prediction_set: allowed }), EXPECTED), []);
  }
});

test("mock mode is refused", () => {
  const problems = contractIssues(
    body({ model: { name: "fraud-detector", version: "mock" } }),
    EXPECTED,
  );
  assert.ok(problems.includes("mode mock"), problems.join("; "));
});

test("another alpha is refused", () => {
  const problems = contractIssues(body({ alpha: 0.05 }), EXPECTED);
  assert.ok(problems.some((problem) => problem.startsWith("alpha")), problems.join("; "));
});

test("another model or version is refused", () => {
  assert.ok(
    contractIssues(body({ model: { name: "other", version: "1" } }), EXPECTED).some((p) =>
      p.startsWith("modele"),
    ),
  );
  assert.ok(
    contractIssues(body({ model: { name: "fraud-detector", version: "2" } }), EXPECTED).some(
      (p) => p.startsWith("version"),
    ),
  );
});

test("an impossible set is refused", () => {
  const problems = contractIssues(body({ prediction_set: [9, 9] }), EXPECTED);
  assert.ok(
    problems.some((problem) => problem.startsWith("ensemble")),
    problems.join("; "),
  );
});

test("a malformed body is reported, not silently accepted", () => {
  assert.deepEqual(contractIssues(null, EXPECTED), ["corps non JSON"]);
  assert.deepEqual(contractIssues("{}", EXPECTED), ["corps non JSON"]);
});

test("expected values default to D44 and can be overridden by the environment", () => {
  assert.deepEqual(expectedValues(), {
    alpha: 0.02,
    modelName: "fraud-detector",
    modelVersion: "1",
  });
  assert.deepEqual(expectedValues({ alpha: "0.02", modelVersion: 3 }), {
    alpha: 0.02,
    modelName: "fraud-detector",
    modelVersion: "3",
  });
});
