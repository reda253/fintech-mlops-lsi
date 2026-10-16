"""Tests for /metrics Prometheus endpoint (§5.8)."""


def test_metrics_endpoint(client, sample_payload):
    # Trigger one prediction and one validation error to populate metrics
    client.post("/predict", json=sample_payload)
    bad_payload = dict(sample_payload, amount=-50)
    client.post("/predict", json=bad_payload)

    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text

    assert "http_requests_total" in text
    assert "ml_inference_duration_seconds" in text
    assert "ml_predictions_total" in text
    assert "ml_fraud_probability" in text
    assert "ml_uncertainty" in text
    assert "ml_input_validation_errors_total" in text
    assert "ml_model_info" in text
    assert "ml_model_loaded_timestamp_seconds" in text
