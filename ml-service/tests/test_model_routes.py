"""Tests for model metadata, performance, and visualization routes."""

from types import SimpleNamespace


def test_get_model_info(client):
    response = client.get("/api/v1/ml/model")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "fraud-detector"
    assert data["version"] == "mock"
    assert data["mode"] == "mock"
    assert data["alpha"] == 0.02


def test_get_model_performance(client):
    response = client.get("/api/v1/ml/performance")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "demo"
    assert data["source"] == "demo"
    assert "benchmark" in data
    assert "fairness_audit" in data

    # Spec §4.5: exactly these five models are benchmarked.
    names = {model["name"] for model in data["benchmark"]["models"]}
    assert names == {
        "LogisticRegression",
        "RandomForest",
        "XGBoost",
        "SVM",
        "MultiLayerPerceptron",
    }
    comparisons = {
        item["comparison"]
        for item in data["statistical_validation"]["holm_bonferroni_correction"]
    }
    assert comparisons == {f"XGBoost vs {name}" for name in names - {"XGBoost"}}


def test_run_metrics_follow_the_pipeline_parent():
    from app.routes.model import _run_evaluation_metrics

    class FakeClient:
        def __init__(self):
            self.runs = {
                "child": SimpleNamespace(
                    data=SimpleNamespace(metrics={}, tags={"mlflow.parentRunId": "parent"})
                ),
                "parent": SimpleNamespace(
                    data=SimpleNamespace(
                        metrics={"pr_auc": 0.81, "review_rate": 0.015},
                        tags={"git_commit": "abc"},
                    )
                ),
            }

        def get_run(self, run_id):
            return self.runs[run_id]

    metrics, tags, run_id = _run_evaluation_metrics(FakeClient(), "child")

    assert metrics["pr_auc"] == 0.81
    assert tags["git_commit"] == "abc"
    assert run_id == "parent"


def test_performance_from_registry_reads_served_version(monkeypatch):
    import mlflow.tracking
    from app.routes import model as model_routes

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_run(self, run_id):
            return SimpleNamespace(
                data=SimpleNamespace(
                    metrics={
                        "pr_auc": 0.77,
                        "roc_auc": 0.95,
                        "brier_score": 0.02,
                        "conformal_coverage_legit": 0.98,
                        "conformal_coverage_fraud": 0.97,
                        "review_rate": 0.012,
                        "automation_rate": 0.988,
                        "alpha": 0.02,
                        "latency_p95_sec": 0.009,
                    },
                    tags={"git_commit": "deadbeef"},
                )
            )

    monkeypatch.setattr(mlflow.tracking, "MlflowClient", FakeClient)
    monkeypatch.setattr(
        model_routes,
        "_model_version",
        lambda info: SimpleNamespace(run_id="run-1"),
    )

    info = SimpleNamespace(name="fraud-detector", version="3", alpha=0.02)
    measured = model_routes._performance_from_registry(info)

    assert measured is not None
    assert measured["run_id"] == "run-1"
    assert measured["final_test_evaluation"]["pr_auc"]["value"] == 0.77
    assert measured["final_test_evaluation"]["conformal_metrics"]["coverage_fraud"] == 0.97
    assert measured["tags"]["git_commit"] == "deadbeef"


def test_get_visualizations_valid(client):
    response = client.get("/api/v1/ml/viz/pca?view=class")
    assert response.status_code == 200
    data = response.json()
    assert data["method"] == "pca"
    assert data["view"] == "class"
    assert "warning" in data


def test_get_visualizations_invalid_method(client):
    response = client.get("/api/v1/ml/viz/unknown_method?view=class")
    assert response.status_code == 422
