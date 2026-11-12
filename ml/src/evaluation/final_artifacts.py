"""Verified consumption of the final-evaluation artifacts produced by D48."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_ARTIFACTS = (
    "final_metrics.json",
    "final_report.md",
    "fairness_groups.csv",
    "bootstrap_intervals.json",
    "predictions.csv",
)
HISTORY_ARTIFACTS = (
    "previous_evaluation/final_metrics.json",
    "previous_evaluation/final_report.md",
)
REQUIRED_OVERALL = (
    "pr_auc",
    "roc_auc",
    "brier_score",
    "coverage_legitimate",
    "coverage_fraud",
    "review_rate",
    "automation_rate",
    "automatic_error_rate",
    "n_transactions",
    "fraud_count",
)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
PREDICTION_COLUMNS = ("label", "fraud_probability", "include_0", "include_1")


class FinalEvaluationError(ValueError):
    """The saved final-evaluation directory is absent, partial or inconsistent."""


@dataclass(frozen=True)
class FinalEvaluation:
    """Metrics and provenance extracted from a verified D48 directory."""

    directory: Path
    metrics: dict[str, float | None]
    provenance: dict[str, str | int | bool]


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalEvaluationError(message)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FinalEvaluationError(f"{label} absent: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise FinalEvaluationError(f"{label} illisible: {path}") from exc
    if not isinstance(payload, dict):
        raise FinalEvaluationError(f"{label} doit etre un objet JSON: {path}")
    return payload


def _hash_field(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    _require(
        isinstance(value, str) and bool(HASH_PATTERN.fullmatch(value)),
        f"{label}: empreinte SHA-256 invalide pour {key}",
    )
    return value


def _finite(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"metrique finale invalide: {label}",
    )
    return float(value)


def _optional_finite(value: Any, label: str) -> float | None:
    if value is None:
        return None
    return _finite(value, label)


def _positive_count(value: Any, label: str) -> int:
    _require(
        type(value) is int and value > 0,
        f"effectif final invalide: {label}",
    )
    return value


def _non_negative_count(value: Any, label: str) -> int:
    _require(
        type(value) is int and value >= 0,
        f"effectif final invalide: {label}",
    )
    return value


def _verify_manifest(directory: Path) -> tuple[dict[str, str], dict[str, Any]]:
    manifest = _read_json(directory / "artifact_manifest.json", "manifeste final")
    _require(
        manifest.get("status") == "complete",
        "manifeste final incomplet: status 'complete' requis",
    )
    artifacts = manifest.get("artifacts")
    _require(isinstance(artifacts, dict), "manifeste final sans table d'artefacts")
    for name in (*REQUIRED_ARTIFACTS, *HISTORY_ARTIFACTS):
        _require(name in artifacts, f"artefact absent du manifeste: {name}")
        path = directory / name
        _require(path.is_file(), f"artefact absent du dossier: {name}")
        _require(
            artifacts[name] == _sha256(path),
            f"empreinte differente pour {name}: artefact altere",
        )
    return artifacts, manifest


def _verify_predictions(
    directory: Path,
    artifacts: dict[str, str],
    metrics: dict[str, Any],
    transactions: int,
) -> str:
    predictions_sha = _hash_field(metrics, "predictions_sha256", "metriques finales")
    _require(
        artifacts["predictions.csv"] == predictions_sha,
        "empreinte predictions.csv incoherente avec final_metrics.json",
    )
    path = directory / "predictions.csv"
    try:
        predictions = pd.read_csv(path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise FinalEvaluationError(f"predictions.csv illisible: {path}") from exc
    missing = [
        column for column in PREDICTION_COLUMNS if column not in predictions.columns
    ]
    _require(not missing, f"predictions.csv sans colonnes requises: {missing}")
    _require(
        len(predictions) == transactions,
        "predictions.csv: nombre de lignes different de n_transactions",
    )
    return predictions_sha


def _coverage_total(overall: dict[str, Any], transactions: int, frauds: int) -> float:
    covered = overall.get("covered_counts")
    if isinstance(covered, dict) and {"0", "1"}.issubset(covered):
        legit = _non_negative_count(covered["0"], "covered_counts.0")
        fraud = _non_negative_count(covered["1"], "covered_counts.1")
        return (legit + fraud) / transactions
    legit = _finite(overall["coverage_legitimate"], "coverage_legitimate")
    fraud = _finite(overall["coverage_fraud"], "coverage_fraud")
    n_legit = transactions - frauds
    return (legit * n_legit + fraud * frauds) / transactions


def _verify_history(metrics: dict[str, Any], artifacts: dict[str, str]) -> None:
    history = metrics.get("previous_evaluation")
    _require(isinstance(history, dict), "D48: historique de la premiere mesure absent")
    history_artifacts = history.get("artifacts")
    _require(isinstance(history_artifacts, dict), "D48: artifacts historiques absents")
    for name in HISTORY_ARTIFACTS:
        _require(name in history_artifacts, f"D48: archive historique absente: {name}")
        digest = _hash_field(history_artifacts, name, "historique")
        _require(
            artifacts.get(name) == digest,
            f"D48: empreinte historique incoherente avec le manifeste: {name}",
        )
    measurement = metrics.get("measurement")
    _require(isinstance(measurement, dict), "D48: statut de seconde mesure absent")
    _require(measurement.get("number") == 2, "D48: numero de mesure different de 2")
    _require(measurement.get("post_hoc") is True, "D48: mesure post hoc requise")
    _require(
        measurement.get("independent") is False,
        "D48: la seconde mesure ne doit pas etre declaree independante",
    )


def load_verified_final_evaluation(
    directory: str | Path,
    *,
    expected_model_sha256: str | None = None,
    expected_alpha: float | None = None,
    expected_threshold_legit: float | None = None,
    expected_threshold_fraud: float | None = None,
) -> FinalEvaluation:
    """Load a D48 directory after checking every hash, metric and binding.

    Raises ``FinalEvaluationError`` on any missing, partial or inconsistent
    artifact. The function never opens the final test source.
    """

    output = Path(directory)
    _require(output.is_dir(), f"dossier d'evaluation absent: {output}")
    artifacts, _manifest = _verify_manifest(output)

    metrics_payload = _read_json(output / "final_metrics.json", "metriques finales")
    _require(
        metrics_payload.get("decision_id") == "D48",
        "artefact final: decision D48 requise",
    )
    _require(
        metrics_payload.get("scope") == "final_test",
        "artefact final: scope 'final_test' requis",
    )
    _require(
        metrics_payload.get("model_status") == "provisional",
        "artefact final: le candidat doit rester provisoire",
    )
    _require(
        metrics_payload.get("promotion_ready") is False,
        "artefact final: promotion_ready doit etre false",
    )

    model_sha = _hash_field(metrics_payload, "model_sha256", "metriques finales")
    _hash_field(metrics_payload, "source_sha256", "metriques finales")
    protocol_sha = _hash_field(metrics_payload, "protocol_sha256", "metriques finales")
    _hash_field(metrics_payload, "reference_sha256", "metriques finales")
    _hash_field(metrics_payload, "evaluation_script_sha256", "metriques finales")
    if expected_model_sha256 is not None:
        _require(
            model_sha == expected_model_sha256.lower(),
            "empreinte du candidat differente du modele servi",
        )

    alpha = _finite(metrics_payload.get("alpha"), "alpha")
    threshold_legit = _finite(metrics_payload.get("threshold_legit"), "threshold_legit")
    threshold_fraud = _finite(metrics_payload.get("threshold_fraud"), "threshold_fraud")
    for expected, observed, label in (
        (expected_alpha, alpha, "alpha"),
        (expected_threshold_legit, threshold_legit, "threshold_legit"),
        (expected_threshold_fraud, threshold_fraud, "threshold_fraud"),
    ):
        if expected is not None:
            _require(
                math.isclose(float(expected), observed, rel_tol=0, abs_tol=1e-12),
                f"artefact final: {label} different du modele servi",
            )

    overall = metrics_payload.get("overall")
    _require(isinstance(overall, dict), "metriques finales: bloc 'overall' absent")
    for key in REQUIRED_OVERALL:
        _require(key in overall, f"metrique finale absente: {key}")
    transactions = _positive_count(overall["n_transactions"], "n_transactions")
    frauds = _non_negative_count(overall["fraud_count"], "fraud_count")
    _require(frauds <= transactions, "metriques finales: fraud_count > n_transactions")

    coverage_legit = _finite(overall["coverage_legitimate"], "coverage_legitimate")
    coverage_fraud = _finite(overall["coverage_fraud"], "coverage_fraud")
    coverage_total = _coverage_total(overall, transactions, frauds)
    _verify_predictions(output, artifacts, metrics_payload, transactions)
    _verify_history(metrics_payload, artifacts)

    latency = metrics_payload.get("latency")
    _require(isinstance(latency, dict), "metriques finales: bloc 'latency' absent")
    measured = latency.get("status") == "measured"
    latency_p95_sec: float | None = None
    latency_calls = 0.0
    if measured:
        latency_p95_sec = _finite(latency.get("p95_ms"), "latency.p95_ms") / 1000.0
        latency_calls = _finite(latency.get("calls"), "latency.calls")

    metrics: dict[str, float | None] = {
        "alpha": alpha,
        "pr_auc": _finite(overall["pr_auc"], "pr_auc"),
        "roc_auc": _finite(overall["roc_auc"], "roc_auc"),
        "brier_score": _finite(overall["brier_score"], "brier_score"),
        "conformal_coverage": coverage_total,
        "conformal_coverage_legit": coverage_legit,
        "conformal_coverage_fraud": coverage_fraud,
        "review_rate": _finite(overall["review_rate"], "review_rate"),
        "automation_rate": _finite(overall["automation_rate"], "automation_rate"),
        "auto_error_rate": _optional_finite(
            overall["automatic_error_rate"], "automatic_error_rate"
        ),
        "latency_p95_sec": latency_p95_sec,
        "latency_sample_size": latency_calls,
        "n_test": float(transactions),
        "n_test_fraud": float(frauds),
    }

    provenance: dict[str, str | int | bool] = {
        "decision_id": "D48",
        "model_sha256": model_sha,
        "source_sha256": str(metrics_payload["source_sha256"]),
        "predictions_sha256": str(metrics_payload["predictions_sha256"]),
        "protocol_sha256": protocol_sha,
        "reference_sha256": str(metrics_payload["reference_sha256"]),
        "evaluation_script_sha256": str(metrics_payload["evaluation_script_sha256"]),
        "artifact_manifest_sha256": _sha256(output / "artifact_manifest.json"),
        "measurement_number": 2,
        "measurement_independent": False,
    }
    return FinalEvaluation(directory=output, metrics=metrics, provenance=provenance)
