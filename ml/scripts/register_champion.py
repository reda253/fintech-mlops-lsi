"""Register P2's candidate artifact as ``fraud-detector`` (T21d).

P2 hands over raw objects, not a ready pyfunc: either a dict with the fitted
preprocessor, classifier, calibrator, beta and conformal thresholds, or a
``FraudDetectorModel`` whose calibrator and beta live inside a nested
``CalibratedPriorClassifier``. This script rebuilds the P3 wrapper, logs it
with a signature and registers a new model version.

The candidate is provisional by default: it gets its own version but does not
move the ``champion`` alias. Pass ``--promote`` only after parity validation.

Usage:
    python -m ml.scripts.register_champion \
        --artifact /path/to/candidate_model.joblib \
        --metadata /path/to/metadata.json \
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


def _normalise_payload(payload: Any) -> Any:
    """Turn P2's nested ``FraudDetectorModel`` into the dict contract.

    P2's joblib carries ``classifier=CalibratedPriorClassifier``, where the
    inner estimator, ``beta`` and calibrator are nested. Bare estimators and
    plain dicts are returned unchanged.
    """

    if isinstance(payload, dict) or not hasattr(payload, "classifier"):
        return payload

    wrapped = payload.classifier
    if wrapped is None:
        raise ValueError("Le modele candidat ne contient pas de classifier.")

    if hasattr(wrapped, "beta"):
        classifier = getattr(wrapped, "classifier", wrapped)
        beta = getattr(wrapped, "beta", None)
        calibrator = getattr(wrapped, "calibrator", None)
        calibration_method = getattr(
            calibrator, "method", type(calibrator).__name__ if calibrator is not None else None
        )
    else:
        classifier = wrapped
        beta = getattr(payload, "beta", None)
        calibrator = getattr(payload, "calibrator", None)
        calibration_method = getattr(payload, "calibration_method", None)

    return {
        "preprocessor": getattr(payload, "preprocessor", None),
        "classifier": classifier,
        "calibrator": calibrator,
        "calibration_method": calibration_method,
        "beta": beta,
        "feature_names": getattr(payload, "feature_names", None),
        "threshold_legit": getattr(payload, "threshold_legit", None),
        "threshold_fraud": getattr(payload, "threshold_fraud", None),
        "alpha": getattr(payload, "alpha", None),
    }


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
    trained_at: str | None = None,
) -> FraudDetectorModel:
    """Adapt a dict payload, P2's wrapper or a bare estimator to our wrapper."""

    payload = _normalise_payload(payload)

    if isinstance(payload, dict):
        preprocessor = _first(payload, "preprocessor", "pipeline", "preproc", "feature_pipeline")
        classifier = _first(payload, "classifier", "model", "estimator", "clf")
        if classifier is None:
            raise ValueError("Le dict candidat doit contenir 'classifier' ou 'model'.")
        calibrator = payload.get("calibrator")
        feature_names = payload.get("feature_names")
        threshold_legit, threshold_fraud = _resolve_thresholds(payload, alpha)
        metadata = payload.get("metadata") or {}
        trained_at = payload.get("trained_at") or metadata.get("trained_at") or trained_at
        payload_alpha = payload.get("alpha") or metadata.get("alpha", alpha)
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
            raise TypeError(
                "Le joblib doit etre un dict, un FraudDetectorModel ou un estimateur "
                "avec predict_proba()."
            )
        preprocessor = None
        classifier = payload
        calibrator = None
        feature_names = None
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
        feature_names=feature_names,
        threshold_legit=float(threshold_legit),
        threshold_fraud=float(threshold_fraud),
        alpha=float(payload_alpha or alpha),
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
    metadata_path: Path | None = None,
    promote: bool = False,
) -> dict[str, Any]:
    """Load, package and register P2's candidate; provisional unless promoted."""

    import joblib

    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)

    metadata: dict[str, Any] = {}
    if metadata_path is not None:
        metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))

    payload = joblib.load(Path(artifact_path))
    model = build_model_from_payload(
        payload,
        alpha=float(metadata.get("alpha", alpha)),
        model_name=model_name,
        model_version=model_version,
        git_commit=git_commit or str(metadata.get("git_commit") or _current_git_commit()),
        data_sha256=data_sha256 or str(metadata.get("data_sha256") or "unknown"),
        trained_at=metadata.get("timestamp_utc"),
    )
    input_example = load_input_example(input_example_path)
    status = "CHAMPION" if promote else str(metadata.get("status", "PROVISIONAL"))
    extra_tags = {
        "status": status,
        "source_run_id": str(metadata.get("run_id", "unknown")),
        "source_launch_id": str(metadata.get("launch_id", "unknown")),
        "protocol_sha256": str(metadata.get("protocol_sha256", "unknown")),
        "source_model_sha256": str(metadata.get("model_sha256", "unknown")),
        "source_artifact": Path(artifact_path).name,
    }

    with mlflow.start_run(run_name=f"register-{model_name}-v{model_version}") as run:
        mlflow.set_tag("source", "p2-candidate-artifact")
        mlflow.set_tag("artifact_file", Path(artifact_path).name)
        mlflow.set_tag("status", status)
        for key, value in extra_tags.items():
            if value != "unknown":
                mlflow.set_tag(key, value)
        mlflow.log_param("alpha", model.alpha)
        mlflow.log_param("beta", model.beta)
        if metadata_path is not None:
            mlflow.log_artifact(str(metadata_path))
        result = register_model(
            model,
            input_example,
            model_name=model_name,
            pipeline_run_id=run.info.run_id,
            description=(
                f"P2 candidate artifact ({Path(artifact_path).name}), {status.lower()}"
            ),
            set_champion=promote,
            extra_tags=extra_tags,
        )
        for key, value in result["tags"].items():
            mlflow.set_tag(f"model_{key}", value)
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register P2's candidate as fraud-detector")
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, default=None)
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--experiment", default="fraud-detector-registry")
    parser.add_argument("--model-name", default="fraud-detector")
    parser.add_argument("--model-version", default="1")
    parser.add_argument("--alpha", type=float, default=0.02)
    parser.add_argument("--git-commit", default=None)
    parser.add_argument("--data-sha256", default=None)
    parser.add_argument("--input-example", type=Path, default=None)
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Move the champion alias to this version (default: provisional).",
    )
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
        metadata_path=args.metadata,
        promote=args.promote,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
