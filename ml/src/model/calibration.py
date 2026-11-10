"""Inference-time probability correction and calibration."""

from dataclasses import dataclass

import numpy as np
from scipy.special import logit


def _proba(p: np.ndarray) -> np.ndarray:
    values = np.asarray(p, dtype=float)
    if (
        values.ndim != 1
        or not np.isfinite(values).all()
        or ((values < 0) | (values > 1)).any()
    ):
        raise ValueError("Probabilités finies dans [0,1] requises")
    return values


def _logit(p: np.ndarray) -> np.ndarray:
    return logit(np.clip(p, 1e-12, 1 - 1e-12)).reshape(-1, 1)


def _correct_proba(p: np.ndarray, beta: float) -> np.ndarray:
    """Même correction et validation que validation.fold_data.correct_proba."""
    values = _proba(p)
    if np.ndim(beta) != 0 or not np.isfinite(beta) or not 0 < beta <= 1:
        raise ValueError("beta doit etre fini dans ]0, 1].")
    weighted = beta * values
    return weighted / (weighted + (1.0 - values))


@dataclass
class Calibrator:
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
    classifier: object
    beta: float
    calibrator: Calibrator

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        raw = self.classifier.predict_proba(X)[:, 1]
        fraud = self.calibrator.predict(_correct_proba(raw, self.beta))
        return np.column_stack((1 - fraud, fraud))
