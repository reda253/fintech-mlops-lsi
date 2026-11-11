"""Tests synthétiques de l'évaluation ; aucun apprentissage."""

import json

import numpy as np
import pytest

from ml.scripts import evaluate_final_candidate as evaluation


class FakePreprocessor:
    def transform(self, X):
        return np.arange(len(X)).reshape(-1, 1)

    def fit(self, *args, **kwargs):
        raise AssertionError("aucun réajustement autorisé")


class FakeClassifier:
    def predict_proba(self, X):
        values = np.resize(np.array([0.1, 0.8, 0.4, 0.95]), len(X))
        return np.column_stack((1 - values, values))

    def fit(self, *args, **kwargs):
        raise AssertionError("aucun réentraînement autorisé")


class FakeCandidate:
    alpha = 0.02
    threshold_legit = 0.5
    threshold_fraud = 0.6
    preprocessor = FakePreprocessor()
    classifier = FakeClassifier()


def reference():
    return {
        "selected_alpha": 0.02,
        "alpha_results": [
            {"alpha": 0.02, "status": "eligible", "quantiles": {"0": 0.5, "1": 0.6}}
        ],
    }


def test_metrics_and_group_counts_without_fit():
    result, groups = evaluation.evaluate(FakeCandidate(), evaluation.synthetic_data())
    assert result["n_transactions"] == 4
    assert result["review_rate"] == pytest.approx(0.25)
    assert result["automatic_error_rate"] == pytest.approx(1 / 3)
    assert result["coverage_by_class"] == {"0": 0.5, "1": 1.0}
    assert result["fraud_coverage_floor"] == pytest.approx(0.96)
    assert result["review_capacity_met"] is False
    assert set(groups[groups["attribute"] == "age"]["group"]) == set(
        evaluation.AGE_LABELS
    )
    assert (
        int(
            groups.loc[
                (groups["attribute"] == "age") & (groups["group"] == "0-25"), "n"
            ].iloc[0]
        )
        == 1
    )
    assert groups.loc[groups["attribute"] == "gender", "n"].sum() == 4


def test_rejects_changed_candidate_threshold():
    bad = reference()
    bad["alpha_results"][0]["quantiles"]["0"] = 0.51
    with pytest.raises(ValueError, match="Seuils"):
        evaluation.validate_candidate(FakeCandidate(), bad)


def test_synthetic_cli_writes_only_aggregate_outputs(tmp_path, monkeypatch):
    model = tmp_path / "model.joblib"
    model.write_bytes(b"synthetic")
    ref = tmp_path / "reference.json"
    ref.write_text(json.dumps(reference()), encoding="utf-8")
    output = tmp_path / "results"
    monkeypatch.setattr(evaluation.joblib, "load", lambda path: FakeCandidate())
    assert (
        evaluation.main(
            [
                "--model",
                str(model),
                "--reference",
                str(ref),
                "--output-dir",
                str(output),
                "--synthetic",
                "--no-mlflow",
            ]
        )
        == 0
    )
    assert {x.name for x in output.iterdir()} == {
        "final_metrics.json",
        "final_report.md",
        "fairness_groups.csv",
        "bootstrap_intervals.json",
        "artifact_manifest.json",
        "predictions.csv",
    }
    import pandas as pd

    predictions = pd.read_csv(output / "predictions.csv")
    assert list(predictions.columns) == [
        "label",
        "fraud_probability",
        "include_0",
        "include_1",
    ]
    assert predictions["label"].tolist() == [0, 0, 1, 1]
    assert predictions["fraud_probability"].tolist() == pytest.approx(
        [0.1, 0.8, 0.4, 0.95]
    )
    assert predictions[["include_0", "include_1"]].values.tolist() == [
        [1, 0],
        [0, 1],
        [1, 1],
        [0, 1],
    ]
    result = json.loads((output / "final_metrics.json").read_text(encoding="utf-8"))
    assert result["scope"] == "synthetic_only"
    assert result["model_status"] == "provisional"
    assert result["overall"]["n_transactions"] == 4


def test_final_mode_requires_confirmation_before_model_or_data_reads(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        evaluation.joblib, "load", lambda path: pytest.fail("chargement interdit")
    )
    with pytest.raises(SystemExit):
        evaluation.main(
            [
                "--model",
                str(tmp_path / "not-loaded"),
                "--reference",
                str(tmp_path / "not-read"),
                "--output-dir",
                str(tmp_path / "output"),
                "--source",
                str(tmp_path / "fraudTest.csv"),
            ]
        )


def test_journal_reservation_tracks_hash_and_reason(tmp_path):
    journal = tmp_path / "central.jsonl"
    digest = "a" * 64
    model_hash = "b" * 64
    first = evaluation.reserve_source(journal, "first.csv", digest, model_hash, None)
    with pytest.raises(ValueError, match="déjà évaluée"):
        evaluation.reserve_source(journal, "copy.csv", digest, model_hash, None)
    second = evaluation.reserve_source(
        journal, "copy.csv", digest, model_hash, "motif synthétique"
    )
    entries = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()
    ]
    assert first != second and len(entries) == 2
    assert entries[1]["reason"] == "motif synthétique"
    assert entries[1]["source_sha256"] == digest
    assert entries[1]["source_name"] == "copy.csv"
    assert entries[1]["model_sha256"] == model_hash


def test_previous_journal_format_is_recognized(tmp_path):
    journal = tmp_path / "central.jsonl"
    journal.write_text(
        json.dumps({"status": "completed", "source_sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="déjà évaluée"):
        evaluation.reserve_source(journal, "renamed.csv", "a" * 64, "b" * 64, None)


def test_age_groups_use_exact_eda_boundaries():
    ages = [0, 25, 26, 35, 36, 45, 46, 55, 56, 65, 66, 120]
    template = evaluation.synthetic_data().iloc[0].to_dict()
    rows = []
    for i, age in enumerate(ages):
        rows.append({**template, "dob": f"{2020 - age:04d}-06-01", "is_fraud": i % 2})
    import pandas as pd

    _, groups = evaluation.evaluate(FakeCandidate(), pd.DataFrame(rows))
    counts = groups[groups["attribute"] == "age"].set_index("group")["n"].to_dict()
    assert counts == {label: 2 for label in evaluation.AGE_LABELS}


def test_weighted_metrics_match_sklearn_with_ties_and_weights():
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    from ml.scripts.final_metrics import weighted_metrics

    y = np.array([0, 1, 0, 1, 0])
    p = np.array([0.2, 0.8, 0.8, 0.4, 0.1])
    weights = np.array([1, 2, 3, 4, 5])
    members = np.column_stack((p <= 0.5, p >= 0.4))
    result = weighted_metrics(y, p, members, weights)
    assert result["pr_auc"] == pytest.approx(
        average_precision_score(y, p, sample_weight=weights)
    )
    assert result["roc_auc"] == pytest.approx(
        roc_auc_score(y, p, sample_weight=weights)
    )
    assert result["brier_score"] == pytest.approx(
        brier_score_loss(y, p, sample_weight=weights)
    )
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        log_loss,
        matthews_corrcoef,
        precision_score,
        recall_score,
    )

    pred = p >= 0.5
    assert result["accuracy"] == pytest.approx(
        accuracy_score(y, pred, sample_weight=weights)
    )
    assert result["precision"] == pytest.approx(
        precision_score(y, pred, sample_weight=weights)
    )
    assert result["recall"] == pytest.approx(
        recall_score(y, pred, sample_weight=weights)
    )
    assert result["f1"] == pytest.approx(f1_score(y, pred, sample_weight=weights))
    assert result["mcc"] == pytest.approx(
        matthews_corrcoef(y, pred, sample_weight=weights)
    )
    assert result["log_loss"] == pytest.approx(
        log_loss(y, p, sample_weight=weights, labels=[0, 1])
    )


def test_bootstrap_reproducible_and_group_without_fraud():
    from ml.scripts.final_metrics import bootstrap_intervals

    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.8, 0.4, 0.95])
    members = np.column_stack((p <= 0.5, p >= 0.4))
    masks = {"no_fraud": np.array([True, True, False, False])}
    a = bootstrap_intervals(y, p, members, masks, resamples=100, seed=42)
    b = bootstrap_intervals(y, p, members, masks, resamples=100, seed=42)
    assert a == b
    assert a["groups"]["no_fraud"]["recall"]["ci95"] is None
    assert a["groups"]["no_fraud"]["recall"]["valid_resamples"] == 0
    assert a["parameters"]["resamples"] == 100


def test_quality_gates_fail_closed_without_reference():
    overall, _ = evaluation.evaluate(FakeCandidate(), evaluation.synthetic_data())
    gates = evaluation.quality_gates(
        overall, {"status": "measured", "p95_ms": 50.0}, None, None
    )
    assert gates["coverage_by_class"]["status"] == "FAIL"
    assert gates["review_capacity"]["status"] == "FAIL"
    assert gates["latency"]["status"] == "FAIL"
    assert gates["registry_smoke"]["status"] == "UNVERIFIED"
    assert gates["non_regression"]["status"] == "UNVERIFIED"


def test_mlflow_failure_then_republish_without_source_read(tmp_path, monkeypatch):
    import types

    from ml.scripts import final_tracking

    model = tmp_path / "model.joblib"
    model.write_bytes(b"synthetic")
    ref = tmp_path / "reference.json"
    ref.write_text(json.dumps(reference()), encoding="utf-8")
    output = tmp_path / "saved"
    monkeypatch.setattr(evaluation.joblib, "load", lambda path: FakeCandidate())
    assert (
        evaluation.main(
            [
                "--model",
                str(model),
                "--reference",
                str(ref),
                "--output-dir",
                str(output),
                "--synthetic",
                "--no-mlflow",
            ]
        )
        == 0
    )
    monkeypatch.setattr(
        final_tracking, "get_tracking_uri", lambda value: "http://localhost:5000"
    )

    class FakeRun:
        info = types.SimpleNamespace(run_id="synthetic-run")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeMLflow:
        fail = True

        def set_tracking_uri(self, uri):
            pass

        def set_experiment(self, name):
            pass

        def start_run(self, **kwargs):
            return FakeRun()

        def set_tags(self, tags):
            pass

        def log_params(self, params):
            pass

        def log_metrics(self, metrics):
            if self.fail:
                raise OSError("simulated outage")

        def log_artifact(self, path):
            pass

    fake = FakeMLflow()
    monkeypatch.setitem(__import__("sys").modules, "mlflow", fake)
    failed = final_tracking.publish_saved(output)
    assert failed["status"] == "failed" and failed["run_id"] == "synthetic-run"
    monkeypatch.setattr(
        evaluation.joblib, "load", lambda path: pytest.fail("model must not be read")
    )
    monkeypatch.setattr(
        evaluation.pd,
        "read_csv",
        lambda *a, **k: pytest.fail("source must not be read"),
    )
    fake.fail = False
    assert evaluation.main(["--republish", str(output)]) == 0
    saved = json.loads((output / "mlflow_status.json").read_text(encoding="utf-8"))
    assert saved["status"] == "published" and saved["run_id"] == "synthetic-run"


def test_latency_measurement_uses_1000_calls_without_fit():
    class PredictOnly:
        def __init__(self):
            self.calls = 0

        def predict_one(self, record):
            self.calls += 1
            return {"prediction_set": [0]}

    model = PredictOnly()
    result = evaluation.measure_latency(model)
    assert model.calls == 1020
    assert result["calls"] == 1000 and result["warmups"] == 20
    assert len(result["p95_ci95_ms"]) == 2
    assert result["p95_ci95_ms"][0] <= result["p95_ci95_ms"][1]
