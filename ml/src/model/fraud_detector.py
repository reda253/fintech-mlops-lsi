"""Custom MLflow pyfunc model wrapper (§5.3, D13).

Wraps the fitted preprocessing pipeline (from ml.src.preprocessing.pipeline) and
calibrated classifier into a single self-contained artifact, eliminating
training/serving skew by ensuring features are computed identically in both paths.
"""

from __future__ import annotations

import logging
from typing import Any

import mlflow.pyfunc
import numpy as np
import pandas as pd

try:  # Package path used by the training pipeline and the tests.
    from ml.src.model.calibration import (
        build_prediction_set,
        correct_proba,
    )
except ImportError:  # pragma: no cover - fallback when ml/src is on PYTHONPATH
    from model.calibration import (  # type: ignore[no-redef]
        build_prediction_set,
        correct_proba,
    )

logger = logging.getLogger(__name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometers."""
    r = 6371.0  # Earth radius in kilometers
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    delta_phi = np.radians(lat2 - lat1)
    delta_lambda = np.radians(lon2 - lon1)

    a = (
        np.sin(delta_phi / 2.0) ** 2
        + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return float(r * c)


def compute_binary_entropy(p: float) -> float:
    """Calculate normalized Shannon entropy in [0, 1]."""
    p_clipped = min(max(p, 1e-7), 1.0 - 1e-7)
    entropy = -(p_clipped * np.log2(p_clipped) + (1.0 - p_clipped) * np.log2(1.0 - p_clipped))
    return float(np.clip(entropy, 0.0, 1.0))


def adapt_to_sparkov_record(record: dict[str, Any]) -> dict[str, Any]:
    """Adapt API request dictionary or Sparkov row to canonical Sparkov format (§4.3, D13).

    Maps:
    - amount -> amt
    - trans_datetime (ISO string or datetime) -> trans_date_trans_time (%Y-%m-%d %H:%M:%S)
    - customer (nested dict) -> flattens dob, gender, state, city_pop, lat, long
    """
    sparkov: dict[str, Any] = {}

    # 1. Amount: 'amt' (Sparkov) or 'amount' (API)
    if "amt" in record:
        sparkov["amt"] = float(record["amt"])
    elif "amount" in record:
        sparkov["amt"] = float(record["amount"])
    else:
        raise ValueError("Missing amount field: expected 'amt' or 'amount'")

    # 2. Transaction timestamp: 'trans_date_trans_time' (Sparkov) or 'trans_datetime' (API)
    raw_time = record.get("trans_date_trans_time") or record.get("trans_datetime")
    if raw_time is None:
        raise ValueError("Missing timestamp field: expected 'trans_date_trans_time' or 'trans_datetime'")

    if hasattr(raw_time, "strftime"):
        sparkov["trans_date_trans_time"] = raw_time.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(raw_time, str):
        clean_time = raw_time.replace("T", " ")
        clean_time = clean_time.split(".")[0].split("+")[0].split("Z")[0]
        sparkov["trans_date_trans_time"] = clean_time
    else:
        sparkov["trans_date_trans_time"] = str(raw_time)

    # 3. Direct transaction categorical and geographic coordinates
    sparkov["category"] = str(record.get("category", ""))
    sparkov["merch_lat"] = float(record.get("merch_lat", 0.0))
    sparkov["merch_long"] = float(record.get("merch_long", 0.0))

    # 4. Customer profile (nested or flat)
    customer = record.get("customer")
    if isinstance(customer, dict):
        dob_val = customer.get("dob")
        if hasattr(dob_val, "strftime"):
            sparkov["dob"] = dob_val.strftime("%Y-%m-%d")
        elif isinstance(dob_val, str):
            sparkov["dob"] = dob_val.split("T")[0].split(" ")[0]
        else:
            sparkov["dob"] = str(dob_val)

        sparkov["gender"] = str(customer.get("gender", ""))
        sparkov["state"] = str(customer.get("state", ""))
        sparkov["city_pop"] = float(customer.get("city_pop", 0.0))
        sparkov["lat"] = float(customer.get("lat", 0.0))
        sparkov["long"] = float(customer.get("long", 0.0))
    else:
        dob_val = record.get("dob")
        if hasattr(dob_val, "strftime"):
            sparkov["dob"] = dob_val.strftime("%Y-%m-%d")
        elif isinstance(dob_val, str):
            sparkov["dob"] = dob_val.split("T")[0].split(" ")[0]
        else:
            sparkov["dob"] = str(dob_val)

        sparkov["gender"] = str(record.get("gender", ""))
        sparkov["state"] = str(record.get("state", ""))
        sparkov["city_pop"] = float(record.get("city_pop", 0.0))
        sparkov["lat"] = float(record.get("lat", 0.0))
        sparkov["long"] = float(record.get("long", 0.0))

    return sparkov


class FraudDetectorModel(mlflow.pyfunc.PythonModel):
    """Custom pyfunc model implementing end-to-end inference and conformal sets (§5.3).

    Pipeline order (D13, §4.10, §5.3)::

        preprocessor -> classifier -> prior correction (beta) -> calibrator
        -> Mondrian prediction set

    Wraps the fitted preprocessing pipeline, calibrated classifier and
    class-conditional conformal thresholds into a single self-contained
    MLflow artifact, eliminating training/serving skew.
    """

    def __init__(
        self,
        classifier: Any = None,
        preprocessor: Any = None,
        scaler: Any = None,  # backward compatibility alias for preprocessor
        calibrator: Any = None,
        calibration_method: str | None = None,
        beta: float | None = None,
        feature_names: list[str] | None = None,
        threshold_legit: float = 0.50,
        threshold_fraud: float = 0.50,
        alpha: float = 0.02,
        model_name: str = "fraud-detector",
        model_version: str = "1",
        algorithm: str = "xgboost-calibrated",
        trained_at: str | None = None,
        git_commit: str = "unknown",
        data_sha256: str = "unknown",
    ):
        self.classifier = classifier
        self.preprocessor = preprocessor if preprocessor is not None else scaler
        self.calibrator = calibrator
        self.calibration_method = calibration_method
        self.beta = beta
        self.feature_names = feature_names
        self.threshold_legit = float(threshold_legit)
        self.threshold_fraud = float(threshold_fraud)
        self.alpha = float(alpha)
        self.model_name = model_name
        self.model_version = str(model_version)
        self.algorithm = algorithm
        self.trained_at = trained_at
        self.git_commit = git_commit
        self.data_sha256 = data_sha256

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Backfill attributes missing from pre-T21 pickles.

        P2's D44 joblib stores the calibrator and beta inside
        ``classifier=CalibratedPriorClassifier``; those artifacts predate the
        flat ``calibrator``/``beta``/``calibration_method`` attributes. They
        stay ``None`` here so the nested classifier is not calibrated twice.
        """

        defaults: dict[str, Any] = {
            "preprocessor": None,
            "calibrator": None,
            "calibration_method": None,
            "beta": None,
            "feature_names": None,
            "threshold_legit": 0.50,
            "threshold_fraud": 0.50,
            "alpha": 0.02,
            "model_name": "fraud-detector",
            "model_version": "1",
            "algorithm": "xgboost-calibrated",
            "trained_at": None,
            "git_commit": "unknown",
            "data_sha256": "unknown",
        }
        for key, value in defaults.items():
            state.setdefault(key, value)

        nested_calibrator = getattr(state.get("classifier"), "calibrator", None)
        if state["calibration_method"] is None and nested_calibrator is not None:
            state["calibration_method"] = getattr(
                nested_calibrator, "method", type(nested_calibrator).__name__
            )

        self.__dict__.update(state)

    def transform_record(self, record: dict[str, Any]) -> np.ndarray:
        """Adapt API record to Sparkov format and transform through the fitted preprocessing pipeline."""
        sparkov_record = adapt_to_sparkov_record(record)
        if self.preprocessor is not None:
            if hasattr(self.preprocessor, "transform_one"):
                features = self.preprocessor.transform_one(sparkov_record)
                return features.reshape(1, -1)
            if hasattr(self.preprocessor, "transform"):
                df = pd.DataFrame([sparkov_record])
                return np.asarray(self.preprocessor.transform(df), dtype=np.float32)
            raise TypeError("Preprocessor must implement transform_one() or transform()")
        return np.zeros((1, 1), dtype=np.float32)

    def calibrated_probability(self, transaction: dict[str, Any]) -> float:
        """Return the calibrated fraud probability for one raw transaction."""

        sparkov_record = adapt_to_sparkov_record(transaction)

        if self.classifier is None:
            # Fallback heuristic only used by the legacy smoke wrapper.
            amt = float(sparkov_record.get("amt", 0.0))
            if amt > 500:
                return 0.92
            if amt >= 200:
                return 0.45
            return 0.03

        if self.preprocessor is None:
            # Single-object artifacts may already be a full raw-input pipeline.
            features = pd.DataFrame([sparkov_record])
        else:
            features = self.transform_record(transaction)
        probabilities = np.asarray(self.classifier.predict_proba(features), dtype=np.float64)[0]
        fraud_proba = float(probabilities[1]) if probabilities.size > 1 else float(probabilities[0])

        if self.beta is not None:
            fraud_proba = float(correct_proba(np.array([fraud_proba]), float(self.beta))[0])
        if self.calibrator is not None:
            fraud_proba = float(np.asarray(self.calibrator.predict(np.array([fraud_proba])))[0])

        return float(np.clip(fraud_proba, 0.0, 1.0))

    def batch_probabilities(self, model_input: pd.DataFrame) -> np.ndarray:
        """Vectorised calibrated probabilities on raw Sparkov rows.

        Used by offline evaluation and visualization. ``predict_one`` remains the
        serving path and both share the same preprocessing pipeline (D13).
        """

        if self.classifier is None:
            raise ValueError("Le modele doit contenir un classifier.")

        frame = model_input.copy()
        if "customer" in frame.columns and "amt" not in frame.columns:
            frame = pd.DataFrame(
                [adapt_to_sparkov_record(record) for record in frame.to_dict(orient="records")]
            )

        features = frame if self.preprocessor is None else self.preprocessor.transform(frame)
        probabilities = np.asarray(self.classifier.predict_proba(features), dtype=np.float64)[:, 1]
        if self.beta is not None:
            probabilities = correct_proba(probabilities, float(self.beta))
        if self.calibrator is not None:
            probabilities = np.asarray(self.calibrator.predict(probabilities), dtype=np.float64)
        return np.clip(probabilities, 0.0, 1.0)

    def predict_one(self, transaction: dict[str, Any]) -> dict[str, Any]:
        """Run single transaction prediction and return complete evaluation bundle."""
        fraud_proba = self.calibrated_probability(transaction)

        # Point prediction (argmax at 0.5 on the calibrated probability)
        prediction = 1 if fraud_proba >= 0.50 else 0

        # Mondrian conformal prediction sets (§4.10)
        prediction_set = build_prediction_set(
            fraud_proba,
            self.threshold_legit,
            self.threshold_fraud,
        )

        uncertainty = compute_binary_entropy(fraud_proba)
        uncertainty_level = "FAIBLE" if len(prediction_set) == 1 else "ELEVEE"

        return {
            "prediction": prediction,
            "fraud_probability": round(fraud_proba, 4),
            "prediction_set": prediction_set,
            "uncertainty": round(uncertainty, 4),
            "uncertainty_level": uncertainty_level,
            "alpha": self.alpha,
            "model_name": self.model_name,
            "model_version": self.model_version,
        }

    def predict(
        self,
        context: Any,
        model_input: pd.DataFrame,
    ) -> pd.DataFrame:
        """Batch inference entry point implementing the mlflow.pyfunc interface."""
        if isinstance(model_input, pd.DataFrame):
            records = model_input.to_dict(orient="records")
        else:
            records = list(model_input)

        rows = [self.predict_one(row) for row in records]
        columns = [
            "prediction",
            "fraud_probability",
            "prediction_set",
            "uncertainty",
            "uncertainty_level",
            "alpha",
            "model_name",
            "model_version",
        ]
        return pd.DataFrame(rows, columns=columns)

    def to_metadata(self) -> dict[str, Any]:
        """JSON-serialisable metadata stored with the registered model version."""

        return {
            "alpha": float(self.alpha),
            "beta": None if self.beta is None else float(self.beta),
            "calibration": self.calibration_method or "none",
            "threshold_legit": float(self.threshold_legit),
            "threshold_fraud": float(self.threshold_fraud),
            "algorithm": self.algorithm,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "trained_at": self.trained_at or "unknown",
            "git_commit": self.git_commit,
            "data_sha256": self.data_sha256,
        }
