"""T21: attach the dashboard projections to an already registered model version."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ml.scripts.attach_viz import (
    ERROR_VIEW_WARNING,
    FEATURES,
    METHODS,
    VIEWS,
    attach_projections,
    build_sample,
    ensure_development_source,
    generate_projections,
    list_viz_artifacts,
    projection_keys,
    refuse_development_extract,
    resolve_run_id,
)
from ml.src.data.load_data import DATE_COLUMN
from ml.src.pipeline.steps import generate_synthetic_data


def _full_source(rows: int = 10) -> pd.DataFrame:
    return pd.DataFrame(
        {
            DATE_COLUMN: [
                pd.Timestamp("2020-01-01") + pd.Timedelta(minutes=index)
                for index in range(rows)
            ],
            "trans_num": [f"tx-{index}" for index in range(rows)],
            "is_fraud": [index % 2 for index in range(rows)],
            **{feature: [1.0] * rows for feature in FEATURES},
        }
    )


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


def test_final_test_set_is_refused_before_any_read(monkeypatch: pytest.MonkeyPatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("read_csv must not run for fraudTest.csv")

    monkeypatch.setattr("ml.scripts.attach_viz.load_development_block", forbidden)
    monkeypatch.setattr(pd, "read_csv", forbidden)

    with pytest.raises(ValueError, match="D47"):
        build_sample(Path("data/raw/fraudTest.csv"), samples=10)


def test_development_extract_is_refused():
    with pytest.raises(ValueError, match="pre-filtered extract"):
        refuse_development_extract(Path("data/raw/development_extract.csv"))


def test_build_sample_refuses_a_renamed_source(tmp_path: Path):
    path = tmp_path / "calibration.csv"
    _full_source(rows=10).to_csv(path, index=False)

    with pytest.raises(ValueError, match="Unverifiable development source"):
        build_sample(path, samples=10)


def test_build_sample_defaults_to_synthetic_rows():
    frame = build_sample(None, samples=60, seed=7)
    assert len(frame) == 60
    assert {"is_fraud", *FEATURES}.issubset(frame.columns)


def test_build_sample_keeps_only_the_development_zone(tmp_path: Path):
    path = tmp_path / "fraudTrain.csv"
    _full_source(rows=10).to_csv(path, index=False)

    frame = build_sample(path, samples=10)

    assert sorted(frame["trans_num"]) == sorted(f"tx-{index}" for index in range(7))


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


def test_generate_projections_labels_the_error_view():
    frame = generate_synthetic_data(n_samples=40, random_state=11)
    projections = generate_projections(FakeModel(), frame, model_version="1", max_samples=40)
    for key, payload in projections.items():
        if key.endswith("_error"):
            assert payload["warning"] == ERROR_VIEW_WARNING
        else:
            assert payload["warning"] != ERROR_VIEW_WARNING
