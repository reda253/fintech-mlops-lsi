"""Tests for modular ML pipeline steps and CI smoke pipeline."""

import tempfile
from pathlib import Path

import mlflow
import pytest

from ml.src.pipeline.smoke import run_smoke
from ml.src.pipeline.steps import (
    generate_synthetic_data,
    step_evaluate,
    step_prepare,
    step_quality_gates,
    step_train,
)


@pytest.fixture
def local_mlflow_env():
    """Isolate MLflow store to a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "mlflow.db"
        uri = f"sqlite:///{db_path.as_posix()}"
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("test-steps")
        yield uri


def test_synthetic_data_generation():
    df = generate_synthetic_data(n_samples=100)
    assert len(df) == 100
    assert "amount" in df.columns
    assert "is_fraud" in df.columns
    assert set(df["is_fraud"].unique()).issubset({0, 1})


def test_step_prepare(local_mlflow_env):
    with mlflow.start_run():
        res = step_prepare(test_mode=True, parent_run=True)
    assert "development" in res
    assert "prob_calib" in res
    assert "test" in res
    assert len(res["development"]) > len(res["prob_calib"])


def test_step_train_and_evaluate(local_mlflow_env):
    with mlflow.start_run():
        prep = step_prepare(test_mode=True, parent_run=True)
        train_res = step_train(dev_df=prep["development"], parent_run=True)
        eval_metrics = step_evaluate(
            pipeline_artifacts=train_res,
            test_df=prep["test"],
            parent_run=True,
        )

    assert "model" in train_res
    assert "pr_auc" in eval_metrics
    assert eval_metrics["latency_p95_sec"] >= 0


def test_step_quality_gates(local_mlflow_env):
    metrics = {
        "pr_auc": 0.88,
        "conformal_coverage": 0.95,
        "review_rate": 0.015,
        "latency_p95_sec": 0.010,
    }
    with mlflow.start_run():
        gates = step_quality_gates(metrics=metrics, champion_pr_auc=0.85, parent_run=True)
    assert gates["all_passed"] is True


def test_step_quality_gates_rejects_regression(local_mlflow_env):
    metrics = {
        "pr_auc": 0.60,
        "conformal_coverage": 0.95,
        "review_rate": 0.015,
        "latency_p95_sec": 0.010,
    }
    with mlflow.start_run():
        gates = step_quality_gates(metrics=metrics, champion_pr_auc=0.85, parent_run=True)
    assert gates["all_passed"] is False
    assert gates["gate_non_regression"] is False


def test_smoke_pipeline_end_to_end():
    assert run_smoke() is True
