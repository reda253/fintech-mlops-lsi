"""Tests for Pydantic input validation on /predict."""


def test_validation_rejects_negative_amount(client, sample_payload):
    sample_payload["amount"] = -10.0
    response = client.post("/predict", json=sample_payload)
    assert response.status_code == 422


def test_validation_rejects_zero_amount(client, sample_payload):
    sample_payload["amount"] = 0.0
    response = client.post("/predict", json=sample_payload)
    assert response.status_code == 422


def test_validation_rejects_unknown_category(client, sample_payload):
    sample_payload["category"] = "crypto_scam"
    response = client.post("/predict", json=sample_payload)
    assert response.status_code == 422


def test_validation_rejects_invalid_latitude(client, sample_payload):
    sample_payload["merch_lat"] = 95.0
    response = client.post("/predict", json=sample_payload)
    assert response.status_code == 422


def test_validation_rejects_invalid_longitude(client, sample_payload):
    sample_payload["merch_long"] = -190.0
    response = client.post("/predict", json=sample_payload)
    assert response.status_code == 422


def test_validation_rejects_missing_customer(client, sample_payload):
    del sample_payload["customer"]
    response = client.post("/predict", json=sample_payload)
    assert response.status_code == 422


def test_validation_rejects_invalid_gender(client, sample_payload):
    sample_payload["customer"]["gender"] = "X"
    response = client.post("/predict", json=sample_payload)
    assert response.status_code == 422
