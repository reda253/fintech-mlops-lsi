"""T21d: ingest a P2-style candidate joblib and register it as a model version."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import joblib
import mlflow
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.linear_model import LogisticRegression

from ml.scripts.register_champion import (
    DEFAULT_INPUT_EXAMPLE,
    _resolve_thresholds,
    build_model_from_payload,
    register_candidate,
)
from ml.src.model.calibration import (
    CalibratedPriorClassifier,
    IdentityCalibrator,
    conformal_quantile,
)
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
        metadata_path = root / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "status": "PROVISIONAL",
                    "run_id": "a23b25c3a46444e5ae4da4058f729dc8",
                    "alpha": 0.02,
                    "beta": 1.0,
                    "git_commit": "p2commit",
                    "data_sha256": "p2hash",
                }
            ),
            encoding="utf-8",
        )
        uri = f"sqlite:///{(root / 'registry.db').as_posix()}"
        try:
            result = register_candidate(
                artifact,
                tracking_uri=uri,
                experiment="test-register-champion",
                model_name="fraud-detector-p2-test",
                alpha=0.02,
                metadata_path=metadata_path,
            )
            assert result["version"] == "1"
            assert result["alias"] is None
            assert result["tags"]["alpha"] == "0.02"
            assert result["tags"]["git_commit"] == "p2commit"
            assert result["tags"]["data_sha256"] == "p2hash"
            assert result["tags"]["status"] == "PROVISIONAL"
            assert result["tags"]["source_run_id"] == "a23b25c3a46444e5ae4da4058f729dc8"

            registered = MlflowClient().get_registered_model("fraud-detector-p2-test")
            assert "champion" not in registered.aliases

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


def test_build_model_from_p2_nested_wrapper():
    payload = _candidate_payload()
    nested = CalibratedPriorClassifier(
        classifier=payload["classifier"],
        beta=0.25,
        calibrator=payload["calibrator"],
    )
    p2_model = SimpleNamespace(
        preprocessor=payload["preprocessor"],
        classifier=nested,
        threshold_legit=0.20,
        threshold_fraud=0.80,
        alpha=0.02,
        feature_names=["feature"],
    )

    model = build_model_from_payload(p2_model)

    assert model.classifier is payload["classifier"]
    assert model.calibrator is payload["calibrator"]
    assert model.beta == 0.25
    assert model.threshold_legit == 0.20
    assert model.threshold_fraud == 0.80
    assert model.alpha == 0.02
    assert model.feature_names == ["feature"]


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
