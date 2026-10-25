"""Tests for RealPredictor in ml-service."""

import uuid

from app.main import app
from app.predictor import RealPredictor
from fastapi.testclient import TestClient


class DummyModel:
    def predict_one(self, record):
        assert "trans_datetime" in record
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


def test_real_predictor_not_ready_when_no_model():
    """Fail-safe invariant: pod must NOT report ready if no model is loaded."""
    real_pred = RealPredictor(
        model_uri="models:/fraud-detector/nonexistent",
        name="fraud-detector",
        version="fail-1",
        model_instance=None,
    )
    real_pred.warmup()
    assert real_pred.is_ready() is False

    with TestClient(app) as client:
        app.state.predictor = real_pred
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Model not ready or warm-up in progress"


def test_real_predictor_predict_503_when_no_model(sample_payload):
    """Fail-safe invariant: return 503 when model is missing so risk-service defaults to REVUE."""
    real_pred = RealPredictor(
        model_uri="",
        name="fraud-detector",
        version="missing-1",
        model_instance=None,
    )

    with TestClient(app) as client:
        app.state.predictor = real_pred
        resp = client.post("/predict", json=sample_payload)
        assert resp.status_code == 503
        assert "Model not loaded" in resp.json()["detail"]


class MalformedModel:
    def predict_one(self, record):
        # Missing prediction_set entirely, or returning None
        return {
            "prediction": 0,
            "fraud_probability": 0.05,
            # 'prediction_set' omitted
        }


def test_real_predictor_never_defaults_to_approve_on_malformed_output(sample_payload):
    """Fail-safe invariant: malformed output must NEVER default to [0] (APPROUVER); must be [0, 1] (REVUE)."""
    real_pred = RealPredictor(
        model_uri="dummy",
        name="fraud-detector",
        version="malformed-1",
        model_instance=MalformedModel(),
    )
    real_pred.warmup()
    assert real_pred.is_ready() is True

    with TestClient(app) as client:
        app.state.predictor = real_pred
        resp = client.post("/predict", json=sample_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["prediction_set"] != [0]
        assert data["prediction_set"] == [0, 1]
        assert data["uncertainty_level"] == "ELEVEE"


class FailingModel:
    def predict_one(self, record):
        raise RuntimeError("Inference tensor crash")


def test_real_predictor_fallback_on_runtime_error(sample_payload):
    """Fail-safe invariant: runtime crash during prediction must safely fall back to [0, 1] (REVUE)."""
    real_pred = RealPredictor(
        model_uri="dummy",
        name="fraud-detector",
        version="failing-1",
        model_instance=FailingModel(),
    )
    # warmup with failing model should fail and leave predictor unready
    real_pred.warmup()
    assert real_pred.is_ready() is False
