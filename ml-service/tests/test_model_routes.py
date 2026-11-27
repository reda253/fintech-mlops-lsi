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


def test_run_metrics_fall_back_to_the_evaluation_child():
    from app.routes.model import _run_evaluation_metrics

    class FakeClient:
        def get_run(self, run_id):
            return {
                "parent": SimpleNamespace(
                    info=SimpleNamespace(experiment_id="2"),
                    data=SimpleNamespace(metrics={}, tags={}),
                ),
                "evaluate": SimpleNamespace(
                    info=SimpleNamespace(experiment_id="2", run_id="evaluate"),
                    data=SimpleNamespace(
                        metrics={"pr_auc": 0.8755, "review_rate": 0.0069},
                        tags={"mlflow.runName": "5_evaluate"},
                    ),
                ),
            }[run_id]

        def search_runs(self, experiment_ids, filter_string=None):
            return [self.get_run("evaluate")]

    metrics, tags, run_id = _run_evaluation_metrics(FakeClient(), "parent")

    assert metrics["pr_auc"] == 0.8755
    assert run_id == "evaluate"
    assert tags["mlflow.runName"] == "5_evaluate"


def test_performance_uses_the_version_evaluation_run(monkeypatch):
    import mlflow.tracking
    from app.routes import model as model_routes

    seen = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_run(self, run_id):
            seen["run_id"] = run_id
            return SimpleNamespace(
                info=SimpleNamespace(experiment_id="2"),
                data=SimpleNamespace(
                    metrics={"pr_auc": 0.8755, "review_rate": 0.0069},
                    tags={"decision_id": "D48"},
                ),
            )

    monkeypatch.setattr(mlflow.tracking, "MlflowClient", FakeClient)
    monkeypatch.setattr(
        model_routes,
        "_model_version",
        lambda info: SimpleNamespace(
            run_id="registry-run", tags={"evaluation_run_id": "d48-run"}
        ),
    )

    info = SimpleNamespace(name="fraud-detector", version="1", alpha=0.02)
    measured = model_routes._performance_from_registry(info)

    assert seen["run_id"] == "d48-run"
    assert measured is not None
    assert measured["final_test_evaluation"]["pr_auc"]["value"] == 0.8755


def test_performance_reports_the_published_interval(monkeypatch):
    import mlflow.tracking
    from app.routes import model as model_routes

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_run(self, run_id):
            return SimpleNamespace(
                info=SimpleNamespace(experiment_id="2"),
                data=SimpleNamespace(
                    metrics={
                        "pr_auc": 0.8755,
                        "pr_auc_ci95_low": 0.8638,
                        "pr_auc_ci95_high": 0.8867,
                        "review_rate": 0.0069,
                        "review_rate_ci95_low": 0.00668,
                        "review_rate_ci95_high": 0.00712,
                        "coverage_fraud": 0.9613,
                        "coverage_fraud_ci95_low": 0.9530,
                        "coverage_fraud_ci95_high": 0.9692,
                        "n_transactions": 555719,
                        "fraud_count": 2145,
                    },
                    tags={},
                ),
            )

    monkeypatch.setattr(mlflow.tracking, "MlflowClient", FakeClient)
    monkeypatch.setattr(
        model_routes, "_model_version", lambda info: SimpleNamespace(run_id="r")
    )

    info = SimpleNamespace(name="fraud-detector", version="1", alpha=0.02)
    measured = model_routes._performance_from_registry(info)

    block = measured["final_test_evaluation"]
    assert block["pr_auc"]["ci_95"] == [0.8638, 0.8867]
    assert block["conformal_metrics"]["review_rate_ci_95"] == [0.00668, 0.00712]
    assert block["conformal_metrics"]["coverage_fraud_ci_95"] == [0.9530, 0.9692]
    assert block["n_test"] == 555719
    assert block["n_test_fraud"] == 2145
    assert block["roc_auc"]["ci_95"] is None


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
