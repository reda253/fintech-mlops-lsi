"""Dimensionality reduction (PCA, t-SNE, UMAP) and facet visualization (§4.11).

Generates 2D projection points for React frontend visualization across 5 facets:
1. class: legitimate (0) vs fraud (1)
2. cluster: unsupervised clusters (K-Means)
3. outlier: anomaly detection (Isolation Forest)
4. error: prediction confusion outcome (TP, FP, FN, TN)
5. uncertainty: conformal / entropy uncertainty level (FAIBLE, ELEVEE)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.manifold import TSNE
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


def compute_pca(X: np.ndarray, n_components: int = 2) -> np.ndarray:
    """Compute 2D PCA projection."""
    pca = PCA(n_components=n_components, random_state=42)
    return pca.fit_transform(X)


def compute_tsne(X: np.ndarray, n_components: int = 2, perplexity: float = 30.0) -> np.ndarray:
    """Compute 2D t-SNE projection."""
    # Ensure perplexity is smaller than sample count
    effective_perplexity = min(perplexity, max(1.0, float(len(X) - 1) / 3.0))
    tsne = TSNE(
        n_components=n_components,
        perplexity=effective_perplexity,
        random_state=42,
        init="pca",
        learning_rate="auto",
    )
    return tsne.fit_transform(X)


def compute_umap(X: np.ndarray, n_components: int = 2, n_neighbors: int = 15) -> np.ndarray:
    """Compute 2D UMAP projection (with fallback if umap-learn is not installed)."""
    try:
        import umap  # type: ignore[import-untyped]

        effective_neighbors = min(n_neighbors, max(2, len(X) - 1))
        reducer = umap.UMAP(
            n_components=n_components,
            n_neighbors=effective_neighbors,
            min_dist=0.1,
            random_state=42,
        )
        return reducer.fit_transform(X)
    except (ImportError, RuntimeError, ValueError, TypeError, AttributeError) as exc:
        logger.warning("umap-learn not available (%s); falling back to PCA approximation for UMAP.", exc)
        return compute_pca(X, n_components=n_components)


def compute_normalized_entropy(probabilities: np.ndarray) -> np.ndarray:
    """Calculate binary Shannon entropy normalized to [0, 1]."""
    p = np.clip(probabilities, 1e-7, 1.0 - 1e-7)
    entropy = -(p * np.log2(p) + (1.0 - p) * np.log2(1.0 - p))
    return np.clip(entropy, 0.0, 1.0)


def prepare_visualization_sample(
    df: pd.DataFrame,
    max_samples: int = 1000,
    random_state: int = 42,
) -> pd.DataFrame:
    """Extract a representative stratified subsample (§4.11).

    Includes all fraudulent transactions and a balanced/weighted sample of legitimate ones.
    """
    if len(df) <= max_samples:
        return df.copy()

    frauds = df[df["is_fraud"] == 1]
    legits = df[df["is_fraud"] == 0]

    remaining_budget = max(max_samples - len(frauds), 50)
    sample_legit_count = min(len(legits), remaining_budget)

    sampled_legits = legits.sample(n=sample_legit_count, random_state=random_state)
    combined = pd.concat([frauds, sampled_legits]).sort_values("trans_date_trans_time" if "trans_date_trans_time" in df.columns else "amount")
    return combined.reset_index(drop=True)


def build_facets(
    x_scaled: np.ndarray,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probabilities: np.ndarray,
) -> dict[str, list[str]]:
    """Compute label strings for the 5 required visualization facets."""
    n_samples = len(y_true)

    # 1. class
    class_labels = ["FRAUD" if val == 1 else "LEGIT" for val in y_true]

    # 2. cluster (K-Means)
    n_clusters = min(4, max(2, n_samples // 10))
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
    clusters = kmeans.fit_predict(x_scaled)
    cluster_labels = [f"Cluster_{c}" for c in clusters]

    # 3. outlier (Isolation Forest)
    iso = IsolationForest(contamination=0.05, random_state=42)
    outliers = iso.fit_predict(x_scaled)
    outlier_labels = ["OUTLIER" if o == -1 else "INLIER" for o in outliers]

    # 4. error (Confusion outcome)
    error_labels = []
    for t, p in zip(y_true, y_pred, strict=False):
        if t == 1 and p == 1:
            error_labels.append("TP")
        elif t == 0 and p == 1:
            error_labels.append("FP")
        elif t == 1 and p == 0:
            error_labels.append("FN")
        else:
            error_labels.append("TN")

    # 5. uncertainty
    entropies = compute_normalized_entropy(probabilities)
    uncertainty_labels = ["ELEVEE" if e >= 0.50 else "FAIBLE" for e in entropies]

    return {
        "class": class_labels,
        "cluster": cluster_labels,
        "outlier": outlier_labels,
        "error": error_labels,
        "uncertainty": uncertainty_labels,
    }


def generate_all_projections(
    df: pd.DataFrame,
    features: list[str],
    y_pred: np.ndarray | None = None,
    probabilities: np.ndarray | None = None,
    model_version: str = "mock",
    max_samples: int = 1000,
) -> dict[str, dict[str, Any]]:
    """Compute 2D coordinates and exportable points for PCA, t-SNE, and UMAP across all 5 views."""
    sub_df = prepare_visualization_sample(df, max_samples=max_samples)
    x_raw = sub_df[features].fillna(0).to_numpy()
    y_true = sub_df["is_fraud"].to_numpy()

    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x_raw)

    n_samples = len(sub_df)
    if probabilities is None:
        # Default placeholder heuristic based on scaled amount if not provided
        probabilities = np.clip(x_scaled[:, 0] * 0.2 + 0.1, 0.01, 0.99)
    else:
        probabilities = probabilities[:n_samples]

    if y_pred is None:
        y_pred = (probabilities >= 0.50).astype(int)
    else:
        y_pred = y_pred[:n_samples]

    # Compute coordinates for each projection technique
    logger.info("Computing 2D projections (PCA, t-SNE, UMAP) for %d samples...", n_samples)
    pca_coords = compute_pca(x_scaled, n_components=2)
    tsne_coords = compute_tsne(x_scaled, n_components=2)
    umap_coords = compute_umap(x_scaled, n_components=2)

    coords_map = {
        "pca": pca_coords,
        "tsne": tsne_coords,
        "umap": umap_coords,
    }

    facets = build_facets(x_scaled, y_true, y_pred, probabilities)

    methods = ["pca", "tsne", "umap"]
    views = ["class", "cluster", "outlier", "error", "uncertainty"]

    result: dict[str, dict[str, Any]] = {}

    for method in methods:
        coords = coords_map[method]
        for view in views:
            key = f"{method}_{view}"
            labels = facets[view]
            points = [
                {
                    "x": round(float(coords[i, 0]), 4),
                    "y": round(float(coords[i, 1]), 4),
                    "label": labels[i],
                    "is_fraud": int(y_true[i]),
                }
                for i in range(n_samples)
            ]
            result[key] = {
                "method": method,
                "view": view,
                "model_version": model_version,
                "warning": "t-SNE/UMAP distances between groups are not meaningful",
                "points": points,
            }

    return result


def export_projections_to_cache(
    projections: dict[str, dict[str, Any]],
    output_dir: Path,
) -> None:
    """Save projection JSON files to disk cache for ml-service serving."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for key, data in projections.items():
        file_path = output_dir / f"{key}.json"
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f)
    logger.info("Saved %d projection files to %s", len(projections), output_dir)
