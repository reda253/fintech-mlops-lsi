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
    HISTORY_ARTIFACTS,
    REQUIRED_ARTIFACTS,
    FinalEvaluationError,
    load_verified_final_evaluation,
)
from ml.src.pipeline.smoke import dispose_sqlite_tracking_engine
from ml.src.pipeline.steps import step_evaluate

MODEL_SHA = "a" * 64
SOURCE_SHA = "b" * 64
PROTOCOL_SHA = "c" * 64
REFERENCE_SHA = "d" * 64
SCRIPT_SHA = "e" * 64


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _overall(rows: int = 100, frauds: int = 10) -> dict[str, Any]:
    return {
        "pr_auc": 0.81,
        "roc_auc": 0.92,
        "brier_score": 0.08,
        "coverage_legitimate": 0.99,
        "coverage_fraud": 0.995,
        "review_rate": 0.01,
        "automation_rate": 0.99,
        "automatic_error_rate": 0.02,
        "n_transactions": rows,
        "fraud_count": frauds,
        "class_counts": {"0": rows - frauds, "1": frauds},
        "covered_counts": {"0": rows - frauds, "1": frauds},
        "coverage_by_class": {"0": 0.99, "1": 0.995},
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
    decision_id: str = "D48",
    scope: str = "final_test",
    promotion_ready: bool = False,
    alpha: float = 0.02,
    threshold_legit: float = 0.5,
    threshold_fraud: float = 0.6,
    overall_overrides: dict[str, Any] | None = None,
) -> Path:
    output = tmp_path / "d48"
    output.mkdir()
    predictions = _predictions(rows if predictions_rows is None else predictions_rows)
    predictions.to_csv(output / "predictions.csv", index=False)
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
        "source_sha256": SOURCE_SHA,
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
        "latency": {"status": "measured", "p95_ms": 12.0, "calls": 1000},
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
        expected_model_sha256=MODEL_SHA,
        expected_alpha=0.02,
        expected_threshold_legit=0.5,
        expected_threshold_fraud=0.6,
    )

    assert evaluation.metrics["pr_auc"] == pytest.approx(0.81)
    assert evaluation.metrics["conformal_coverage"] == pytest.approx(1.0)
    assert evaluation.metrics["conformal_coverage_legit"] == pytest.approx(0.99)
    assert evaluation.metrics["conformal_coverage_fraud"] == pytest.approx(0.995)
    assert evaluation.metrics["latency_p95_sec"] == pytest.approx(0.012)
    assert evaluation.metrics["n_test"] == 100.0
    assert evaluation.metrics["n_test_fraud"] == 10.0
    assert evaluation.provenance["decision_id"] == "D48"
    assert evaluation.provenance["model_sha256"] == MODEL_SHA


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
