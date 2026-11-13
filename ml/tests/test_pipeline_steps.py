"""Tests for modular ML pipeline steps and CI smoke pipeline (T21)."""

import inspect
import tempfile
from pathlib import Path

import mlflow
import numpy as np
import pytest

import ml.src.pipeline.steps as pipeline_steps
from ml.src.pipeline.smoke import dispose_sqlite_tracking_engine, run_smoke
from ml.src.pipeline.steps import (
    DEFAULT_ALPHA,
    generate_synthetic_data,
    step_calibrate,
    step_conformal,
    step_evaluate_synthetic,
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
        for other in blocks[index + 1 :]:
            assert set(block["trans_num"]).isdisjoint(set(other["trans_num"]))
    assert set(prob_calib["trans_num"]).isdisjoint(set(test["trans_num"]))


def test_step_prepare_real_mode_never_reads_final_test(
    tmp_path: Path, local_mlflow_env, monkeypatch
):
    frame = generate_synthetic_data(n_samples=2000, random_state=7)
    data_dir = tmp_path / "data" / "raw"
    data_dir.mkdir(parents=True)
    data_path = data_dir / "fraudTrain.csv"
    frame.to_csv(data_path, index=False)

    calls: list[str] = []
    real_read = pipeline_steps._read_sparkov_csv

    def spy(path):
        name = Path(path).name
        calls.append(name)
        if "fraudtest" in name.lower():
            raise AssertionError("fraudTest.csv must never be read by the pipeline")
        return real_read(path)

    monkeypatch.setattr(pipeline_steps, "_read_sparkov_csv", spy)
    with mlflow.start_run():
        result = step_prepare(data_path=data_path, parent_run=True)

    assert calls == ["fraudTrain.csv"]
    assert result["test"] is None
    assert result["test_data_hash"] is None
    assert result["source"] == "sparkov"


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
        metrics = step_evaluate_synthetic(
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
    assert (
        metrics["auto_error_rate"] is None or 0.0 <= metrics["auto_error_rate"] <= 1.0
    )
    assert metrics["conformal_coverage_fraud"] > 0.0
    assert metrics["latency_p95_sec"] >= 0.0
    assert metrics["alpha"] == 0.02
    assert conformal["fit_rows"] + conformal["choice_rows"] + conformal[
        "evaluation_rows"
    ] == len(prep["conformal_calib"])


def test_calibrate_and_conformal_use_d46_splits(local_mlflow_env):
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
            parent_run=True,
        )

    assert calibration["fit_rows"] == len(prep["prob_calib"]) // 2
    assert (
        calibration["choice_rows"] == len(prep["prob_calib"]) - calibration["fit_rows"]
    )
    assert conformal["fit_rows"] + conformal["choice_rows"] + conformal[
        "evaluation_rows"
    ] == len(prep["conformal_calib"])
    assert conformal["fit_rows"] > conformal["choice_rows"]
    assert conformal["alpha_selection_status"] in {
        "selected",
        "no_eligible_alpha",
    }
    assert conformal["alpha"] in {0.01, 0.02, 0.03, 0.05, 0.10}
    assert set(conformal["alpha_selection"]) == {"0.01", "0.02", "0.03", "0.05", "0.1"}


def test_quality_gates_boundary_and_alpha_propagation(local_mlflow_env):
    base = {
        "pr_auc": 0.88,
        "conformal_coverage": 0.97,
        "conformal_coverage_legit": 0.98,
        "conformal_coverage_fraud": 0.97,
        "review_rate": 0.020,
        "latency_p95_sec": 0.010,
        "alpha": DEFAULT_ALPHA,
    }
    with mlflow.start_run():
        passing = step_quality_gates(
            metrics=base, champion_pr_auc=0.85, parent_run=True
        )
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
        "conformal_coverage_legit": 0.94,
        "conformal_coverage_fraud": 0.94,
        "review_rate": 0.01,
        "latency_p95_sec": 0.01,
        "alpha": 0.05,
    }
    with mlflow.start_run():
        at_alpha_05 = step_quality_gates(
            metrics=metrics, baseline_pr_auc=0.30, parent_run=True
        )
        at_alpha_02 = step_quality_gates(
            metrics={**metrics, "alpha": 0.02}, baseline_pr_auc=0.30, parent_run=True
        )

    assert at_alpha_05["gate_coverage"] is True
    assert at_alpha_05["gate_coverage_legit"] is True
    assert at_alpha_05["gate_coverage_fraud"] is True
    assert at_alpha_02["gate_coverage"] is False


def test_coverage_gate_rejects_low_fraud_coverage_despite_global_average(
    local_mlflow_env,
):
    metrics = {
        "pr_auc": 0.90,
        "conformal_coverage": 0.995,
        "conformal_coverage_legit": 0.999,
        "conformal_coverage_fraud": 0.90,
        "review_rate": 0.01,
        "latency_p95_sec": 0.01,
        "alpha": 0.02,
    }
    with mlflow.start_run():
        gates = step_quality_gates(
            metrics=metrics, baseline_pr_auc=0.30, parent_run=True
        )

    assert gates["gate_coverage_legit"] is True
    assert gates["gate_coverage_fraud"] is False
    assert gates["gate_coverage"] is False
    assert gates["all_passed"] is False


def test_non_regression_uses_logreg_baseline(local_mlflow_env):
    metrics = {
        "pr_auc": 0.41,
        "conformal_coverage_legit": 0.98,
        "conformal_coverage_fraud": 0.98,
        "review_rate": 0.015,
        "latency_p95_sec": 0.010,
    }
    with mlflow.start_run():
        above = step_quality_gates(
            metrics=metrics, baseline_pr_auc=0.40, parent_run=True
        )
        below = step_quality_gates(
            metrics={**metrics, "pr_auc": 0.39}, baseline_pr_auc=0.40, parent_run=True
        )

    assert above["gate_non_regression"] is True
    assert below["gate_non_regression"] is False


def test_non_regression_is_unverified_without_reference(local_mlflow_env):
    with mlflow.start_run():
        gates = step_quality_gates(metrics={"pr_auc": 0.90}, parent_run=True)

    assert gates["gate_non_regression"] is False
    assert gates["all_passed"] is False


def test_quality_gates_rejects_regression(local_mlflow_env):
    metrics = {
        "pr_auc": 0.60,
        "conformal_coverage": 0.97,
        "conformal_coverage_legit": 0.97,
        "conformal_coverage_fraud": 0.97,
        "review_rate": 0.015,
        "latency_p95_sec": 0.010,
    }
    with mlflow.start_run():
        gates = step_quality_gates(
            metrics=metrics, champion_pr_auc=0.85, parent_run=True
        )
    assert gates["all_passed"] is False
    assert gates["gate_non_regression"] is False


def test_latency_sample_defaults_to_one_thousand():
    default = (
        inspect.signature(step_evaluate_synthetic)
        .parameters["latency_sample_size"]
        .default
    )
    assert default == 1000


def test_auto_error_rate_is_none_when_nothing_is_automatic(local_mlflow_env):
    class AlwaysReviewModel:
        alpha = 0.02
        threshold_legit = 0.40
        threshold_fraud = 0.40

        def batch_probabilities(self, frame):
            return np.full(len(frame), 0.50)

        def predict_one(self, record):
            return {"prediction_set": []}

    frame = generate_synthetic_data(n_samples=20, random_state=5)
    with mlflow.start_run():
        metrics = step_evaluate_synthetic(
            pyfunc_model=AlwaysReviewModel(),
            test_df=frame,
            latency_sample_size=5,
            parent_run=True,
        )

    assert metrics["review_rate"] == 1.0
    assert metrics["auto_error_rate"] is None
    assert metrics["latency_sample_size"] == 5.0


def test_smoke_pipeline_end_to_end():
    assert run_smoke() is True
