"""Tests for RealPredictor in ml-service."""

import uuid

from app.main import app
from app.predictor import RealPredictor
from fastapi.testclient import TestClient


class DummyModel:
    def predict_one(self, record):
        return {
            "prediction": 1,
            "fraud_probability": 0.94,
            "prediction_set": [1],
            "uncertainty": 0.12,
            "uncertainty_level": "FAIBLE",
            "alpha": 0.05,
            "model_name": "fraud-detector",
            "model_version": "test-v1",
        }


def test_real_predictor_predict_flow(sample_payload):
    real_pred = RealPredictor(
        model_uri="models:/fraud-detector/champion",
        name="fraud-detector",
        version="real-1",
        model_instance=DummyModel(),
    )
    real_pred.warmup()
    assert real_pred.is_ready() is True

    # Temporarily attach RealPredictor to app state
    with TestClient(app) as client:
        app.state.predictor = real_pred

        corr_id = str(uuid.uuid4())
        response = client.post(
            "/predict",
            json=sample_payload,
            headers={"X-Correlation-Id": corr_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["prediction"] == 1
        assert data["fraud_probability"] == 0.94
        assert data["prediction_set"] == [1]
        assert data["uncertainty_level"] == "FAIBLE"
        assert data["model"]["version"] == "real-1"

        # Check performance endpoint
        perf_resp = client.get("/api/v1/ml/performance")
        assert perf_resp.status_code == 200
        perf_data = perf_resp.json()
        assert "benchmark" in perf_data
        assert "statistical_validation" in perf_data
        assert "final_test_evaluation" in perf_data
        assert "fairness_audit" in perf_data

        # Check viz endpoint
        viz_resp = client.get("/api/v1/ml/viz/pca?view=class")
        assert viz_resp.status_code == 200
        viz_data = viz_resp.json()
        assert viz_data["method"] == "pca"
        assert viz_data["view"] == "class"
        assert len(viz_data["points"]) > 0
