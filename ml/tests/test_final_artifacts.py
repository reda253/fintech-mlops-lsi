"""D48: verified consumption of the saved final-evaluation artifacts."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import pandas as pd
import pytest

from ml.src.evaluation.final_artifacts import (
    APPROVED_D48_MODEL_SHA256,
    APPROVED_D48_SOURCE_SHA256,
    HISTORY_ARTIFACTS,
    REQUIRED_ARTIFACTS,
    FinalEvaluationError,
    load_verified_final_evaluation,
)
from ml.src.pipeline.smoke import dispose_sqlite_tracking_engine
from ml.src.pipeline.steps import step_evaluate

MODEL_SHA = APPROVED_D48_MODEL_SHA256
SOURCE_SHA = APPROVED_D48_SOURCE_SHA256
PROTOCOL_SHA = "c" * 64
REFERENCE_SHA = "d" * 64
SCRIPT_SHA = "e" * 64
LEGIT_COVERED = 89
FRAUD_COVERED = 10


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _overall(rows: int = 100, frauds: int = 10) -> dict[str, Any]:
    legit = rows - frauds
    coverage_legit = LEGIT_COVERED / legit
    coverage_fraud = FRAUD_COVERED / frauds
    return {
        "pr_auc": 0.81,
        "roc_auc": 0.92,
        "brier_score": 0.08,
        "coverage_legitimate": coverage_legit,
        "coverage_fraud": coverage_fraud,
        "review_rate": 0.01,
        "automation_rate": 0.99,
        "automatic_error_rate": 0.02,
        "n_transactions": rows,
        "fraud_count": frauds,
        "class_counts": {"0": legit, "1": frauds},
        "covered_counts": {"0": LEGIT_COVERED, "1": FRAUD_COVERED},
        "coverage_by_class": {
            "0": coverage_legit,
            "1": coverage_fraud,
        },
    }


def _predictions(rows: int = 100) -> pd.DataFrame:
    labels = np.array([1] * 10 + [0] * (rows - 10), dtype=int)
    probabilities = np.linspace(0.01, 0.99, rows)
    members = np.column_stack([probabilities < 0.4, probabilities >= 0.6]).astype(int)
    return pd.DataFrame(
        {
            "label": labels,
            "fraud_probability": probabilities,
            "include_0": members[:, 0],
            "include_1": members[:, 1],
            "gender": ["M"] * rows,
            "age_group": ["36-45"] * rows,
        }
    )


def build_artifact(
    tmp_path: Path,
    *,
    rows: int = 100,
    predictions_rows: int | None = None,
    predictions: pd.DataFrame | None = None,
    decision_id: str = "D48",
    scope: str = "final_test",
    promotion_ready: bool = False,
    alpha: float = 0.02,
    threshold_legit: float = 0.5,
    threshold_fraud: float = 0.6,
    source_sha256: str = SOURCE_SHA,
    overall_overrides: dict[str, Any] | None = None,
    latency: dict[str, Any] | None = None,
) -> Path:
    output = tmp_path / "d48"
    output.mkdir()
    frame = (
        predictions
        if predictions is not None
        else _predictions(rows if predictions_rows is None else predictions_rows)
    )
    frame.to_csv(output / "predictions.csv", index=False)
    predictions_sha = _sha(output / "predictions.csv")

    history_dir = output / "previous_evaluation"
    history_dir.mkdir()
    (history_dir / "final_metrics.json").write_text("{}\n", encoding="utf-8")
    (history_dir / "final_report.md").write_text("# previous\n", encoding="utf-8")
    history_artifacts = {
        f"previous_evaluation/{name}": _sha(history_dir / name)
        for name in ("final_metrics.json", "final_report.md")
    }

    overall = _overall(rows)
    if overall_overrides:
        overall.update(overall_overrides)
    metrics = {
        "scope": scope,
        "model_status": "provisional",
        "decision_id": decision_id,
        "protocol_revision": "d48-test",
        "model_sha256": MODEL_SHA,
        "source_sha256": source_sha256,
        "reference_sha256": REFERENCE_SHA,
        "protocol_sha256": PROTOCOL_SHA,
        "evaluation_script_sha256": SCRIPT_SHA,
        "metrics_module_sha256": "f" * 64,
        "tracking_module_sha256": "0" * 64,
        "alpha": alpha,
        "threshold_legit": threshold_legit,
        "threshold_fraud": threshold_fraud,
        "promotion_ready": promotion_ready,
        "predictions_sha256": predictions_sha,
        "overall": overall,
        "latency": latency
        if latency is not None
        else {"status": "measured", "p95_ms": 12.0, "calls": 1000},
        "previous_evaluation": {"artifacts": history_artifacts},
        "measurement": {"number": 2, "post_hoc": True, "independent": False},
        "fairness": [],
        "versions": {},
    }
    _write_json(output / "final_metrics.json", metrics)
    (output / "final_report.md").write_text("# report\n", encoding="utf-8")
    (output / "fairness_groups.csv").write_text("attribute,group,n\n", encoding="utf-8")
    _write_json(output / "bootstrap_intervals.json", {"overall": {}})

    artifacts = {
        name: _sha(output / name) for name in (*REQUIRED_ARTIFACTS, *HISTORY_ARTIFACTS)
    }
    _write_json(
        output / "artifact_manifest.json",
        {"status": "complete", "artifacts": artifacts},
    )
    return output


class FakeModel:
    alpha = 0.02
    threshold_legit = 0.5
    threshold_fraud = 0.6


@pytest.fixture
def local_mlflow_env():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "mlflow.db"
        uri = f"sqlite:///{db_path.as_posix()}"
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("test-final-artifacts")
        try:
            yield uri
        finally:
            dispose_sqlite_tracking_engine(uri)


def test_valid_artifact_maps_metrics(tmp_path: Path):
    directory = build_artifact(tmp_path)

    evaluation = load_verified_final_evaluation(
        directory,
        expected_alpha=0.02,
        expected_threshold_legit=0.5,
        expected_threshold_fraud=0.6,
    )

    assert evaluation.metrics["pr_auc"] == pytest.approx(0.81)
    assert evaluation.metrics["conformal_coverage"] == pytest.approx(0.99)
    assert evaluation.metrics["conformal_coverage_legit"] == pytest.approx(
        LEGIT_COVERED / 90
    )
    assert evaluation.metrics["conformal_coverage_fraud"] == pytest.approx(1.0)
    assert evaluation.metrics["latency_p95_sec"] == pytest.approx(0.012)
    assert evaluation.metrics["n_test"] == 100.0
    assert evaluation.metrics["n_test_fraud"] == 10.0
    assert evaluation.provenance["decision_id"] == "D48"
    assert evaluation.provenance["model_sha256"] == MODEL_SHA
    assert evaluation.provenance["source_sha256"] == SOURCE_SHA


def test_tampered_artifact_is_refused(tmp_path: Path):
    directory = build_artifact(tmp_path)
    with (directory / "final_metrics.json").open("ab") as stream:
        stream.write(b"\n")

    with pytest.raises(FinalEvaluationError, match="empreinte"):
        load_verified_final_evaluation(directory)


def test_tampered_predictions_are_refused(tmp_path: Path):
    directory = build_artifact(tmp_path)
    with (directory / "predictions.csv").open("ab") as stream:
        stream.write(b"tampered\n")

    with pytest.raises(FinalEvaluationError, match="empreinte"):
        load_verified_final_evaluation(directory)


def test_missing_manifest_file_is_refused(tmp_path: Path):
    directory = build_artifact(tmp_path)
    (directory / "final_report.md").unlink()

    with pytest.raises(FinalEvaluationError, match="absent"):
        load_verified_final_evaluation(directory)


def test_missing_required_metric_is_refused(tmp_path: Path):
    directory = build_artifact(tmp_path, overall_overrides={"pr_auc": None})
    # None is a valid JSON value but an invalid required metric.
    with pytest.raises(FinalEvaluationError, match="pr_auc"):
        load_verified_final_evaluation(directory)


def test_wrong_model_hash_is_refused(tmp_path: Path):
    directory = build_artifact(tmp_path)

    with pytest.raises(FinalEvaluationError, match="empreinte du candidat"):
        load_verified_final_evaluation(directory, expected_model_sha256="9" * 64)


def test_source_hash_must_match_the_approved_d48_source(tmp_path: Path):
    directory = build_artifact(tmp_path, source_sha256="9" * 64)

    with pytest.raises(FinalEvaluationError, match="source approuvee"):
        load_verified_final_evaluation(directory)


def test_alpha_and_threshold_mismatch_are_refused(tmp_path: Path):
    directory = build_artifact(tmp_path)
    with pytest.raises(FinalEvaluationError, match="alpha"):
        load_verified_final_evaluation(directory, expected_alpha=0.05)
    with pytest.raises(FinalEvaluationError, match="threshold_fraud"):
        load_verified_final_evaluation(directory, expected_threshold_fraud=0.9)


@pytest.mark.parametrize(
    ("decision_id", "scope", "message"),
    [
        ("D47", "final_test", "D48"),
        ("D48", "synthetic_only", "final_test"),
    ],
)
def test_wrong_decision_or_scope_is_refused(
    tmp_path: Path, decision_id: str, scope: str, message: str
):
    directory = build_artifact(tmp_path, decision_id=decision_id, scope=scope)

    with pytest.raises(FinalEvaluationError, match=message):
        load_verified_final_evaluation(directory)


def test_promotion_ready_artifact_is_refused(tmp_path: Path):
    directory = build_artifact(tmp_path, promotion_ready=True)

    with pytest.raises(FinalEvaluationError, match="promotion_ready"):
        load_verified_final_evaluation(directory)


def test_prediction_row_count_mismatch_is_refused(tmp_path: Path):
    directory = build_artifact(tmp_path, rows=100, predictions_rows=99)

    with pytest.raises(FinalEvaluationError, match="nombre de lignes"):
        load_verified_final_evaluation(directory)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"pr_auc": 1.2}, "pr_auc"),
        ({"roc_auc": -0.1}, "roc_auc"),
        ({"brier_score": 1.5}, "brier_score"),
        ({"review_rate": -0.01}, "review_rate"),
        ({"review_rate": 0.02}, "review_rate \\+ automation_rate"),
        ({"coverage_legitimate": 1.5}, "coverage_legitimate"),
        ({"coverage_fraud": -0.2}, "coverage_fraud"),
        ({"automation_rate": 1.5}, "automation_rate"),
        ({"automatic_error_rate": 2.0}, "automatic_error_rate"),
        ({"covered_counts": {"0": 200, "1": 10}}, "covered_counts"),
        ({"class_counts": {"0": 90, "1": 20}}, "class_counts"),
        ({"fraud_count": 0}, "aucune fraude"),
    ],
)
def test_out_of_bounds_metrics_are_refused(
    tmp_path: Path, override: dict[str, Any], message: str
):
    directory = build_artifact(tmp_path, overall_overrides=override)

    with pytest.raises(FinalEvaluationError, match=message):
        load_verified_final_evaluation(directory)


@pytest.mark.parametrize(
    ("alpha", "threshold_legit", "threshold_fraud", "message"),
    [
        (0.0, 0.5, 0.6, "alpha"),
        (1.0, 0.5, 0.6, "alpha"),
        (0.02, -0.1, 0.6, "threshold_legit"),
        (0.02, 0.5, 1.1, "threshold_fraud"),
    ],
)
def test_out_of_bounds_alpha_and_thresholds_are_refused(
    tmp_path: Path,
    alpha: float,
    threshold_legit: float,
    threshold_fraud: float,
    message: str,
):
    directory = build_artifact(
        tmp_path,
        alpha=alpha,
        threshold_legit=threshold_legit,
        threshold_fraud=threshold_fraud,
    )

    with pytest.raises(FinalEvaluationError, match=message):
        load_verified_final_evaluation(directory)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("fraud_probability", 1.5, "fraud_probability"),
        ("fraud_probability", -0.1, "fraud_probability"),
        ("label", 2, "label"),
        ("include_0", 2, "include_0"),
        ("include_1", -1, "include_0/include_1"),
        ("label", np.nan, "non numeriques"),
    ],
)
def test_out_of_bounds_predictions_are_refused(
    tmp_path: Path, column: str, value: Any, message: str
):
    predictions = _predictions()
    predictions.loc[0, column] = value
    directory = build_artifact(tmp_path, predictions=predictions)

    with pytest.raises(FinalEvaluationError, match=message):
        load_verified_final_evaluation(directory)


def test_prediction_fraud_count_must_match(tmp_path: Path):
    predictions = _predictions()
    predictions.loc[0, "label"] = 0
    directory = build_artifact(tmp_path, predictions=predictions)

    with pytest.raises(FinalEvaluationError, match="nombre de fraudes"):
        load_verified_final_evaluation(directory)


@pytest.mark.parametrize(
    ("latency", "message"),
    [
        ({"status": "measured", "p95_ms": 0.0, "calls": 1000}, "strictement positif"),
        ({"status": "measured", "p95_ms": 12.0, "calls": 0}, "latency.calls"),
        ({"status": "measured", "p95_ms": 12.0, "calls": -5}, "latency.calls"),
        ({"status": "measured", "p95_ms": 12.0}, "latency.calls"),
    ],
)
def test_invalid_latency_is_refused(
    tmp_path: Path, latency: dict[str, Any], message: str
):
    directory = build_artifact(tmp_path, latency=latency)

    with pytest.raises(FinalEvaluationError, match=message):
        load_verified_final_evaluation(directory)


def test_step_evaluate_logs_verified_metrics(tmp_path: Path, local_mlflow_env):
    directory = build_artifact(tmp_path)
    with mlflow.start_run():
        metrics = step_evaluate(
            pyfunc_model=FakeModel(),
            evaluation_dir=directory,
            expected_model_sha256=MODEL_SHA,
            parent_run=True,
        )

    assert metrics["pr_auc"] == pytest.approx(0.81)
    assert metrics["alpha"] == pytest.approx(0.02)
    assert metrics["latency_sample_size"] == pytest.approx(1000.0)
