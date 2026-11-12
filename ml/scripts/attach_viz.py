"""Attach PCA/t-SNE/UMAP projections to an existing registry model version.

The pipeline logs ``viz/*.json`` when it packages a model, but models imported
from P2's handoff are registered without them, so ``/api/v1/ml/viz`` falls back
to demo points. This script rebuilds the 15 projections (3 methods x 5 views)
from the served version and logs them under ``viz/`` on that version's run.

It never reads ``fraudTest.csv``: the official final test stays reserved for the
D47 measurement. Use synthetic rows, or pass the **full** source with
``--data-path``: only its development zone (earliest 70 % by transaction date) is
loaded, and the calibration rows are never parsed. A pre-filtered extract cannot
prove its provenance, so ``--development-extract`` is refused.

``umap-learn`` is not part of the locked environment, so UMAP uses the existing
PCA fallback in ``ml.src.visualization.projections``; PCA and UMAP therefore
share coordinates until the dependency is added.

Usage:
    python -m ml.scripts.attach_viz \
        --model-name fraud-detector \
        --version 1 \
        --tracking-uri http://localhost:5001 \
        --samples 500
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
for _path in (ROOT_DIR, SRC_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from ml.src.data.load_data import load_development_block
from ml.src.visualization.projections import (
    export_projections_to_cache,
    generate_all_projections,
    prepare_visualization_sample,
)

FEATURES = ["amt", "city_pop", "lat", "long", "merch_lat", "merch_long"]
METHODS = ("pca", "tsne", "umap")
VIEWS = ("class", "cluster", "outlier", "error", "uncertainty")
FINAL_TEST_NAME = "fraudtest"
DEVELOPMENT_SOURCE_NAME = "fraudTrain.csv"
ERROR_VIEW_WARNING = (
    "error view = point classification at p >= 0.50; service decisions follow "
    "the conformal set ([1] block, [0] approve, [] or [0, 1] review)"
)


def projection_keys() -> list[str]:
    """Return the 15 ``<method>_<view>`` artifact stems expected by the service."""
    return [f"{method}_{view}" for method in METHODS for view in VIEWS]


def ensure_development_source(path: Path) -> None:
    """Refuse the final test and any source whose development provenance is unverifiable."""
    if FINAL_TEST_NAME in path.name.lower():
        raise ValueError(
            "fraudTest.csv is reserved for the official evaluation (D47); "
            "use the full source (only its development zone is read) or synthetic rows."
        )
    if path.name != DEVELOPMENT_SOURCE_NAME:
        raise ValueError(
            f"Unverifiable development source '{path.name}': pass the full "
            f"{DEVELOPMENT_SOURCE_NAME} (only its development zone is read); "
            "pre-filtered extracts are refused."
        )


def refuse_development_extract(path: Path) -> None:
    """Refuse a pre-filtered extract whose development provenance cannot be verified."""
    raise ValueError(
        f"{path} is a pre-filtered extract; its development provenance cannot be "
        "verified. Pass the full source with --data-path instead: only its "
        "development zone (earliest 70 % by transaction date) is read."
    )


def build_sample(
    data_path: Path | None,
    samples: int,
    seed: int = 42,
) -> pd.DataFrame:
    """Load the development zone of a full source, or generate a synthetic sample."""
    if samples < 1:
        raise ValueError("--samples must be positive")
    if data_path is None:
        from ml.src.pipeline.steps import generate_synthetic_data

        return generate_synthetic_data(n_samples=samples, random_state=seed)

    ensure_development_source(data_path)
    return load_development_block(data_path)


def generate_projections(
    model: Any,
    frame: pd.DataFrame,
    model_version: str,
    max_samples: int = 500,
) -> dict[str, dict[str, Any]]:
    """Score the sample and project it into the 15 dashboard artifacts."""
    sample = prepare_visualization_sample(frame, max_samples=max_samples)
    probabilities = np.asarray(model.batch_probabilities(sample), dtype=float)
    y_pred = (probabilities >= 0.50).astype(np.int64)
    projections = generate_all_projections(
        df=sample,
        features=FEATURES,
        y_pred=y_pred,
        probabilities=probabilities,
        model_version=model_version,
        max_samples=max_samples,
    )
    for key, payload in projections.items():
        if key.endswith("_error"):
            payload["warning"] = ERROR_VIEW_WARNING
    return projections


def resolve_run_id(client: Any, model_name: str, version: str | None, alias: str | None) -> str:
    """Return the MLflow run that backs a version or alias."""
    version_row = (
        client.get_model_version_by_alias(model_name, alias)
        if alias
        else client.get_model_version(model_name, str(version))
    )
    run_id = getattr(version_row, "run_id", None)
    if not run_id:
        raise ValueError(f"No MLflow run attached to {model_name}/{alias or version}")
    return str(run_id)


def attach_projections(
    client: Any,
    run_id: str,
    projections: dict[str, dict[str, Any]],
    dry_run: bool = False,
) -> list[str]:
    """Write the projection JSON files under ``viz/`` on an existing run."""
    expected = set(projection_keys())
    missing = sorted(expected - set(projections))
    unexpected = sorted(set(projections) - expected)
    if missing or unexpected:
        raise ValueError(
            f"Projection set mismatch: missing={missing}, unexpected={unexpected}"
        )
    if dry_run:
        return sorted(projections)

    with tempfile.TemporaryDirectory(prefix="ml-viz-") as tmp:
        export_projections_to_cache(projections, Path(tmp))
        client.log_artifacts(run_id=run_id, local_dir=tmp, artifact_path="viz")
    return sorted(projections)


def list_viz_artifacts(
    client: Any,
    run_id: str,
    attempts: int = 5,
    delay: float = 1.0,
) -> list[str]:
    """List uploaded projection files, tolerating a briefly stale artifact store."""
    expected = len(projection_keys())
    stored: list[str] = []
    for attempt in range(attempts):
        stored = sorted(
            Path(item.path).stem
            for item in client.list_artifacts(run_id, "viz")
            if item.path.endswith(".json")
        )
        if len(stored) >= expected:
            return stored
        if attempt + 1 < attempts:
            time.sleep(delay)
    return stored


def _load_python_model(model_uri: str) -> Any:
    """Load the registered model and unwrap the custom pyfunc implementation."""
    import mlflow

    loaded = mlflow.pyfunc.load_model(model_uri)
    unwrap = getattr(loaded, "unwrap_python_model", None)
    return unwrap() if callable(unwrap) else loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-name", default="fraud-detector")
    identity = parser.add_mutually_exclusive_group()
    identity.add_argument("--version", default="1")
    identity.add_argument("--alias")
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--data-path",
        type=Path,
        default=None,
        help=(
            "Full development source (fraudTrain.csv); only its development zone "
            "is read. Defaults to synthetic rows."
        ),
    )
    parser.add_argument(
        "--development-extract",
        type=Path,
        default=None,
        help="Pre-filtered extract: always refused (provenance not verifiable).",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.data_path is not None and args.development_extract is not None:
        parser.error("--data-path and --development-extract are mutually exclusive")
    if args.development_extract is not None:
        refuse_development_extract(args.development_extract)

    import mlflow
    from mlflow.tracking import MlflowClient

    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)
    client = MlflowClient(tracking_uri=args.tracking_uri)

    version = None if args.alias else str(args.version)
    run_id = resolve_run_id(client, args.model_name, version, args.alias)
    suffix = f"@{args.alias}" if args.alias else f"/{version}"
    print(f"Model {args.model_name}{suffix} -> run {run_id}")

    if args.dry_run:
        print(json.dumps({"run_id": run_id, "artifacts": projection_keys()}, indent=2))
        return 0

    frame = build_sample(args.data_path, args.samples, args.seed)
    model = _load_python_model(f"models:/{args.model_name}{suffix}")
    projections = generate_projections(
        model,
        frame,
        model_version=str(args.alias or version),
        max_samples=args.samples,
    )
    attached = attach_projections(client, run_id, projections)

    stored = list_viz_artifacts(client, run_id)
    missing = sorted(set(projection_keys()) - set(stored))
    if missing:
        raise ValueError(f"Artifacts missing after upload: {missing}")

    print(
        json.dumps(
            {
                "run_id": run_id,
                "samples": len(frame),
                "attached": attached,
                "stored": stored,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
