"""Tests for MLflow custom pyfunc model packaging, feature adapter, and parity (D13)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from ml.src.model.fraud_detector import (
    FraudDetectorModel,
    adapt_to_sparkov_record,
    compute_binary_entropy,
    haversine_distance,
)
from ml.src.preprocessing.pipeline import build_preprocessing_pipeline


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


def test_adapt_to_sparkov_record():
    """Verify API request dictionary maps to flat Sparkov format required by preprocessing."""
    api_record = {
        "transaction_id": "11111111-1111-1111-1111-111111111111",
        "trans_datetime": "2026-10-24T23:30:00",
        "amount": 250.0,
        "category": "shopping_net",
        "merch_lat": 40.7130,
        "merch_long": -74.0065,
        "customer": {
            "dob": "1990-01-01",
            "gender": "M",
            "city_pop": 1000000,
            "lat": 40.7128,
            "long": -74.0060,
            "state": "NY",
        },
    }

    adapted = adapt_to_sparkov_record(api_record)
    assert adapted["amt"] == 250.0
    assert adapted["trans_date_trans_time"] == "2026-10-24 23:30:00"
    assert adapted["dob"] == "1990-01-01"
    assert adapted["gender"] == "M"
    assert adapted["category"] == "shopping_net"
    assert adapted["state"] == "NY"
    assert adapted["city_pop"] == 1000000.0
    assert adapted["lat"] == 40.7128
    assert adapted["long"] == -74.0060
    assert adapted["merch_lat"] == 40.7130
    assert adapted["merch_long"] == -74.0065


def test_training_serving_feature_parity():
    """Parity test (D13): feature vector from training path must be identical to serving path.

    Asserts that passing a Sparkov row through build_preprocessing_pipeline() during training
    produces the exact same numerical feature vector as passing the API request through
    the served FraudDetectorModel pyfunc wrapper.
    """
    train_data = pd.DataFrame([
        {
            "trans_date_trans_time": "2026-10-24 23:30:00",
            "dob": "1990-01-01",
            "amt": 250.0,
            "category": "shopping_net",
            "gender": "M",
            "state": "NY",
            "city_pop": 1000000,
            "lat": 40.7128,
            "long": -74.0060,
            "merch_lat": 40.7130,
            "merch_long": -74.0065,
        },
        {
            "trans_date_trans_time": "2026-10-25 10:15:00",
            "dob": "1985-05-15",
            "amt": 45.0,
            "category": "grocery_pos",
            "gender": "F",
            "state": "CA",
            "city_pop": 50000,
            "lat": 34.0522,
            "long": -118.2437,
            "merch_lat": 34.0500,
            "merch_long": -118.2500,
        },
    ])

    pipeline = build_preprocessing_pipeline(scale_numeric=True)
    pipeline.fit(train_data)

    # 1. Training path transformation
    feat_training = pipeline.transform(train_data.iloc[[0]])[0]

    # 2. Serving path transformation via FraudDetectorModel adapter
    api_payload = {
        "transaction_id": "11111111-1111-1111-1111-111111111111",
        "trans_datetime": "2026-10-24T23:30:00",
        "amount": 250.0,
        "category": "shopping_net",
        "merch_lat": 40.7130,
        "merch_long": -74.0065,
        "customer": {
            "dob": "1990-01-01",
            "gender": "M",
            "city_pop": 1000000,
            "lat": 40.7128,
            "long": -74.0060,
            "state": "NY",
        },
    }

    pyfunc_model = FraudDetectorModel(preprocessor=pipeline)
    feat_serving = pyfunc_model.transform_record(api_payload)[0]

    # 3. Assert zero training/serving skew
    assert feat_training.shape == feat_serving.shape
    np.testing.assert_allclose(feat_training, feat_serving, rtol=1e-5, atol=1e-5)


def test_fraud_detector_conformal_sets():
    """Verify FraudDetectorModel applies Mondrian conformal prediction sets."""
    train_data = pd.DataFrame([
        {
            "trans_date_trans_time": "2026-10-24 12:00:00",
            "dob": "1990-01-01",
            "amt": 10.0,
            "category": "shopping_net",
            "gender": "M",
            "state": "NY",
            "city_pop": 100000,
            "lat": 40.0,
            "long": -74.0,
            "merch_lat": 40.0,
            "merch_long": -74.0,
        },
        {
            "trans_date_trans_time": "2026-10-24 23:00:00",
            "dob": "1980-01-01",
            "amt": 900.0,
            "category": "shopping_net",
            "gender": "F",
            "state": "NY",
            "city_pop": 100000,
            "lat": 40.0,
            "long": -74.0,
            "merch_lat": 40.0,
            "merch_long": -74.0,
        },
    ])
    pipeline = build_preprocessing_pipeline(scale_numeric=True)
    X = pipeline.fit_transform(train_data)
    y = np.array([0, 1])

    clf = LogisticRegression().fit(X, y)

    pyfunc = FraudDetectorModel(
        classifier=clf,
        preprocessor=pipeline,
        threshold_legit=0.40,
        threshold_fraud=0.40,
        alpha=0.05,
    )

    sample_api = {
        "trans_datetime": "2026-10-24 12:00:00",
        "amount": 10.0,
        "category": "shopping_net",
        "merch_lat": 40.0,
        "merch_long": -74.0,
        "customer": {
            "dob": "1990-01-01",
            "gender": "M",
            "state": "NY",
            "city_pop": 100000,
            "lat": 40.0,
            "long": -74.0,
        },
    }
    result = pyfunc.predict_one(sample_api)
    assert "prediction" in result
    assert "fraud_probability" in result
    assert "prediction_set" in result
    assert "uncertainty_level" in result
    assert result["alpha"] == 0.05
