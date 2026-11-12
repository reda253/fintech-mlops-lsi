"""T21f: projections are downloaded from the registered model version on cache miss."""

from __future__ import annotations

import json
from types import SimpleNamespace

import mlflow
from app.cache import ModelCacheManager
from app.routes import model as model_routes
from app.schemas import ModelInfo


class _RealPredictor:
    def get_model_info(self) -> ModelInfo:
        return ModelInfo(name="fraud-detector", version="1", mode="real", alpha=0.02)


class _MockPredictor:
    def get_model_info(self) -> ModelInfo:
        return ModelInfo(name="fraud-detector", version="mock", mode="mock")


def test_viz_cache_miss_downloads_from_model_version(monkeypatch, tmp_path):
    payload = {
        "method": "pca",
        "view": "class",
        "model_version": "1",
        "warning": "test",
        "points": [{"x": 0.1, "y": -0.2, "label": "LEGIT", "is_fraud": 0}],
    }
    artifact = tmp_path / "downloaded" / "viz" / "pca_class.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    class _Client:
        def get_model_version(self, name, version):
            assert (name, version) == ("fraud-detector", "1")
            return SimpleNamespace(run_id="run-1")

    monkeypatch.setattr(model_routes, "cache_manager", ModelCacheManager(tmp_path / "cache"))
    monkeypatch.setattr(mlflow.tracking, "MlflowClient", lambda: _Client())
    monkeypatch.setattr(
        mlflow.artifacts,
        "download_artifacts",
        lambda **kwargs: str(artifact),
    )

    data = model_routes._download_viz_from_registry(_RealPredictor(), "pca", "class")
    assert data == payload
    cached = model_routes.cache_manager.get_viz_path("pca", "class", "1")
    assert cached.is_file()
    assert json.loads(cached.read_text(encoding="utf-8"))["model_version"] == "1"


def test_viz_download_is_skipped_in_mock_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(model_routes, "cache_manager", ModelCacheManager(tmp_path / "cache"))
    assert model_routes._download_viz_from_registry(_MockPredictor(), "pca", "class") is None


def test_viz_cache_path_is_version_scoped(tmp_path):
    manager = ModelCacheManager(tmp_path)
    assert manager.get_viz_path("pca", "class", "1").name == "pca_class_v1.json"
    assert manager.get_viz_path("pca", "class", "2").name == "pca_class_v2.json"
    assert manager.get_viz_path("pca", "class").name == "pca_class.json"
