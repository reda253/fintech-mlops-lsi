"""Registry plumbing tests: lean code staging, signature, tags, alias, load round-trip."""

from __future__ import annotations

import tempfile
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.linear_model import LogisticRegression

from ml.src.model.calibration import IdentityCalibrator
from ml.src.model.fraud_detector import FraudDetectorModel
from ml.src.model.registry import (
    build_input_example,
    register_model,
    stage_model_code,
)
from ml.src.pipeline.smoke import dispose_sqlite_tracking_engine
from ml.src.pipeline.steps import generate_synthetic_data
from ml.src.preprocessing.pipeline import build_preprocessing_pipeline


def _tiny_model() -> tuple[FraudDetectorModel, pd.DataFrame]:
    frame = generate_synthetic_data(n_samples=400, random_state=7).head(300)
    preprocessor = build_preprocessing_pipeline()
    features = preprocessor.fit_transform(frame)
    target = frame["is_fraud"].to_numpy(dtype=int)
    classifier = LogisticRegression(max_iter=1000).fit(features, target)

    model = FraudDetectorModel(
        classifier=classifier,
        preprocessor=preprocessor,
        calibrator=IdentityCalibrator(),
        calibration_method="identity",
        beta=1.0,
        threshold_legit=0.30,
        threshold_fraud=0.30,
        alpha=0.02,
        git_commit="abc123",
        data_sha256="deadbeef",
    )
    return model, build_input_example(frame)


def test_stage_model_code_contains_only_runtime_modules(tmp_path):
    staging = stage_model_code(tmp_path / "staging")
    files = sorted(
        path.relative_to(staging).as_posix()
        for path in staging.rglob("*")
        if path.is_file()
    )
    assert "ml/src/model/fraud_detector.py" in files
    assert "ml/src/model/calibration.py" in files
    assert "ml/src/preprocessing/pipeline.py" in files
    assert "preprocessing/pipeline.py" in files
    assert "model/calibration.py" in files
    assert all(".venv" not in name and "__pycache__" not in name for name in files)
    assert sum((staging / name).stat().st_size for name in files) < 500_000


def test_register_model_tags_alias_and_load_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        uri = f"sqlite:///{(Path(tmp) / 'registry.db').as_posix()}"
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("test-registry")
        try:
            model, input_example = _tiny_model()
            with mlflow.start_run() as run:
                result = register_model(
                    model,
                    input_example,
                    model_name="fraud-detector-test",
                    pipeline_run_id=run.info.run_id,
                    set_champion=True,
                    set_challenger=False,
                )

            assert result["version"] == "1"
            assert result["model_uri"] == "models:/fraud-detector-test/1"

            client = MlflowClient()
            registered = client.get_registered_model("fraud-detector-test")
            assert str(registered.aliases["champion"]) == "1"

            version = client.get_model_version("fraud-detector-test", "1")
            assert version.tags["alpha"] == "0.02"
            assert version.tags["beta"] == "1.0"
            assert version.tags["git_commit"] == "abc123"
            assert version.tags["data_sha256"] == "deadbeef"
            assert version.tags["pipeline_run_id"] == run.info.run_id
            assert version.tags["algorithm"] == "xgboost-calibrated"

            loaded = mlflow.pyfunc.load_model(result["model_uri"])
            assert loaded.metadata.metadata["alpha"] == 0.02
            expected = model.predict(None, input_example).reset_index(drop=True)
            actual = loaded.predict(input_example).reset_index(drop=True)
            pd.testing.assert_frame_equal(expected, actual, check_dtype=False)
            assert actual["alpha"].tolist() == [0.02, 0.02]
            assert set(actual["prediction_set"].iloc[0]).issubset({0, 1})
        finally:
            dispose_sqlite_tracking_engine(uri)


def test_register_model_provisional_keeps_existing_champion():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        uri = f"sqlite:///{(Path(tmp) / 'registry.db').as_posix()}"
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("test-registry-provisional")
        try:
            model, input_example = _tiny_model()
            with mlflow.start_run():
                first = register_model(
                    model,
                    input_example,
                    model_name="fraud-detector-provisional",
                    set_champion=True,
                )
            with mlflow.start_run():
                second = register_model(
                    model,
                    input_example,
                    model_name="fraud-detector-provisional",
                    set_champion=False,
                    set_challenger=True,
                    extra_tags={"status": "PROVISIONAL"},
                )

            assert first["alias"] == "champion"
            assert second["alias"] == "challenger"
            client = MlflowClient()
            registered = client.get_registered_model("fraud-detector-provisional")
            assert str(registered.aliases["champion"]) == "1"
            assert str(registered.aliases["challenger"]) == "2"
            version = client.get_model_version("fraud-detector-provisional", "2")
            assert version.tags["status"] == "PROVISIONAL"
        finally:
            dispose_sqlite_tracking_engine(uri)


def test_fraud_detector_setstate_backfills_old_pickle_attributes():
    model = FraudDetectorModel.__new__(FraudDetectorModel)
    nested_classifier = type(
        "CalibratedPriorClassifier",
        (),
        {
            "calibrator": type("Sigmoid", (), {"method": "sigmoid"})(),
        },
    )()

    model.__setstate__({"classifier": nested_classifier})

    assert model.preprocessor is None
    assert model.calibrator is None
    assert model.beta is None
    assert model.calibration_method == "sigmoid"
    assert model.threshold_legit == 0.50
    assert model.threshold_fraud == 0.50
    assert model.alpha == 0.02
    assert model.model_name == "fraud-detector"
    assert model.git_commit == "unknown"


def test_build_input_example_uses_nested_customer():
    frame = generate_synthetic_data(n_samples=20, random_state=3)
    example = build_input_example(frame)
    assert len(example) == 2
    assert {"transaction_id", "trans_datetime", "amount", "customer"}.issubset(example.columns)
    customer = example["customer"].iloc[0]
    assert {"dob", "gender", "city_pop", "lat", "long", "state"}.issubset(customer)


def test_batch_and_single_probabilities_agree():
    model, _ = _tiny_model()
    frame = generate_synthetic_data(n_samples=30, random_state=11)
    batch = model.batch_probabilities(frame)
    single = np.array([model.calibrated_probability(row) for row in frame.to_dict("records")])
    np.testing.assert_allclose(batch, single, rtol=1e-6, atol=1e-8)
    assert np.all((batch >= 0.0) & (batch <= 1.0))
