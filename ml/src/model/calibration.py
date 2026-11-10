"""Probability correction, calibration and Mondrian conformal utilities (§4.10, §5.3).

Pure helpers shared by P2's final training, the training pipeline and the
packaged pyfunc model. The module deliberately imports only numpy at module
level (sklearn is imported lazily inside the calibrators) so that it stays
importable inside the ml-service image and inside the MLflow artifact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


def _proba(p: np.ndarray) -> np.ndarray:
    values = np.asarray(p, dtype=float)
    if (
        values.ndim != 1
        or not np.isfinite(values).all()
        or ((values < 0) | (values > 1)).any()
    ):
        raise ValueError("Probabilités finies dans [0,1] requises")
    return values


def correct_proba(p: Any, beta: float) -> np.ndarray:
    """Correct the posterior learned on an undersampled train set.

    ``beta`` is the fraction of legitimate rows kept during undersampling
    (``n_kept / n_legit``), matching ``validation.fold_data.correct_proba``.
    """

    values = np.asarray(p, dtype=np.float64)
    if np.ndim(beta) != 0 or not np.isfinite(beta) or not 0 < beta <= 1:
        raise ValueError("beta doit etre fini dans ]0, 1].")
    if not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
        raise ValueError("Les probabilites doivent etre finies dans [0, 1].")

    weighted = beta * values
    return np.asarray(weighted / (weighted + (1.0 - values)), dtype=np.float64)


def _correct_proba(p: np.ndarray, beta: float) -> np.ndarray:
    """Same correction and validation as ``validation.fold_data.correct_proba``."""

    values = _proba(p)
    if np.ndim(beta) != 0 or not np.isfinite(beta) or not 0 < beta <= 1:
        raise ValueError("beta doit etre fini dans ]0, 1].")
    weighted = beta * values
    return weighted / (weighted + (1.0 - values))


def _logit_flat(probabilities: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probabilities, dtype=np.float64), 1e-12, 1.0 - 1e-12)
    return np.log(clipped / (1.0 - clipped))


def _logit(p: np.ndarray) -> np.ndarray:
    """Column of log-odds, kept for P2's sklearn-based ``Calibrator``."""

    return _logit_flat(p).reshape(-1, 1)


class IdentityCalibrator:
    """No-op calibrator used when calibration data cannot support a fit."""

    def fit(self, probabilities: Any, y: Any) -> IdentityCalibrator:
        return self

    def predict(self, probabilities: Any) -> np.ndarray:
        return np.asarray(probabilities, dtype=np.float64)


class PlattCalibrator:
    """Sigmoid (Platt) calibration fitted on the log-odds of the probability."""

    def __init__(self, coef: float = 1.0, intercept: float = 0.0):
        self.coef = float(coef)
        self.intercept = float(intercept)

    def fit(self, probabilities: Any, y: Any) -> PlattCalibrator:
        from sklearn.linear_model import LogisticRegression

        x = _logit_flat(np.asarray(probabilities, dtype=np.float64)).reshape(-1, 1)
        model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
        model.fit(x, np.asarray(y, dtype=int))
        self.coef = float(model.coef_[0][0])
        self.intercept = float(model.intercept_[0])
        return self

    def predict(self, probabilities: Any) -> np.ndarray:
        z = self.coef * _logit_flat(np.asarray(probabilities, dtype=np.float64))
        z = z + self.intercept
        return 1.0 / (1.0 + np.exp(-z))


def fit_calibrator(
    probabilities: Any,
    y: Any,
    method: str | None = None,
) -> tuple[Any, str, float, float]:
    """Fit isotonic and sigmoid calibrators; keep the lowest Brier score.

    Returns ``(calibrator, method, brier_before, brier_after)``.
    """

    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import brier_score_loss

    p = np.asarray(probabilities, dtype=np.float64)
    target = np.asarray(y, dtype=int)
    if p.size != target.size:
        raise ValueError("probabilities et y doivent avoir la meme taille.")
    if p.size == 0:
        raise ValueError("Aucune donnee de calibration fournie.")

    brier_before = float(brier_score_loss(target, p))

    if np.unique(target).size < 2:
        calibrator = IdentityCalibrator().fit(p, target)
        return calibrator, "identity", brier_before, brier_before

    candidates: dict[str, Any] = {
        "isotonic": IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(p, target),
        "sigmoid": PlattCalibrator().fit(p, target),
    }

    def score(name: str) -> float:
        calibrated = np.clip(candidates[name].predict(p), 0.0, 1.0)
        return float(brier_score_loss(target, calibrated))

    if method is None:
        method = min(candidates, key=score)
    if method not in candidates:
        raise ValueError(f"Methode de calibration inconnue : {method}")

    brier_after = score(method)
    return candidates[method], method, brier_before, brier_after


@dataclass
class Calibrator:
    """P2 inference-time calibrator wrapping a fitted sklearn estimator."""

    method: str
    estimator: object

    def predict(self, p: np.ndarray) -> np.ndarray:
        values = _proba(p)
        output = (
            self.estimator.predict_proba(_logit(values))[:, 1]
            if self.method == "sigmoid"
            else self.estimator.predict(values)
        )
        return _proba(output)


@dataclass
class CalibratedPriorClassifier:
    """P2 final-model adapter: prior correction followed by calibration."""

    classifier: object
    beta: float
    calibrator: Calibrator

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        raw = self.classifier.predict_proba(X)[:, 1]
        fraud = self.calibrator.predict(_correct_proba(raw, self.beta))
        return np.column_stack((1 - fraud, fraud))


def conformal_quantile(scores: Any, alpha: float) -> float:
    """Empirical conformal quantile ``ceil((n + 1) * (1 - alpha)) / n``."""

    values = np.sort(np.asarray(scores, dtype=np.float64))
    n = values.size
    if n == 0:
        raise ValueError("Aucun score de non-conformite fourni.")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha doit etre dans ]0, 1[.")

    rank = math.ceil((n + 1) * (1.0 - alpha))
    if rank > n:
        # The finite sample cannot certify the requested level: stay conservative.
        return 1.0
    return float(np.clip(values[rank - 1], 0.0, 1.0))


def mondrian_thresholds(
    probabilities: Any,
    y: Any,
    alpha: float,
) -> dict[str, float]:
    """Compute class-conditional (Mondrian) non-conformity thresholds.

    ``threshold_legit`` is the largest probability still allowed to include
    class 0; ``threshold_fraud`` is the non-conformity quantile for class 1,
    so class 1 is included when ``p >= 1 - threshold_fraud``.
    """

    p = np.asarray(probabilities, dtype=np.float64)
    target = np.asarray(y, dtype=int)
    if p.size != target.size:
        raise ValueError("probabilities et y doivent avoir la meme taille.")

    legit_scores = p[target == 0]
    fraud_scores = 1.0 - p[target == 1]
    if legit_scores.size == 0 or fraud_scores.size == 0:
        raise ValueError("Le bloc conforme doit contenir les deux classes.")

    return {
        "threshold_legit": conformal_quantile(legit_scores, alpha),
        "threshold_fraud": conformal_quantile(fraud_scores, alpha),
        "n_legit": float(legit_scores.size),
        "n_fraud": float(fraud_scores.size),
    }


def build_prediction_set(
    probability: float,
    threshold_legit: float,
    threshold_fraud: float,
) -> list[int]:
    """Mondrian prediction set for one calibrated probability."""

    prediction_set: list[int] = []
    if probability <= threshold_legit:
        prediction_set.append(0)
    if probability >= (1.0 - threshold_fraud):
        prediction_set.append(1)
    return prediction_set


def decide(prediction_set: list[int]) -> str:
    """Map a conformal set to the shared decision policy (§2.5)."""

    if prediction_set == [0]:
        return "APPROUVER"
    if prediction_set == [1]:
        return "BLOQUER"
    return "REVUE"
