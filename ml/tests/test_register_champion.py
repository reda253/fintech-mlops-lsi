"""T21d: ingest a P2-style candidate joblib and register it as a model version."""

from __future__ import annotations

import tempfile
from pathlib import Path

import joblib
import mlflow
import pandas as pd
from sklearn.linear_model import LogisticRegression

from ml.scripts.register_champion import (
    DEFAULT_INPUT_EXAMPLE,
    _resolve_thresholds,
    register_candidate,
)
from ml.src.model.calibration import IdentityCalibrator, conformal_quantile
from ml.src.pipeline.smoke import dispose_sqlite_tracking_engine
from ml.src.pipeline.steps import generate_synthetic_data
from ml.src.preprocessing.pipeline import build_preprocessing_pipeline


def _candidate_payload() -> dict:
    frame = generate_synthetic_data(n_samples=400, random_state=21).head(300)
    preprocessor = build_preprocessing_pipeline()
    features = preprocessor.fit_transform(frame)
    classifier = LogisticRegression(max_iter=1000).fit(
        features, frame["is_fraud"].to_numpy(dtype=int)
    )
    return {
        "preprocessor": preprocessor,
        "classifier": classifier,
        "calibrator": IdentityCalibrator(),
        "calibration_method": "identity",
        "beta": 1.0,
        "threshold_legit": 0.30,
        "threshold_fraud": 0.30,
        "alpha": 0.02,
        "metadata": {
            "git_commit": "p2commit",
            "data_sha256": "p2hash",
            "trained_at": "2026-11-01T10:00:00+00:00",
        },
    }


def test_register_candidate_fixture_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        artifact = root / "candidate_model.joblib"
        joblib.dump(_candidate_payload(), artifact)
        uri = f"sqlite:///{(root / 'registry.db').as_posix()}"
        try:
            result = register_candidate(
                artifact,
                tracking_uri=uri,
                experiment="test-register-champion",
                model_name="fraud-detector-p2-test",
                alpha=0.02,
            )
            assert result["version"] == "1"
            assert result["alias"] == "champion"
            assert result["tags"]["alpha"] == "0.02"
            assert result["tags"]["git_commit"] == "p2commit"
            assert result["tags"]["data_sha256"] == "p2hash"

            loaded = mlflow.pyfunc.load_model(result["model_uri"])
            output = loaded.predict(DEFAULT_INPUT_EXAMPLE)
            assert isinstance(output, pd.DataFrame)
            assert list(output.columns[:3]) == [
                "prediction",
                "fraud_probability",
                "prediction_set",
            ]
            assert output["alpha"].tolist() == [0.02, 0.02]
        finally:
            dispose_sqlite_tracking_engine(uri)


def test_resolve_thresholds_from_scores():
    payload = {
        "conformal_scores": {
            "legit": [0.01, 0.02, 0.03, 0.04, 0.05],
            "fraud": [0.10, 0.20, 0.30, 0.40, 0.50],
        }
    }
    legit, fraud = _resolve_thresholds(payload, alpha=0.2)
    assert legit == conformal_quantile(payload["conformal_scores"]["legit"], 0.2)
    assert fraud == conformal_quantile(payload["conformal_scores"]["fraud"], 0.2)


def test_resolve_thresholds_requires_scores_or_quantiles():
    try:
        _resolve_thresholds({}, alpha=0.02)
    except ValueError as exc:
        assert "threshold_legit" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("ValueError expected")
