"""Tests for MLflow custom pyfunc model packaging and RealPredictor."""

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from ml.src.model.fraud_detector import (
    FraudDetectorModel,
    compute_binary_entropy,
    haversine_distance,
)


def test_haversine_distance():
    # Equator distance for 1 degree longitude is ~111.32 km
    dist = haversine_distance(0.0, 0.0, 0.0, 1.0)
    assert 110.0 < dist < 112.0

    # Same location should be 0.0
    assert haversine_distance(40.71, -74.01, 40.71, -74.01) == 0.0


def test_compute_binary_entropy():
    # Maximum uncertainty when p = 0.5
    assert np.isclose(compute_binary_entropy(0.5), 1.0, atol=1e-3)
    # Low uncertainty near 0 or 1
    assert compute_binary_entropy(0.01) < 0.15
    assert compute_binary_entropy(0.99) < 0.15


def test_fraud_detector_feature_extraction():
    model = FraudDetectorModel()
    sample = {
        "amount": 100.0,
        "merch_lat": 40.71,
        "merch_long": -74.01,
        "customer": {
            "lat": 40.65,
            "long": -73.95,
            "city_pop": 50000,
        },
    }
    features = model.extract_features(sample)
    assert features.shape == (1, 3)
    assert np.isfinite(features).all()
    # amount_log = ln(101) ~ 4.615
    assert 4.5 < features[0, 0] < 4.7


def test_fraud_detector_conformal_sets():
    # Train dummy logistic regression
    rng = np.random.default_rng(42)
    X = rng.normal(size=(100, 3))
    y = (X[:, 0] > 0.5).astype(int)

    scaler = StandardScaler().fit(X)
    clf = LogisticRegression().fit(scaler.transform(X), y)

    pyfunc = FraudDetectorModel(
        classifier=clf,
        scaler=scaler,
        threshold_legit=0.40,
        threshold_fraud=0.40,
        alpha=0.05,
    )

    sample_legit = {
        "amount": 5.0,
        "merch_lat": 40.0,
        "merch_long": -74.0,
        "customer": {"lat": 40.0, "long": -74.0, "city_pop": 1000},
    }
    result = pyfunc.predict_one(sample_legit)
    assert "prediction" in result
    assert "fraud_probability" in result
    assert "prediction_set" in result
    assert "uncertainty_level" in result
    assert result["alpha"] == 0.05
