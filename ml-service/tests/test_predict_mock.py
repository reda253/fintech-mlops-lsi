"""Tests for mock prediction rules (§5.7, D12)."""

import uuid


def test_predict_approved_under_200(client, sample_payload):
    sample_payload["amount"] = 85.50
    response = client.post("/predict", json=sample_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["transaction_id"] == sample_payload["transaction_id"]
    assert data["prediction"] == 0
    assert data["prediction_set"] == [0]
    assert data["uncertainty_level"] == "FAIBLE"
    assert data["fraud_probability"] < 0.10
    assert data["model"]["name"] == "fraud-detector"
    assert data["inference_ms"] >= 0


def test_predict_review_between_200_and_500(client, sample_payload):
    sample_payload["amount"] = 350.00
    response = client.post("/predict", json=sample_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["prediction_set"] == [0, 1]
    assert data["uncertainty_level"] == "ELEVEE"
    assert data["fraud_probability"] == 0.45


def test_predict_blocked_over_500(client, sample_payload):
    sample_payload["amount"] = 920.00
    response = client.post("/predict", json=sample_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["prediction"] == 1
    assert data["prediction_set"] == [1]
    assert data["uncertainty_level"] == "FAIBLE"
    assert data["fraud_probability"] > 0.90


def test_predict_boundary_exact_200(client, sample_payload):
    sample_payload["amount"] = 200.00
    response = client.post("/predict", json=sample_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["prediction_set"] == [0, 1]


def test_predict_boundary_exact_500(client, sample_payload):
    sample_payload["amount"] = 500.00
    response = client.post("/predict", json=sample_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["prediction_set"] == [0, 1]


def test_predict_correlation_id_propagation(client, sample_payload):
    corr_id = str(uuid.uuid4())
    response = client.post(
        "/predict",
        json=sample_payload,
        headers={"X-Correlation-Id": corr_id},
    )

    assert response.status_code == 200
    assert response.headers.get("X-Correlation-Id") == corr_id
