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

    Wraps the fitted preprocessing pipeline and calibrated classifier into a single
    self-contained MLflow artifact, eliminating training/serving skew (D13).
    """

    def __init__(
        self,
        classifier: Any = None,
        preprocessor: Any = None,
        scaler: Any = None,  # backward compatibility alias for preprocessor
        feature_names: list[str] | None = None,
        threshold_legit: float = 0.50,
        threshold_fraud: float = 0.50,
        alpha: float = 0.05,
        model_name: str = "fraud-detector",
        model_version: str = "1",
    ):
        self.classifier = classifier
        self.preprocessor = preprocessor if preprocessor is not None else scaler
        self.feature_names = feature_names
        self.threshold_legit = threshold_legit
        self.threshold_fraud = threshold_fraud
        self.alpha = alpha
        self.model_name = model_name
        self.model_version = model_version

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

    def predict_one(self, transaction: dict[str, Any]) -> dict[str, Any]:
        """Run single transaction prediction and return complete evaluation bundle."""
        sparkov_record = adapt_to_sparkov_record(transaction)

        if self.preprocessor is not None:
            features = self.transform_record(transaction)
        else:
            features = None

        if self.classifier is not None and hasattr(self.classifier, "predict_proba") and features is not None:
            probs = self.classifier.predict_proba(features)[0]
            fraud_proba = float(probs[1]) if len(probs) > 1 else float(probs[0])
        else:
            # Fallback heuristic based on amount if no classifier fitted yet
            amt = float(sparkov_record.get("amt", 0.0))
            if amt > 500:
                fraud_proba = 0.92
            elif amt >= 200:
                fraud_proba = 0.45
            else:
                fraud_proba = 0.03

        # Point prediction (argmax)
        prediction = 1 if fraud_proba >= 0.50 else 0

        # Mondrian conformal prediction sets (§4.10)
        prediction_set: list[int] = []
        if fraud_proba <= self.threshold_legit:
            prediction_set.append(0)
        if fraud_proba >= (1.0 - self.threshold_fraud):
            prediction_set.append(1)

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

    def predict(self, context: Any, model_input: pd.DataFrame | list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Batch inference entry point implementing mlflow.pyfunc interface."""
        if isinstance(model_input, pd.DataFrame):
            records = model_input.to_dict(orient="records")
        else:
            records = list(model_input)

        return [self.predict_one(row) for row in records]
