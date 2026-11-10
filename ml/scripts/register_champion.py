"""Register P2's candidate artifact as ``fraud-detector`` (T21d).

P2 hands over raw objects, not a ready pyfunc: a dict with the fitted
preprocessor, classifier, calibrator, beta and conformal thresholds (or scores).
This script rebuilds the P3 wrapper, logs it with a signature and registers a
new model version with the champion alias.

Usage:
    python -m ml.scripts.register_champion \
        --artifact /path/to/candidate_model.joblib \
        --tracking-uri http://localhost:5000 \
        --alpha 0.02
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
for _path in (ROOT_DIR, SRC_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from ml.src.model.calibration import conformal_quantile
from ml.src.model.fraud_detector import FraudDetectorModel
from ml.src.model.registry import register_model

DEFAULT_INPUT_EXAMPLE = pd.DataFrame(
    [
        {
            "transaction_id": "11111111-1111-1111-1111-111111111111",
            "trans_datetime": "2020-07-14T02:13:45",
            "amount": 150.0,
            "category": "shopping_net",
            "merch_lat": 40.71,
            "merch_long": -74.01,
            "customer": {
                "dob": "1962-05-18",
                "gender": "F",
                "city_pop": 1577385,
                "lat": 40.65,
                "long": -73.95,
                "state": "NY",
            },
        },
        {
            "transaction_id": "22222222-2222-2222-2222-222222222222",
            "trans_datetime": "2020-07-15T03:04:05",
            "amount": 12.5,
            "category": "grocery_pos",
            "merch_lat": 34.05,
            "merch_long": -118.24,
            "customer": {
                "dob": "1985-05-15",
                "gender": "M",
                "city_pop": 50000,
                "lat": 34.0522,
                "long": -118.2437,
                "state": "CA",
            },
        },
    ]
)


def _first(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = payload.get(name)
        if value is not None:
            return value
    return None


def _resolve_thresholds(
    payload: dict[str, Any],
    alpha: float,
) -> tuple[float, float]:
    threshold_legit = _first(payload, "threshold_legit", "q_legit", "quantile_legit")
    threshold_fraud = _first(payload, "threshold_fraud", "q_fraud", "quantile_fraud")
    if threshold_legit is not None and threshold_fraud is not None:
        return float(threshold_legit), float(threshold_fraud)

    scores = payload.get("conformal_scores") or {}
    if not isinstance(scores, dict):
        scores = {}
    legit_scores = _first(payload, "legit_scores", "nonconformity_legit") or scores.get("legit")
    fraud_scores = _first(payload, "fraud_scores", "nonconformity_fraud") or scores.get("fraud")
    if legit_scores is None or fraud_scores is None:
        raise ValueError(
            "Le candidat doit fournir threshold_legit/threshold_fraud "
            "ou les scores de non-conformite par classe."
        )
    return (
        conformal_quantile(np.asarray(legit_scores, dtype=float), alpha),
        conformal_quantile(np.asarray(fraud_scores, dtype=float), alpha),
    )


def build_model_from_payload(
    payload: Any,
    *,
    alpha: float = 0.02,
    model_name: str = "fraud-detector",
    model_version: str = "1",
    git_commit: str = "unknown",
    data_sha256: str = "unknown",
) -> FraudDetectorModel:
    """Adapt either a dict payload or a single full pipeline into the wrapper."""

    if isinstance(payload, dict):
        preprocessor = _first(payload, "preprocessor", "pipeline", "preproc", "feature_pipeline")
        classifier = _first(payload, "classifier", "model", "estimator", "clf")
        if classifier is None:
            raise ValueError("Le dict candidat doit contenir 'classifier' ou 'model'.")
        calibrator = payload.get("calibrator")
        threshold_legit, threshold_fraud = _resolve_thresholds(payload, alpha)
        metadata = payload.get("metadata") or {}
        trained_at = payload.get("trained_at") or metadata.get("trained_at")
        payload_alpha = payload.get("alpha", metadata.get("alpha", alpha))
        beta = payload.get("beta", metadata.get("beta"))
        calibration_method = (
            payload.get("calibration_method")
            or payload.get("calibration")
            or metadata.get("calibration")
            or (type(calibrator).__name__ if calibrator is not None else "none")
        )
        git_commit = payload.get("git_commit", metadata.get("git_commit", git_commit))
        data_sha256 = payload.get("data_sha256", metadata.get("data_sha256", data_sha256))
    else:
        # Single object: assumed to consume raw Sparkov rows and expose predict_proba.
        if not hasattr(payload, "predict_proba"):
            raise TypeError("Le joblib doit etre un dict ou un estimateur avec predict_proba().")
        preprocessor = None
        classifier = payload
        calibrator = None
        threshold_legit = 0.0
        threshold_fraud = 0.0
        payload_alpha = alpha
        beta = None
        calibration_method = "none"
        trained_at = None

    return FraudDetectorModel(
        classifier=classifier,
        preprocessor=preprocessor,
        calibrator=calibrator,
        calibration_method=str(calibration_method),
        beta=None if beta is None else float(beta),
        threshold_legit=float(threshold_legit),
        threshold_fraud=float(threshold_fraud),
        alpha=float(payload_alpha),
        model_name=model_name,
        model_version=str(model_version),
        algorithm="xgboost-calibrated",
        trained_at=str(trained_at or datetime.now(UTC).isoformat()),
        git_commit=str(git_commit),
        data_sha256=str(data_sha256),
    )


def _current_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def load_input_example(path: Path | None) -> pd.DataFrame:
    if path is None:
        return DEFAULT_INPUT_EXAMPLE.copy()
    if path.suffix.lower() in {".json"}:
        records = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(records, dict):
            records = [records]
        return pd.DataFrame(records)
    frame = pd.read_csv(path)
    from ml.src.model.registry import build_input_example

    return build_input_example(frame)


def register_candidate(
    artifact_path: Path,
    *,
    tracking_uri: str | None = None,
    experiment: str = "fraud-detector-registry",
    model_name: str = "fraud-detector",
    model_version: str = "1",
    alpha: float = 0.02,
    git_commit: str | None = None,
    data_sha256: str | None = None,
    input_example_path: Path | None = None,
) -> dict[str, Any]:
    """Load, package, register and alias P2's candidate artifact."""

    import joblib

    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)

    payload = joblib.load(Path(artifact_path))
    model = build_model_from_payload(
        payload,
        alpha=alpha,
        model_name=model_name,
        model_version=model_version,
        git_commit=git_commit or _current_git_commit(),
        data_sha256=data_sha256 or "unknown",
    )
    input_example = load_input_example(input_example_path)

    with mlflow.start_run(run_name=f"register-{model_name}-v{model_version}") as run:
        mlflow.set_tag("source", "p2-candidate-artifact")
        mlflow.set_tag("artifact_file", Path(artifact_path).name)
        mlflow.log_param("alpha", model.alpha)
        mlflow.log_param("beta", model.beta)
        result = register_model(
            model,
            input_example,
            model_name=model_name,
            pipeline_run_id=run.info.run_id,
            description=f"Imported from P2 candidate artifact ({Path(artifact_path).name})",
        )
        for key, value in result["tags"].items():
            mlflow.set_tag(f"model_{key}", value)
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register P2's candidate as fraud-detector")
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--experiment", default="fraud-detector-registry")
    parser.add_argument("--model-name", default="fraud-detector")
    parser.add_argument("--model-version", default="1")
    parser.add_argument("--alpha", type=float, default=0.02)
    parser.add_argument("--git-commit", default=None)
    parser.add_argument("--data-sha256", default=None)
    parser.add_argument("--input-example", type=Path, default=None)
    args = parser.parse_args(argv)

    result = register_candidate(
        args.artifact,
        tracking_uri=args.tracking_uri,
        experiment=args.experiment,
        model_name=args.model_name,
        model_version=args.model_version,
        alpha=args.alpha,
        git_commit=args.git_commit,
        data_sha256=args.data_sha256,
        input_example_path=args.input_example,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
