"""Custom MLflow pyfunc model wrapper (§5.3).

Encapsulates feature extraction, scaling, calibrated classifier, and Mondrian
conformal prediction thresholds into a single self-contained artifact.
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


class FraudDetectorModel(mlflow.pyfunc.PythonModel):
    """Custom pyfunc model implementing end-to-end inference and conformal sets."""

    def __init__(
        self,
        classifier: Any = None,
        scaler: Any = None,
        feature_names: list[str] | None = None,
        threshold_legit: float = 0.50,
        threshold_fraud: float = 0.50,
        alpha: float = 0.05,
        model_name: str = "fraud-detector",
        model_version: str = "1",
    ):
        self.classifier = classifier
        self.scaler = scaler
        self.feature_names = feature_names or ["amount_log", "distance_km", "city_pop_log"]
        self.threshold_legit = threshold_legit
        self.threshold_fraud = threshold_fraud
        self.alpha = alpha
        self.model_name = model_name
        self.model_version = model_version

    def extract_features(self, row: dict[str, Any] | pd.Series) -> np.ndarray:
        """Extract and derive features from raw transaction and customer fields (§4.3)."""
        amount = float(row.get("amount", 0.0))
        amount_log = np.log1p(max(0.0, amount))

        merch_lat = float(row.get("merch_lat", 0.0))
        merch_long = float(row.get("merch_long", 0.0))

        customer = row.get("customer", {})
        if isinstance(customer, dict):
            cust_lat = float(customer.get("lat", 0.0))
            cust_long = float(customer.get("long", 0.0))
            city_pop = float(customer.get("city_pop", 1000.0))
        else:
            cust_lat = float(row.get("lat", 0.0))
            cust_long = float(row.get("long", 0.0))
            city_pop = float(row.get("city_pop", 1000.0))

        distance_km = haversine_distance(cust_lat, cust_long, merch_lat, merch_long)
        city_pop_log = np.log1p(max(0.0, city_pop))

        feature_vector = np.array([amount_log, distance_km, city_pop_log], dtype=np.float32)
        return feature_vector.reshape(1, -1)

    def predict_one(self, transaction: dict[str, Any]) -> dict[str, Any]:
        """Run single transaction prediction and return complete evaluation bundle."""
        features = self.extract_features(transaction)

        if self.scaler is not None:
            features = self.scaler.transform(features)

        if self.classifier is not None and hasattr(self.classifier, "predict_proba"):
            probs = self.classifier.predict_proba(features)[0]
            fraud_proba = float(probs[1]) if len(probs) > 1 else float(probs[0])
        else:
            # Fallback heuristic based on amount if no classifier fitted yet
            amount = float(transaction.get("amount", 0.0))
            if amount > 500:
                fraud_proba = 0.92
            elif amount >= 200:
                fraud_proba = 0.45
            else:
                fraud_proba = 0.03

        # Point prediction (argmax)
        prediction = 1 if fraud_proba >= 0.50 else 0

        # Mondrian conformal prediction sets (§4.10)
        # Class 0 included if fraud_proba <= threshold_legit
        # Class 1 included if fraud_proba >= (1 - threshold_fraud)
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
