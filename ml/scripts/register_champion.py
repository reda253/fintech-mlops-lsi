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
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
for _path in (ROOT_DIR, SRC_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from ml.src.model.calibration import conformal_quantile
from ml.src.model.fraud_detector import FraudDetectorModel
from ml.src.model.registry import register_model

FINAL_DECISION_ID = "D48"

# The six documented §5.4 gates. A promotion report must carry exactly these,
# each explicitly true, plus the provenance of the D48 evaluation.
REQUIRED_GATES = (
    "gate_non_regression",
    "gate_coverage",
    "gate_coverage_legit",
    "gate_coverage_fraud",
    "gate_review_rate",
    "gate_latency",
)

# Approved D48 protocol text: docs/final_evaluation_protocol.md at bc30b93.
APPROVED_D48_PROTOCOL_SHA256 = (
    "b0bfaf9ba5b9c3b40dc91c52d34281227846fce4d11b24ff6bf9a166550adc24"
)

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
            calibrator,
            "method",
            type(calibrator).__name__ if calibrator is not None else None,
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
    legit_scores = _first(payload, "legit_scores", "nonconformity_legit") or scores.get(
        "legit"
    )
    fraud_scores = _first(payload, "fraud_scores", "nonconformity_fraud") or scores.get(
        "fraud"
    )
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
        preprocessor = _first(
            payload, "preprocessor", "pipeline", "preproc", "feature_pipeline"
        )
        classifier = _first(payload, "classifier", "model", "estimator", "clf")
        if classifier is None:
            raise ValueError("Le dict candidat doit contenir 'classifier' ou 'model'.")
        calibrator = payload.get("calibrator")
        feature_names = payload.get("feature_names")
        threshold_legit, threshold_fraud = _resolve_thresholds(payload, alpha)
        metadata = payload.get("metadata") or {}
        trained_at = (
            payload.get("trained_at") or metadata.get("trained_at") or trained_at
        )
        payload_alpha = payload.get("alpha") or metadata.get("alpha", alpha)
        beta = payload.get("beta", metadata.get("beta"))
        calibration_method = (
            payload.get("calibration_method")
            or payload.get("calibration")
            or metadata.get("calibration")
            or (type(calibrator).__name__ if calibrator is not None else "none")
        )
        git_commit = payload.get("git_commit", metadata.get("git_commit", git_commit))
        data_sha256 = payload.get(
            "data_sha256", metadata.get("data_sha256", data_sha256)
        )
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


def _sha256_file(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _validate_promotion_gates(
    path: Path,
    *,
    client: MlflowClient | None = None,
    candidate_sha256: str | None = None,
    expected_model_uri: str | None = None,
) -> dict[str, bool]:
    """Refuse promotion unless the six §5.4 gates are proven for this candidate.

    A bare ``{"gate_...": true}`` file is not accepted: a report must also carry
    the provenance of the D48 evaluation that produced it (parent run, child
    ``6_quality_gates`` run, candidate/source/protocol fingerprints), and the
    MLflow runs are re-read to confirm it.
    """

    from ml.src.evaluation.final_artifacts import (
        APPROVED_D48_MODEL_SHA256,
        APPROVED_D48_SOURCE_SHA256,
    )

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    gates = payload.get("gates", payload)
    if not isinstance(gates, dict):
        raise TypeError("Le fichier de portes doit contenir un objet JSON.")

    gate_items = {key: value for key, value in gates.items() if key.startswith("gate_")}
    missing = sorted(set(REQUIRED_GATES) - set(gate_items))
    if missing:
        raise ValueError(f"Portes manquantes : {', '.join(missing)}")
    unexpected = sorted(set(gate_items) - set(REQUIRED_GATES))
    if unexpected:
        raise ValueError(f"Portes inconnues : {', '.join(unexpected)}")
    failed = sorted(key for key, value in gate_items.items() if value is not True)
    if failed:
        raise ValueError(f"Portes non validees : {', '.join(failed)}")

    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise TypeError("Provenance absente : rapport de portes non attribuable.")
    if provenance.get("decision_id") != FINAL_DECISION_ID:
        raise ValueError(
            f"Provenance rattachee a la decision {provenance.get('decision_id')!r}, "
            f"{FINAL_DECISION_ID} requise"
        )
    hashes = {
        key: str(provenance.get(key) or "")
        for key in ("candidate_sha256", "source_sha256", "protocol_sha256")
    }
    for key, value in hashes.items():
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"Provenance : {key} invalide")
    if hashes["candidate_sha256"] != APPROVED_D48_MODEL_SHA256:
        raise ValueError("Provenance : candidat different du modele D44 fige")
    if hashes["source_sha256"] != APPROVED_D48_SOURCE_SHA256:
        raise ValueError(
            "Provenance : source differente de la source approuvee pour D48"
        )
    if hashes["protocol_sha256"] != APPROVED_D48_PROTOCOL_SHA256:
        raise ValueError("Provenance : protocole different du protocole D48 approuve")
    if candidate_sha256 is not None and hashes["candidate_sha256"] != candidate_sha256:
        raise ValueError("Provenance : candidat different de l'artefact a promouvoir")

    parent_run_id = str(provenance.get("parent_run_id") or "")
    gates_run_id = str(provenance.get("gates_run_id") or "")
    if not parent_run_id or not gates_run_id:
        raise ValueError("Provenance : parent_run_id et gates_run_id requis")

    client = client or MlflowClient()
    try:
        parent = client.get_run(parent_run_id)
        gates_run = client.get_run(gates_run_id)
    except Exception as exc:  # mlflow raises MlflowException on a missing run
        raise ValueError(f"Provenance : run MLflow introuvable ({exc})") from exc

    if parent.data.tags.get("decision_id") != FINAL_DECISION_ID:
        raise ValueError("Provenance : le run parent n'est pas une evaluation D48")
    if parent.data.tags.get("evaluation_source") != "final_evaluation_artifacts":
        raise ValueError("Provenance : le run parent ne consomme pas les artefacts D48")
    if parent.data.tags.get("candidate_sha256") != hashes["candidate_sha256"]:
        raise ValueError("Provenance : candidat du run parent different du rapport")
    model_uri = str(parent.data.tags.get("model_uri") or "")
    if expected_model_uri is not None and model_uri != expected_model_uri:
        raise ValueError(
            f"Provenance : modele evalue {model_uri!r} different de {expected_model_uri!r}"
        )
    if gates_run.data.tags.get("mlflow.parentRunId") != parent_run_id:
        raise ValueError("Provenance : le run de portes n'est pas enfant du run parent")
    if not str(gates_run.data.tags.get("mlflow.runName", "")).startswith(
        "6_quality_gates"
    ):
        raise ValueError("Provenance : run enfant 6_quality_gates attendu")
    if gates_run.data.params.get("quality_gates_passed") != "True":
        raise ValueError("Provenance : quality_gates_passed n'est pas True")
    for gate in REQUIRED_GATES:
        if gates_run.data.metrics.get(gate) != 1.0:
            raise ValueError(
                f"Provenance : la porte {gate} n'est pas journalisee a 1.0"
            )

    return {key: True for key in REQUIRED_GATES}


def promote_version(
    model_name: str,
    model_version: str,
    *,
    gates_path: Path | None,
    tracking_uri: str | None = None,
    client: MlflowClient | None = None,
) -> dict[str, Any]:
    """Move ``champion`` to an already-registered, already-measured version."""

    if gates_path is None:
        raise ValueError("--promote-version exige --gates avec les portes de qualite.")
    if client is None:
        client = (
            MlflowClient(tracking_uri=tracking_uri) if tracking_uri else MlflowClient()
        )
    version = str(model_version)
    registered = client.get_model_version(model_name, version)
    candidate_sha256 = str(registered.tags.get("source_model_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", candidate_sha256):
        raise ValueError("Version sans tag source_model_sha256 : promotion refusee")
    if "champion" in registered.aliases:
        raise ValueError(f"{model_name}/{version} porte deja l'alias champion")

    model_uri = f"models:/{model_name}/{version}"
    _validate_promotion_gates(
        gates_path,
        client=client,
        candidate_sha256=candidate_sha256,
        expected_model_uri=model_uri,
    )

    client.set_registered_model_alias(model_name, "champion", version)
    client.set_model_version_tag(model_name, version, "status", "CHAMPION")
    return {
        "name": model_name,
        "version": version,
        "aliases": {"champion": version},
        "model_uri": f"models:/{model_name}@champion",
        "promoted_at": datetime.now(UTC).isoformat(),
    }


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
    gates_path: Path | None = None,
) -> dict[str, Any]:
    """Load, package and register P2's candidate; provisional unless promoted."""

    import joblib

    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    if promote:
        if gates_path is None:
            raise ValueError("--promote exige --gates avec les portes de qualite.")
        _validate_promotion_gates(
            gates_path,
            client=MlflowClient(tracking_uri=tracking_uri)
            if tracking_uri
            else MlflowClient(),
            candidate_sha256=_sha256_file(Path(artifact_path)),
        )
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
        git_commit=git_commit
        or str(metadata.get("git_commit") or _current_git_commit()),
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
            set_challenger=not promote,
            extra_tags=extra_tags,
        )
        for key, value in result["tags"].items():
            mlflow.set_tag(f"model_{key}", value)
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Register P2's candidate as fraud-detector"
    )
    parser.add_argument("--artifact", type=Path, default=None)
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
        help="Move the champion alias to the version registered by this call.",
    )
    parser.add_argument(
        "--promote-version",
        default=None,
        help=(
            "Move the champion alias to an already registered, already measured "
            "version (requires --gates). Preferred over --promote."
        ),
    )
    parser.add_argument(
        "--gates",
        type=Path,
        default=None,
        help="JSON quality-gate report required by --promote/--promote-version.",
    )
    args = parser.parse_args(argv)

    if args.promote_version is not None:
        if args.artifact is not None:
            parser.error("--artifact et --promote-version sont exclusifs")
        if args.promote:
            parser.error(
                "--promote-version deplace deja l'alias ; --promote est inutile"
            )
        result = promote_version(
            args.model_name,
            args.promote_version,
            gates_path=args.gates,
            tracking_uri=args.tracking_uri,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0

    if args.artifact is None:
        parser.error("--artifact ou --promote-version est requis")

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
        gates_path=args.gates,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
