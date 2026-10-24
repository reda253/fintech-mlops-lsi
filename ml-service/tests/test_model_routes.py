"""Tests for model metadata, performance, and visualization routes."""


def test_get_model_info(client):
    response = client.get("/api/v1/ml/model")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "fraud-detector"
    assert data["version"] == "mock"
    assert data["mode"] == "mock"
    assert data["alpha"] == 0.05


def test_get_model_performance(client):
    response = client.get("/api/v1/ml/performance")
    assert response.status_code == 200
    data = response.json()
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
