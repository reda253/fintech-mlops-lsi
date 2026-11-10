"""Unit tests for calibration and Mondrian conformal helpers (§4.10)."""

import numpy as np
import pytest

from ml.src.model.calibration import (
    IdentityCalibrator,
    PlattCalibrator,
    build_prediction_set,
    conformal_quantile,
    correct_proba,
    decide,
    fit_calibrator,
    mondrian_thresholds,
)


def test_correct_proba_matches_closed_form():
    probabilities = np.array([0.01, 0.5, 0.9])
    beta = 0.2
    expected = (beta * probabilities) / (beta * probabilities + (1.0 - probabilities))
    np.testing.assert_allclose(correct_proba(probabilities, beta), expected)
    np.testing.assert_allclose(correct_proba(probabilities, 1.0), probabilities)


@pytest.mark.parametrize("beta", [0.0, -0.1, 1.1, float("nan")])
def test_correct_proba_rejects_invalid_beta(beta):
    with pytest.raises(ValueError):
        correct_proba([0.1, 0.2], beta)


def test_conformal_quantile_hand_calculation():
    scores = [0.5, 0.1, 0.4, 0.2, 0.3]
    # n = 5, alpha = 0.2 -> rank = ceil(6 * 0.8) = 5 -> 0.5
    assert conformal_quantile(scores, 0.2) == pytest.approx(0.5)
    # n = 5, alpha = 0.4 -> rank = ceil(6 * 0.6) = 4 -> 0.4
    assert conformal_quantile(scores, 0.4) == pytest.approx(0.4)
    # The finite sample cannot certify alpha = 0.01 -> conservative 1.0
    assert conformal_quantile(scores, 0.01) == pytest.approx(1.0)


def test_mondrian_thresholds_are_class_conditional():
    probabilities = np.array([0.0, 0.1, 0.2, 0.3, 0.7, 0.8, 0.9, 0.95])
    target = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    thresholds = mondrian_thresholds(probabilities, target, alpha=0.5)

    # Legit scores = probabilities themselves; fraud scores = 1 - probability.
    assert thresholds["threshold_legit"] == pytest.approx(0.2)
    assert thresholds["threshold_fraud"] == pytest.approx(0.2)
    assert thresholds["n_legit"] == 4
    assert thresholds["n_fraud"] == 4


def test_prediction_sets_and_decisions():
    assert build_prediction_set(0.01, threshold_legit=0.1, threshold_fraud=0.1) == [0]
    assert build_prediction_set(0.99, threshold_legit=0.1, threshold_fraud=0.1) == [1]
    assert build_prediction_set(0.5, threshold_legit=0.1, threshold_fraud=0.1) == []
    assert build_prediction_set(0.05, threshold_legit=0.1, threshold_fraud=0.98) == [0, 1]

    assert decide([0]) == "APPROUVER"
    assert decide([1]) == "BLOQUER"
    assert decide([0, 1]) == "REVUE"
    assert decide([]) == "REVUE"


def test_fit_calibrator_keeps_lowest_brier():
    rng = np.random.default_rng(42)
    target = rng.integers(0, 2, size=500)
    probabilities = np.clip(0.3 + 0.4 * target + rng.normal(0, 0.15, size=500), 0.0, 1.0)

    calibrator, method, before, after = fit_calibrator(probabilities, target)
    assert method in {"isotonic", "sigmoid"}
    assert after <= before
    calibrated = calibrator.predict(probabilities)
    assert np.all((calibrated >= 0.0) & (calibrated <= 1.0))


def test_calibrators_are_picklable_roundtrip():
    import pickle

    probabilities = np.array([0.1, 0.4, 0.7, 0.9])
    target = np.array([0, 0, 1, 1])
    for calibrator in (
        IdentityCalibrator(),
        PlattCalibrator().fit(probabilities, target),
    ):
        restored = pickle.loads(pickle.dumps(calibrator))
        np.testing.assert_allclose(
            calibrator.predict(probabilities), restored.predict(probabilities)
        )
