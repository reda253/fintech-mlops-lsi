"""T21d: ingest a P2-style candidate joblib and register it as a model version."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import joblib
import mlflow
import pandas as pd
import pytest
from mlflow.tracking import MlflowClient
from sklearn.linear_model import LogisticRegression

from ml.scripts.register_champion import (
    APPROVED_D48_PROTOCOL_SHA256,
    DEFAULT_INPUT_EXAMPLE,
    REQUIRED_GATES,
    _resolve_thresholds,
    _validate_promotion_gates,
    build_model_from_payload,
    promote_version,
    register_candidate,
)
from ml.src.evaluation.final_artifacts import (
    APPROVED_D48_MODEL_SHA256,
    APPROVED_D48_SOURCE_SHA256,
)
from ml.src.model.calibration import (
    CalibratedPriorClassifier,
    IdentityCalibrator,
    conformal_quantile,
)
from ml.src.pipeline.smoke import dispose_sqlite_tracking_engine
from ml.src.pipeline.steps import generate_synthetic_data
from ml.src.preprocessing.pipeline import build_preprocessing_pipeline


class _Run:
    """Minimal MLflow run stand-in for the provenance checks."""

    def __init__(self, tags=None, metrics=None, params=None):
        self.data = SimpleNamespace(
            tags=dict(tags or {}),
            metrics=dict(metrics or {}),
            params=dict(params or {}),
        )


class _FakeClient:
    def __init__(self, runs, versions=None):
        self.runs = runs
        self.versions = versions or {}
        self.aliases = []
        self.version_tags = {}

    def get_run(self, run_id):
        if run_id not in self.runs:
            raise KeyError(f"run {run_id} absent")
        return self.runs[run_id]

    def get_model_version(self, name, version):
        spec = self.versions.get(str(version), {})
        return SimpleNamespace(
            name=name,
            version=str(version),
            tags=spec,
            aliases=list(spec.get("aliases", [])),
        )

    def set_registered_model_alias(self, name, alias, version):
        self.aliases.append((name, alias, str(version)))

    def set_model_version_tag(self, name, version, key, value):
        self.version_tags[(name, str(version), key)] = value


def _promotion_report(tmp_path, model_uri="models:/fraud-detector/1"):
    parent, gates = "run-parent", "run-gates"
    runs = {
        parent: _Run(
            tags={
                "decision_id": "D48",
                "evaluation_source": "final_evaluation_artifacts",
                "candidate_sha256": APPROVED_D48_MODEL_SHA256,
                "model_uri": model_uri,
            }
        ),
        gates: _Run(
            tags={
                "mlflow.parentRunId": parent,
                "mlflow.runName": "6_quality_gates",
            },
            metrics={gate: 1.0 for gate in REQUIRED_GATES},
            params={"quality_gates_passed": "True"},
        ),
    }
    report = {
        "gates": {gate: True for gate in REQUIRED_GATES},
        "provenance": {
            "decision_id": "D48",
            "parent_run_id": parent,
            "gates_run_id": gates,
            "candidate_sha256": APPROVED_D48_MODEL_SHA256,
            "source_sha256": APPROVED_D48_SOURCE_SHA256,
            "protocol_sha256": APPROVED_D48_PROTOCOL_SHA256,
        },
    }
    path = tmp_path / "gate-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path, runs


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
            assert result["alias"] == "challenger"
            assert result["tags"]["alpha"] == "0.02"
            assert result["tags"]["git_commit"] == "p2commit"
            assert result["tags"]["data_sha256"] == "p2hash"
            assert result["tags"]["status"] == "PROVISIONAL"
            assert result["tags"]["source_run_id"] == "a23b25c3a46444e5ae4da4058f729dc8"

            registered = MlflowClient().get_registered_model("fraud-detector-p2-test")
            assert "champion" not in registered.aliases
            assert str(registered.aliases["challenger"]) == "1"

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


def test_promotion_requires_a_complete_gate_report(tmp_path):
    with pytest.raises(ValueError, match="gates"):
        register_candidate(
            tmp_path / "missing.joblib",
            promote=True,
        )

    report = tmp_path / "gates.json"
    report.write_text(
        json.dumps(
            {
                "gates": {
                    "gate_non_regression": True,
                    "gate_coverage_fraud": False,
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Portes manquantes"):
        _validate_promotion_gates(report)


def test_promotion_accepts_a_complete_attributed_report(tmp_path):
    report, runs = _promotion_report(tmp_path)

    validated = _validate_promotion_gates(report, client=_FakeClient(runs))

    assert validated == {gate: True for gate in REQUIRED_GATES}


def test_promotion_refuses_a_report_without_provenance(tmp_path):
    report, runs = _promotion_report(tmp_path)
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload.pop("provenance")
    report.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TypeError, match="Provenance"):
        _validate_promotion_gates(report, client=_FakeClient(runs))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("decision_id", "D47", "D47"),
        ("candidate_sha256", "b" * 64, "candidat"),
        ("source_sha256", "c" * 64, "source"),
        ("protocol_sha256", "d" * 64, "protocole"),
    ],
)
def test_promotion_refuses_a_report_bound_to_something_else(
    tmp_path, field, value, message
):
    report, runs = _promotion_report(tmp_path)
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["provenance"][field] = value
    report.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _validate_promotion_gates(report, client=_FakeClient(runs))


def test_promotion_refuses_an_unknown_gate(tmp_path):
    report, runs = _promotion_report(tmp_path)
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["gates"]["gate_extra"] = True
    report.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Portes inconnues"):
        _validate_promotion_gates(report, client=_FakeClient(runs))


def test_promotion_refuses_a_gates_run_that_is_not_a_child(tmp_path):
    report, runs = _promotion_report(tmp_path)
    runs["run-gates"].data.tags["mlflow.parentRunId"] = "another-parent"
    with pytest.raises(ValueError, match="enfant"):
        _validate_promotion_gates(report, client=_FakeClient(runs))


def test_promotion_refuses_a_gate_not_logged_at_one(tmp_path):
    report, runs = _promotion_report(tmp_path)
    runs["run-gates"].data.metrics["gate_coverage"] = 0.0
    with pytest.raises(ValueError, match="gate_coverage"):
        _validate_promotion_gates(report, client=_FakeClient(runs))


def test_promotion_refuses_a_report_without_the_measured_model(tmp_path):
    report, runs = _promotion_report(tmp_path)
    with pytest.raises(ValueError, match="modele evalue"):
        _validate_promotion_gates(
            report,
            client=_FakeClient(runs),
            expected_model_uri="models:/fraud-detector/2",
        )


def test_promote_version_moves_the_alias_of_the_measured_version(tmp_path):
    report, runs = _promotion_report(tmp_path)
    client = _FakeClient(
        runs,
        versions={"1": {"source_model_sha256": APPROVED_D48_MODEL_SHA256}},
    )

    result = promote_version("fraud-detector", "1", gates_path=report, client=client)

    assert result["aliases"] == {"champion": "1"}
    assert client.aliases == [("fraud-detector", "champion", "1")]
    assert client.version_tags[("fraud-detector", "1", "status")] == "CHAMPION"


def test_promote_version_refuses_a_model_without_its_source_fingerprint(tmp_path):
    report, runs = _promotion_report(tmp_path)
    client = _FakeClient(runs, versions={"1": {}})

    with pytest.raises(ValueError, match="source_model_sha256"):
        promote_version("fraud-detector", "1", gates_path=report, client=client)
    assert client.aliases == []


def test_promote_version_refuses_a_version_that_is_already_champion(tmp_path):
    report, runs = _promotion_report(tmp_path)
    client = _FakeClient(
        runs,
        versions={
            "1": {
                "source_model_sha256": APPROVED_D48_MODEL_SHA256,
                "aliases": ["champion"],
            }
        },
    )

    with pytest.raises(ValueError, match="deja"):
        promote_version("fraud-detector", "1", gates_path=report, client=client)


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
