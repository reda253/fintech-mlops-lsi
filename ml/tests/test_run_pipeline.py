"""D48 option B: the CLI no longer loads the final test and evaluation is verified."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import mlflow
import pytest

from ml.src.pipeline import run as pipeline_run
from ml.src.pipeline.smoke import dispose_sqlite_tracking_engine


@pytest.fixture
def local_mlflow_env():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "mlflow.db"
        uri = f"sqlite:///{db_path.as_posix()}"
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("test-run-pipeline")
        try:
            yield uri
        finally:
            dispose_sqlite_tracking_engine(uri)


def test_cli_rejects_test_path(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["run.py", "--test-path", "data/raw/fraudTest.csv"],
    )
    with pytest.raises(SystemExit):
        pipeline_run.main()


def test_real_training_without_evaluation_cannot_register(tmp_path: Path):
    with pytest.raises(ValueError, match="evaluation D48"):
        pipeline_run.run_pipeline(
            mode="full",
            data_path=tmp_path / "fraudTrain.csv",
            register=True,
        )


def test_evaluation_dir_is_reserved_to_evaluate_mode(tmp_path: Path):
    with pytest.raises(ValueError, match="reserve a --mode evaluate"):
        pipeline_run.run_pipeline(
            mode="full",
            data_path=tmp_path / "fraudTrain.csv",
            evaluation_dir=tmp_path,
            register=False,
        )


def test_evaluate_mode_requires_directory_and_candidate_hash():
    with pytest.raises(ValueError, match="--evaluation-dir"):
        pipeline_run.run_pipeline(mode="evaluate")
    with pytest.raises(ValueError, match="--candidate-sha256"):
        pipeline_run.run_pipeline(mode="evaluate", evaluation_dir=Path("d48"))


def test_evaluate_mode_loads_the_frozen_model_and_logs_gates(
    local_mlflow_env, tmp_path: Path, monkeypatch
):
    class FakeModel:
        alpha = 0.02
        threshold_legit = 0.5
        threshold_fraud = 0.6

    calls: dict[str, object] = {}

    def fake_load(uri: str):
        calls["uri"] = uri
        return FakeModel()

    def fake_evaluate(
        *, pyfunc_model, evaluation_dir, expected_model_sha256, parent_run
    ):
        calls["directory"] = Path(evaluation_dir)
        calls["sha256"] = expected_model_sha256
        return {
            "alpha": 0.02,
            "pr_auc": 0.90,
            "conformal_coverage_legit": 0.99,
            "conformal_coverage_fraud": 0.99,
            "review_rate": 0.01,
            "latency_p95_sec": 0.01,
        }

    monkeypatch.setattr(pipeline_run, "_load_python_model", fake_load)
    monkeypatch.setattr(pipeline_run, "step_evaluate", fake_evaluate)

    directory = tmp_path / "d48"
    success = pipeline_run.run_pipeline(
        mode="evaluate",
        tracking_uri=local_mlflow_env,
        experiment="test-run-pipeline",
        evaluation_dir=directory,
        candidate_sha256="a" * 64,
        model_uri="models:/fake/1",
        baseline_pr_auc=0.50,
    )

    assert success is True
    assert calls == {
        "uri": "models:/fake/1",
        "directory": directory,
        "sha256": "a" * 64,
    }
