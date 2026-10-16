"""Tests for dimensionality reduction and multi-view projections."""

import json
import tempfile
from pathlib import Path

import numpy as np

from ml.src.pipeline.steps import generate_synthetic_data
from ml.src.visualization.projections import (
    compute_pca,
    compute_tsne,
    compute_umap,
    export_projections_to_cache,
    generate_all_projections,
)


def test_projections_shapes():
    rng = np.random.default_rng(42)
    X = rng.normal(size=(50, 4))

    pca = compute_pca(X, n_components=2)
    assert pca.shape == (50, 2)
    assert np.isfinite(pca).all()

    tsne = compute_tsne(X, n_components=2, perplexity=10.0)
    assert tsne.shape == (50, 2)
    assert np.isfinite(tsne).all()

    umap = compute_umap(X, n_components=2, n_neighbors=5)
    assert umap.shape == (50, 2)
    assert np.isfinite(umap).all()


def test_generate_all_projections_facets():
    df = generate_synthetic_data(n_samples=100)
    features = ["amount", "lat", "long", "city_pop"]

    projections = generate_all_projections(
        df=df,
        features=features,
        model_version="test-v1",
        max_samples=100,
    )

    # 3 methods x 5 views = 15 combinations
    assert len(projections) == 15
    assert "pca_class" in projections
    assert "tsne_cluster" in projections
    assert "umap_uncertainty" in projections

    sample = projections["pca_class"]
    assert sample["method"] == "pca"
    assert sample["view"] == "class"
    assert sample["model_version"] == "test-v1"
    assert len(sample["points"]) == 100
    point = sample["points"][0]
    assert "x" in point
    assert "y" in point
    assert "label" in point
    assert point["is_fraud"] in [0, 1]


def test_export_projections_to_cache():
    df = generate_synthetic_data(n_samples=30)
    features = ["amount", "lat", "long", "city_pop"]
    projections = generate_all_projections(df=df, features=features, max_samples=30)

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir)
        export_projections_to_cache(projections, out_path)

        exported_files = list(out_path.glob("*.json"))
        assert len(exported_files) == 15

        with (out_path / "pca_class.json").open("r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["method"] == "pca"
            assert len(data["points"]) == 30
