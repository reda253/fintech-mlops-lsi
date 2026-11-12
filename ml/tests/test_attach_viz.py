"""T21: attach the dashboard projections to an already registered model version."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ml.scripts.attach_viz import (
    FEATURES,
    METHODS,
    VIEWS,
    attach_projections,
    build_sample,
    ensure_development_source,
    generate_projections,
    list_viz_artifacts,
    projection_keys,
    resolve_run_id,
)
from ml.src.pipeline.steps import generate_synthetic_data


class FakeModel:
    def batch_probabilities(self, frame: pd.DataFrame) -> np.ndarray:
        return np.linspace(0.01, 0.99, len(frame))


class FakeClient:
    def __init__(self, run_id: str = "run-1") -> None:
        self.version = SimpleNamespace(run_id=run_id)
        self.logged: tuple[str, list[str], str] | None = None

    def get_model_version(self, name: str, version: str):
        return self.version

    def get_model_version_by_alias(self, name: str, alias: str):
        return self.version

    def log_artifacts(self, run_id: str, local_dir: str, artifact_path: str) -> None:
        names = sorted(path.name for path in Path(local_dir).glob("*.json"))
        self.logged = (run_id, names, artifact_path)


def _empty_projections() -> dict[str, dict]:
    return {key: {"method": key.split("_")[0], "points": []} for key in projection_keys()}


def test_projection_keys_cover_every_method_and_view():
    keys = projection_keys()
    assert len(keys) == len(METHODS) * len(VIEWS) == 15
    assert len(set(keys)) == 15
    assert "pca_class" in keys and "umap_uncertainty" in keys


def test_final_test_set_is_refused():
    with pytest.raises(ValueError, match="D47"):
        ensure_development_source(Path("data/raw/fraudTest.csv"))
    ensure_development_source(Path("data/raw/fraudTrain.csv"))


def test_build_sample_defaults_to_synthetic_rows():
    frame = build_sample(None, samples=60, seed=7)
    assert len(frame) == 60
    assert {"is_fraud", *FEATURES}.issubset(frame.columns)


def test_build_sample_reads_a_development_extract(tmp_path: Path):
    path = tmp_path / "fraudTrain.csv"
    pd.DataFrame({"amt": [1.0, 2.0]}).to_csv(path, index=False)
    assert len(build_sample(path, samples=10)) == 2


def test_attach_writes_all_projections_under_viz(tmp_path: Path):
    client = FakeClient(run_id="run-42")
    attached = attach_projections(client, "run-42", _empty_projections())
    assert attached == sorted(projection_keys())
    assert client.logged is not None
    run_id, names, artifact_path = client.logged
    assert run_id == "run-42"
    assert artifact_path == "viz"
    assert names == sorted(f"{key}.json" for key in projection_keys())


def test_attach_rejects_an_incomplete_projection_set():
    projections = _empty_projections()
    projections.pop("tsne_error")
    with pytest.raises(ValueError, match="missing"):
        attach_projections(FakeClient(), "run-1", projections)


def test_dry_run_never_writes():
    client = FakeClient()
    assert attach_projections(client, "run-1", _empty_projections(), dry_run=True)
    assert client.logged is None


def test_resolve_run_id_supports_version_and_alias():
    client = FakeClient(run_id="run-9")
    assert resolve_run_id(client, "fraud-detector", "1", None) == "run-9"
    assert resolve_run_id(client, "fraud-detector", None, "challenger") == "run-9"
    empty = FakeClient(run_id="")
    with pytest.raises(ValueError, match="No MLflow run"):
        resolve_run_id(empty, "fraud-detector", "1", None)


def test_list_viz_artifacts_retries_a_stale_listing():
    class FlakyClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def list_artifacts(self, run_id: str, path: str | None = None):
            self.calls += 1
            if self.calls == 1:
                return []
            return [SimpleNamespace(path=f"viz/{key}.json") for key in projection_keys()]

    client = FlakyClient()
    stored = list_viz_artifacts(client, "run-1", attempts=3, delay=0)
    assert client.calls == 2
    assert len(stored) == 15
    assert "pca_class" in stored


def test_generate_projections_uses_model_scores():
    frame = generate_synthetic_data(n_samples=40, random_state=11)
    projections = generate_projections(FakeModel(), frame, model_version="1", max_samples=40)
    assert set(projections) == set(projection_keys())
    for key, payload in projections.items():
        assert payload["method"] == key.split("_")[0]
        assert payload["model_version"] == "1"
        assert 0 < len(payload["points"]) <= 40
