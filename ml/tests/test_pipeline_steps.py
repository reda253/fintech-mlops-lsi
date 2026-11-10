"""Tests for modular ML pipeline steps and CI smoke pipeline (T21)."""

import tempfile
from pathlib import Path

import mlflow
import pytest

from ml.src.pipeline.smoke import dispose_sqlite_tracking_engine, run_smoke
from ml.src.pipeline.steps import (
    DEFAULT_ALPHA,
    generate_synthetic_data,
    step_calibrate,
    step_conformal,
    step_evaluate,
    step_package_model,
    step_prepare,
    step_quality_gates,
    step_train,
)


@pytest.fixture
def local_mlflow_env():
    """Isolate MLflow store to a temporary directory."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "mlflow.db"
        uri = f"sqlite:///{db_path.as_posix()}"
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("test-steps")
        try:
            yield uri
        finally:
            dispose_sqlite_tracking_engine(uri)


def test_synthetic_data_generation():
    df = generate_synthetic_data(n_samples=200)
    assert len(df) == 200
    assert {
        "trans_date_trans_time",
        "dob",
        "amt",
        "category",
        "gender",
        "state",
        "city_pop",
        "lat",
        "long",
        "merch_lat",
        "merch_long",
        "is_fraud",
        "trans_num",
    }.issubset(df.columns)
    assert df["trans_num"].is_unique
    assert set(df["is_fraud"].unique()).issubset({0, 1})
    assert df["trans_date_trans_time"].is_monotonic_increasing


def test_step_prepare_splits_are_disjoint(local_mlflow_env):
    with mlflow.start_run():
        res = step_prepare(test_mode=True, parent_run=True)

    development = res["development"]
    prob_calib = res["prob_calib"]
    conformal_calib = res["conformal_calib"]
    test = res["test"]

    assert len(development) > len(prob_calib) > 0
    assert len(prob_calib) == len(conformal_calib)
    assert res["test_data_hash"] != res["data_hash"]
    assert res["source"] == "synthetic"

    blocks = [development, prob_calib, conformal_calib]
    for index, block in enumerate(blocks):
        for other in blocks[index + 1:]:
            assert set(block["trans_num"]).isdisjoint(set(other["trans_num"]))
    assert set(prob_calib["trans_num"]).isdisjoint(set(test["trans_num"]))


def test_train_calibrate_conformal_and_evaluate(local_mlflow_env):
    with mlflow.start_run():
        prep = step_prepare(test_mode=True, parent_run=True)
        train_res = step_train(dev_df=prep["development"], parent_run=True)
        calibration = step_calibrate(
            train_result=train_res,
            prob_calib_df=prep["prob_calib"],
            parent_run=True,
        )
        conformal = step_conformal(
            train_result=train_res,
            calibration_result=calibration,
            conformal_df=prep["conformal_calib"],
            alpha=0.02,
            parent_run=True,
        )
        model = step_package_model(
            train_result=train_res,
            calibration_result=calibration,
            conformal_result=conformal,
            alpha=0.02,
            parent_run=True,
        )
        metrics = step_evaluate(
            pyfunc_model=model,
            test_df=prep["test"],
            latency_sample_size=25,
            parent_run=True,
        )

    assert "classifier" in train_res
    assert 0.0 < train_res["beta"] <= 1.0
    assert calibration["method"] in {"isotonic", "sigmoid", "identity"}
    assert calibration["brier_after"] <= calibration["brier_before"] + 1e-9
    assert 0.0 <= conformal["threshold_legit"] <= 1.0
    assert 0.0 <= conformal["threshold_fraud"] <= 1.0
    assert conformal["alpha"] == 0.02
    assert model.alpha == 0.02
    assert 0.0 <= metrics["review_rate"] <= 1.0
    assert 0.0 <= metrics["auto_error_rate"] <= 1.0
    assert metrics["conformal_coverage_fraud"] > 0.0
    assert metrics["latency_p95_sec"] >= 0.0
    assert metrics["alpha"] == 0.02


def test_quality_gates_boundary_and_alpha_propagation(local_mlflow_env):
    base = {
        "pr_auc": 0.88,
        "conformal_coverage": 0.97,
        "review_rate": 0.020,
        "latency_p95_sec": 0.010,
        "alpha": DEFAULT_ALPHA,
    }
    with mlflow.start_run():
        passing = step_quality_gates(metrics=base, champion_pr_auc=0.85, parent_run=True)
        failing = step_quality_gates(
            metrics={**base, "review_rate": 0.021},
            champion_pr_auc=0.85,
            parent_run=True,
        )

    assert passing["gate_review_rate"] is True
    assert passing["all_passed"] is True
    assert failing["gate_review_rate"] is False
    assert failing["all_passed"] is False


def test_coverage_gate_uses_model_alpha(local_mlflow_env):
    metrics = {
        "pr_auc": 0.90,
        "review_rate": 0.01,
        "latency_p95_sec": 0.01,
        "alpha": 0.05,
    }
    with mlflow.start_run():
        at_alpha_05 = step_quality_gates(
            metrics={**metrics, "conformal_coverage": 0.94}, parent_run=True
        )
        at_alpha_02 = step_quality_gates(
            metrics={**metrics, "alpha": 0.02, "conformal_coverage": 0.94}, parent_run=True
        )

    assert at_alpha_05["gate_coverage"] is True
    assert at_alpha_02["gate_coverage"] is False


def test_quality_gates_rejects_regression(local_mlflow_env):
    metrics = {
        "pr_auc": 0.60,
        "conformal_coverage": 0.97,
        "review_rate": 0.015,
        "latency_p95_sec": 0.010,
    }
    with mlflow.start_run():
        gates = step_quality_gates(
            metrics=metrics, champion_pr_auc=0.85, parent_run=True
        )
    assert gates["all_passed"] is False
    assert gates["gate_non_regression"] is False


def test_smoke_pipeline_end_to_end():
    assert run_smoke() is True
