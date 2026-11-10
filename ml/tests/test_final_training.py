"""Tests synthétiques du workflow final ; aucune source Sparkov lue."""

import json
import subprocess
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from ml.src.final import train_final as final


class TinyPreprocessor:
    def fit_transform(self, X, y):
        self.fit_rows = len(X)
        return self.transform(X)

    def transform(self, X):
        return X[["amt"]].to_numpy(dtype=float)

    def get_feature_names_out(self):
        return np.array(["amt"])


class TinyClassifier:
    def fit(self, X, y):
        self.fit_rows = len(X)
        return self

    def predict_proba(self, X):
        fraud = np.clip(X[:, 0], 0.001, 0.999)
        return np.column_stack((1 - fraud, fraud))


def synthetic_splits():
    sizes = (120, 120, 400)
    frames = []
    start = 0
    for size in sizes:
        labels = np.arange(size) % 2
        frame = pd.DataFrame(
            {
                "trans_date_trans_time": pd.date_range(
                    "2019-01-01", periods=size, freq="min"
                )
                + pd.Timedelta(minutes=start),
                "is_fraud": labels,
                "amt": np.where(labels == 1, 0.9, 0.1),
            },
            index=np.arange(start, start + size),
        )
        frames.append(frame)
        start += size
    return dict(
        zip(
            ("development", "probability_calibration", "conformal_calibration"),
            frames,
            strict=True,
        )
    )


def test_mondrian_finite_sample_quantiles_and_insufficient_class():
    p = np.r_[np.arange(100) / 1000, 1 - np.arange(100) / 1000]
    y = np.r_[np.zeros(100, dtype=int), np.ones(100, dtype=int)]
    q = final.mondrian_quantiles(p, y, 0.01)
    assert q == {0: 0.099, 1: pytest.approx(0.099)}
    assert final.prediction_membership(np.array([0.01, 0.99]), q).tolist() == [
        [True, False],
        [False, True],
    ]
    with pytest.raises(ValueError, match="Quantile fini impossible"):
        final.mondrian_quantiles(
            p[:20], np.r_[np.zeros(10, dtype=int), np.ones(10, dtype=int)], 0.01
        )


def test_review_and_automatic_error_exclude_ambiguous():
    members = np.array([[True, False], [False, True], [True, True], [False, False]])
    result = final.evaluate_sets(members, np.array([0, 0, 1, 1]))
    assert result["review_rate"] == 0.5
    assert result["automation_rate"] == 0.5
    assert result["automatic_error_rate"] == 0.5
    assert result["coverage_by_class"] == {"0": 0.5, "1": 0.5}


def test_internal_chronology_moves_shared_boundary_right():
    frame = synthetic_splits()["conformal_calibration"].copy()
    date = "trans_date_trans_time"
    frame.iloc[199, frame.columns.get_loc(date)] = frame.iloc[200][date]
    parts = final.chronological_parts(frame, (2, 1, 1))
    assert [len(part) for part in parts] == [201, 99, 100]
    assert parts[0][date].max() < parts[1][date].min()
    assert parts[1][date].max() < parts[2][date].min()
    assert sum(map(len, parts)) == len(frame)


def test_nonmonotonic_review_grid_finds_new_alpha():
    probabilities = np.linspace(0, 1, 101)
    thresholds = {0.01: 0.7, 0.02: 0.5, 0.03: 0.48, 0.05: 0.3, 0.10: 0.2}
    rows = [
        {
            "alpha": alpha,
            "status": "eligible",
            "selection_review_rate": final.review_rate(
                final.prediction_membership(probabilities, {0: q, 1: q})
            ),
        }
        for alpha, q in thresholds.items()
    ]
    assert rows[0]["selection_review_rate"] > rows[1]["selection_review_rate"]
    assert rows[-1]["selection_review_rate"] > rows[1]["selection_review_rate"]
    assert (
        final.select_alpha([row for row in rows if row["alpha"] in (0.01, 0.05, 0.10)])
        is None
    )
    assert final.select_alpha(rows)["alpha"] == 0.02


def test_integration_uses_disjoint_zones_and_calibrated_artifact(tmp_path, monkeypatch):
    splits = synthetic_splits()
    prep = TinyPreprocessor()
    classifier = TinyClassifier()
    monkeypatch.setattr(final, "build_preprocessing_pipeline", lambda: prep)
    monkeypatch.setattr(final, "build_model", lambda name, params, seed: classifier)
    report = final.run_workflow(splits, {}, tmp_path / "output")
    assert prep.fit_rows == len(splits["development"])
    assert classifier.fit_rows == len(splits["development"])
    assert report["internal_rows"] == {
        "prob_fit": 60,
        "prob_choice": 60,
        "conf_fit": 200,
        "conf_choice": 100,
        "conf_eval": 100,
    }
    assert report["selected_alpha"] == 0.01
    assert report["capacity_met"]
    assert (tmp_path / "output" / "candidate_model.joblib").is_file()
    assert (tmp_path / "output" / "report.md").is_file()
    assert (tmp_path / "output" / "reliability.png").is_file()
    assert (tmp_path / "output" / "alpha_review.png").is_file()
    assert report["model_status"] == "provisional"
    for method in report["calibration_metrics"]["probability_choice_methods"].values():
        assert 0 <= method["ece"] <= 1
        assert 0 <= method["brier"] <= 1


def test_no_alpha_meets_capacity_does_not_package(tmp_path, monkeypatch):
    splits = synthetic_splits()
    monkeypatch.setattr(final, "build_preprocessing_pipeline", TinyPreprocessor)
    monkeypatch.setattr(
        final, "build_model", lambda name, params, seed: TinyClassifier()
    )
    monkeypatch.setattr(final, "review_rate", lambda members: 0.5)
    report = final.run_workflow(splits, {}, tmp_path / "output")
    assert report["selected_alpha"] is None
    assert not report["capacity_met"]
    assert not (tmp_path / "output" / "candidate_model.joblib").exists()


def test_rejects_extra_zone_before_fit(tmp_path, monkeypatch):
    splits = synthetic_splits()
    splits["test"] = splits["development"].copy()
    monkeypatch.setattr(final, "build_model", lambda *args: pytest.fail("fit reached"))
    with pytest.raises(ValueError, match="Trois zones exactes"):
        final.run_workflow(splits, {}, tmp_path / "output")


def test_cli_with_real_pipeline_on_synthetic_csv(tmp_path):
    # Development is imbalanced; later periods have enough frauds for all ranks.
    n = 4000
    i = np.arange(n)
    labels = np.where(i < 2800, i % 30 == 0, i % 2 == 0)
    frame = pd.DataFrame(
        {
            "trans_date_trans_time": pd.date_range(
                "2019-01-01", periods=n, freq="min"
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "dob": "1980-01-01",
            "amt": np.where(labels, 900.0, 5.0),
            "category": "shopping_net",
            "gender": "F",
            "state": "NY",
            "city_pop": 10000,
            "lat": 40.0,
            "long": -74.0,
            "merch_lat": 40.0,
            "merch_long": -74.0,
            "trans_num": i,
            "cc_num": 1,
            "is_fraud": labels.astype(int),
        }
    )
    source = tmp_path / "data/raw/fraudTrain.csv"
    source.parent.mkdir(parents=True)
    frame.to_csv(source, index=False)
    output = tmp_path / "report"
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "ml.src.final.train_final",
            "--local-report-only",
            "--source",
            str(source),
            "--best-params",
            "configs/best_params.json",
            "--output-dir",
            str(output),
            "--journal",
            str(tmp_path / "launches.jsonl"),
        ],
        cwd=root,
        check=True,
    )
    report = json.loads((output / "results.json").read_text(encoding="utf8"))
    events = [
        json.loads(line)
        for line in (tmp_path / "launches.jsonl").read_text().splitlines()
    ]
    assert [e["event"] for e in events] == [
        "launch_started",
        "source_read_started",
        "source_read_completed",
        "choice_block_metrics",
        "choice_block_metrics",
        "choice_block_metrics",
        "choice_block_metrics",
        "choice_block_metrics",
        "launch_completed",
    ]
    assert events[1]["zones"] == list(final.ZONE_NAMES)
    assert events[2]["rows"] == {
        "development": 2800,
        "probability_calibration": 600,
        "conformal_calibration": 600,
    }
    for event, row in zip(events[3:8], report["alpha_results"], strict=True):
        assert event["alpha"] == row["alpha"]
        assert event["fraud_count"] == row["choice"]["fraud_count"] == 75
        assert event["class_counts"] == row["choice"]["class_counts"]
        assert event["coverage_by_class"] == row["choice"]["coverage_by_class"]
        assert event["covered_counts"] == row["choice"]["covered_counts"]
    assert report["beta"] == pytest.approx(940 / 2706)
    assert report["selected_alpha"] == 0.01
    assert [row["alpha"] for row in report["alpha_results"]] == list(final.ALPHAS)
    model = joblib.load(output / "candidate_model.joblib")
    prediction = model.predict_one(frame.iloc[-2].to_dict())
    assert prediction["prediction_set"] == [1]
    assert prediction["alpha"] == model.alpha == report["selected_alpha"]
    assert model.threshold_fraud == report["alpha_results"][0]["quantiles"]["1"]
    for row in report["alpha_results"]:
        gate = row["fraud_coverage_gate"]
        assert gate["floor"] == pytest.approx(1 - row["alpha"] - 0.02)
        assert gate["met"] == (gate["observed"] >= gate["floor"])
        assert "automatic_error_rate" in row["evaluation"]
    code = (
        "import sys, joblib; "
        "sys.path.insert(0, 'ml-service'); "
        "model = joblib.load(sys.argv[1]); "
        "assert 'ml.src.final.train_final' not in sys.modules; "
        "assert type(model.classifier).__module__ == 'ml.src.model.calibration'; "
        "from app.predictor import RealPredictor; "
        "service = RealPredictor(model_instance=model); "
        "service.warmup(); assert service.is_ready(); "
        "import mlflow.pyfunc; "
        "mlflow.pyfunc.save_model(path=sys.argv[2], python_model=model, pip_requirements=[]); "
        "loaded_service = RealPredictor(model_uri=sys.argv[2]); "
        "loaded_service.warmup(); assert loaded_service.is_ready(); "
        "assert 'ml.src.final.train_final' not in sys.modules"
    )
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            code,
            str(output / "candidate_model.joblib"),
            str(tmp_path / "serving_model"),
        ],
        cwd=root,
        check=True,
    )


def test_overlapping_probability_and_conformal_periods_rejected(tmp_path):
    zones = synthetic_splits()
    prob = zones["probability_calibration"].copy()
    prob.loc[prob.index[-1], "trans_date_trans_time"] = zones[
        "conformal_calibration"
    ].iloc[0]["trans_date_trans_time"]
    zones["probability_calibration"] = prob
    with pytest.raises(ValueError, match="Frontières"):
        final.run_workflow(zones, {}, tmp_path / "output")


def test_only_disjoint_corrected_scores_reach_calibration_and_selection(
    tmp_path, monkeypatch
):
    splits = synthetic_splits()
    dev = splits["development"]
    dev["is_fraud"] = (np.arange(len(dev)) % 40 == 0).astype(int)
    for zone in splits.values():
        zone["amt"] = (zone.index.to_numpy() + 1) / 1000
    monkeypatch.setattr(final, "build_preprocessing_pipeline", TinyPreprocessor)
    monkeypatch.setattr(final, "build_model", lambda *args: TinyClassifier())
    seen = {}
    original_fit, original_choice = final.fit_calibrators, final.choose_calibrator

    def fit(p, y):
        seen["fit"] = p.copy()
        return original_fit(p, y)

    def choice(models, p, y):
        seen["choice"] = p.copy()
        return original_choice(models, p, y)

    monkeypatch.setattr(final, "fit_calibrators", fit)
    monkeypatch.setattr(final, "choose_calibrator", choice)
    result = final.run_workflow(splits, {}, tmp_path / "out")
    assert result["beta"] == pytest.approx(30 / 117)
    raw = splits["probability_calibration"]["amt"].to_numpy()
    expected = final.correct_proba(raw, 30 / 117)
    np.testing.assert_allclose(seen["fit"], expected[:60])
    np.testing.assert_allclose(seen["choice"], expected[60:])


@pytest.mark.parametrize(
    "key,value",
    [
        ("alphas", [0.05]),
        ("probability_weights", [2, 1]),
        ("conformal_weights", [1, 1, 1]),
        ("xgb_params", {"max_depth": 2}),
        ("outer_fractions", [0.8, 0.1, 0.1]),
    ],
)
def test_changed_protocol_requires_explicit_journal_entry(tmp_path, key, value):
    journal = tmp_path / "audit.jsonl"
    source = tmp_path / "data/raw/fraudTrain.csv"
    original = final.protocol_snapshot({}, "sha")
    with final.launch_audit(journal, source, original):
        pass
    before = journal.read_bytes()
    changed = {**original, key: value}
    with (
        pytest.raises(ValueError, match="protocol-change-reason"),
        final.launch_audit(journal, source, changed),
    ):
        pytest.fail("changed protocol accepted without explicit decision")
    assert journal.read_bytes() == before
    with final.launch_audit(journal, source, changed, "Décision explicite de test"):
        pass
    events = [
        json.loads(line) for line in journal.read_text(encoding="utf8").splitlines()
    ]
    assert events[2]["event"] == "protocol_change_acknowledged"
    assert events[2]["replacement"]["protocol"][key] == value
    assert events[3]["event"] == "launch_started"
    assert not journal.with_suffix(".jsonl.lock").exists()


def test_journal_logs_failure_and_prevents_concurrent_launch(tmp_path):
    journal = tmp_path / "audit.jsonl"
    source = tmp_path / "data/raw/fraudTrain.csv"
    protocol = final.protocol_snapshot({}, "sha")
    with (
        pytest.raises(RuntimeError, match="synthetic failure"),
        final.launch_audit(journal, source, protocol),
    ):
        with (
            pytest.raises(ValueError, match="verrou"),
            final.launch_audit(journal, source, protocol),
        ):
            pytest.fail("concurrent run accepted")
        raise RuntimeError("synthetic failure")
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    assert events[-1]["event"] == "launch_failed"
    with final.launch_audit(journal, source, protocol):
        pass
    assert not journal.with_suffix(".jsonl.lock").exists()


@pytest.mark.parametrize("name", ["fraudTest.csv", "calibration.csv"])
def test_final_loader_rejects_forbidden_sources_before_read(
    tmp_path, monkeypatch, name
):
    monkeypatch.setattr(
        final, "load_training_dataset", lambda *a: pytest.fail("source read")
    )
    monkeypatch.setattr(Path, "open", lambda *a, **kw: pytest.fail("file read"))
    with pytest.raises(ValueError, match="Source interdite"):
        final.load_final_zones(tmp_path / "data/raw" / name, lambda *a, **kw: None)


def test_journal_cannot_be_stored_in_repository():
    with (
        pytest.raises(ValueError, match="hors du dépôt"),
        final.launch_audit(
            final.ROOT / "not-created.jsonl", final.ROOT / "data/raw/fraudTrain.csv", {}
        ),
    ):
        pytest.fail("journal accepted inside repository")


def test_ece_and_brier_known_values():
    result = final.calibration_metrics(np.array([0, 1]), np.array([0.2, 0.8]))
    assert result == {"brier": pytest.approx(0.04), "ece": pytest.approx(0.2)}


@pytest.mark.parametrize("alpha,minimum", [(0.01, 99), (0.05, 19), (0.10, 9)])
def test_exact_minimum_class_counts_for_finite_quantile(alpha, minimum):
    for n in (minimum - 1, minimum):
        labels = np.repeat([0, 1], n)
        probabilities = np.repeat([0.1, 0.9], n)
        if n < minimum:
            with pytest.raises(ValueError, match="Quantile fini impossible"):
                final.mondrian_quantiles(probabilities, labels, alpha)
        else:
            assert final.mondrian_quantiles(probabilities, labels, alpha) == {
                0: pytest.approx(0.1),
                1: pytest.approx(0.1),
            }


def test_coverage_summary_known_counts_and_missing_class():
    y = np.array([0, 0, 1, 1, 1])
    members = np.array(
        [[True, False], [False, True], [True, True], [False, False], [False, True]]
    )
    result = final.coverage_summary(members, y)
    assert result == {
        "fraud_count": 3,
        "class_counts": {"0": 2, "1": 3},
        "covered_counts": {"0": 1, "1": 2},
        "coverage_by_class": {"0": 0.5, "1": 2 / 3},
    }
    absent = final.coverage_summary(members[:2], np.array([0, 0]))
    assert absent["fraud_count"] == 0
    assert absent["coverage_by_class"]["1"] is None
    unavailable = final.coverage_summary(None, y)
    assert unavailable["fraud_count"] == 3
    assert unavailable["covered_counts"] == {"0": None, "1": None}
    assert unavailable["coverage_by_class"] == {"0": None, "1": None}


def test_choice_labels_only_change_reporting_not_selected_alpha(tmp_path, monkeypatch):
    monkeypatch.setattr(final, "build_preprocessing_pipeline", TinyPreprocessor)
    monkeypatch.setattr(final, "build_model", lambda *args: TinyClassifier())
    original = synthetic_splits()
    changed = {k: v.copy() for k, v in original.items()}
    conf = changed["conformal_calibration"]
    idx = conf.index[200:300]
    conf.loc[idx, "is_fraud"] = 1 - conf.loc[idx, "is_fraud"]
    before = final.run_workflow(original, {}, tmp_path / "before")
    after = final.run_workflow(changed, {}, tmp_path / "after")
    assert before["selected_alpha"] == after["selected_alpha"] == 0.01
    for a, b in zip(before["alpha_results"], after["alpha_results"], strict=True):
        assert a["quantiles"] == b["quantiles"]
        assert a["selection_review_rate"] == b["selection_review_rate"]
        assert a["choice"]["coverage_by_class"] == {"0": 1.0, "1": 1.0}
        assert b["choice"]["coverage_by_class"] == {"0": 0.0, "1": 0.0}
    assert "couverture choix 1" in (tmp_path / "before/report.md").read_text(
        encoding="utf-8"
    )


def test_inapplicable_alpha_still_records_choice_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(final, "build_preprocessing_pipeline", TinyPreprocessor)
    monkeypatch.setattr(final, "build_model", lambda *args: TinyClassifier())

    def unavailable(*args):
        raise ValueError("Quantile fini impossible : cas synthétique")

    monkeypatch.setattr(final, "mondrian_quantiles", unavailable)
    report = final.run_workflow(synthetic_splits(), {}, tmp_path / "output")
    events = []
    final.record_choice_metrics(
        report, lambda event, **details: events.append((event, details))
    )
    assert len(events) == len(final.ALPHAS)
    assert [e[1]["alpha"] for e in events] == list(final.ALPHAS)
    for event, details in events:
        assert event == "choice_block_metrics"
        assert details["status"] == "inapplicable"
        assert details["fraud_count"] == 50
        assert details["coverage_by_class"] == {"0": None, "1": None}
    json.dumps(events, allow_nan=False)


@pytest.mark.parametrize("covered", [0, 5])
def test_exact_binomial_and_bonferroni_hand_calculation(covered):
    # Binomial(5, .5): the two extreme outcomes have mass 2 / 32.
    result = final.exact_fraud_coverage_test(covered, 5, 0.5)
    assert result["alternative"] == "two-sided"
    assert result["comparisons"] == 5
    assert result["p_raw"] == pytest.approx(1 / 16)
    assert result["p_bonferroni"] == pytest.approx(5 / 16)
    lo, hi = result["ci95_clopper_pearson"]
    if covered == 0:
        assert lo == 0.0
        assert hi == pytest.approx(1 - 0.025 ** (1 / 5))
    else:
        assert lo == pytest.approx(0.025 ** (1 / 5))
        assert hi == 1.0
    assert final.exact_fraud_coverage_test(0, 1, 0.5)["p_bonferroni"] == 1.0


@pytest.mark.parametrize("covered,total", [(None, 5), (0, 0)])
def test_coverage_test_unavailable_is_not_a_zero_p_value(covered, total):
    result = final.exact_fraud_coverage_test(covered, total, 0.05)
    assert result["status"] == "unavailable"
    assert result["p_raw"] is None
    assert result["p_bonferroni"] is None
    assert result["ci95_clopper_pearson"] is None
    assert result["comparisons"] == 5
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "covered,total,alpha", [(6, 5, 0.05), (0, -1, 0.05), (0, 1, 0)]
)
def test_coverage_test_rejects_invalid_counts(covered, total, alpha):
    with pytest.raises(ValueError, match="invalides"):
        final.exact_fraud_coverage_test(covered, total, alpha)


def test_report_has_adjacent_exact_and_adjusted_tests_without_reducing_family(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(final, "build_preprocessing_pipeline", TinyPreprocessor)
    monkeypatch.setattr(final, "build_model", lambda *args: TinyClassifier())
    original = final.mondrian_quantiles

    def quantiles(p, y, alpha):
        if alpha == 0.01:
            raise ValueError("Quantile fini impossible : cas synthétique")
        return original(p, y, alpha)

    monkeypatch.setattr(final, "mondrian_quantiles", quantiles)
    output = tmp_path / "report"
    report = final.run_workflow(synthetic_splits(), {}, output)
    assert report["selected_alpha"] == 0.02
    saved = json.loads((output / "results.json").read_text(encoding="utf8"))
    text = (output / "report.md").read_text(encoding="utf8")
    assert "| p exact brut | p Bonferroni (5) |" in text
    assert "transactions indépendantes" in text
    assert "marginaux, non ajustés" in text
    assert saved["alpha_results"][0]["fraud_coverage_test"]["p_raw"] is None
    for row in saved["alpha_results"][1:]:
        test = row["fraud_coverage_test"]
        assert test["total"] == test["covered"] == 50
        assert test["comparisons"] == 5
        assert test["p_bonferroni"] == min(1.0, 5 * test["p_raw"])
        assert f"| {test['p_raw']} | {test['p_bonferroni']} |" in text


def test_inference_prior_correction_matches_training():
    from ml.src.model.calibration import _correct_proba

    values = np.array([0.0, 0.1, 0.5, 0.9, 1.0])
    np.testing.assert_allclose(
        _correct_proba(values, 0.123), final.correct_proba(values, 0.123)
    )


def test_protocol_hash_and_grid_change_are_recorded(tmp_path):
    import hashlib

    journal = tmp_path / "launches.jsonl"
    source = tmp_path / "data/raw/fraudTrain.csv"
    old = final.protocol_snapshot({}, "digest")
    old["alphas"] = [0.01, 0.05, 0.1]
    with final.launch_audit(journal, source, old):
        pass
    new = final.protocol_snapshot({}, "digest")
    with (
        pytest.raises(ValueError, match="protocol-change-reason"),
        final.launch_audit(journal, source, new),
    ):
        pytest.fail("changed grid accepted without explicit reason")
    with final.launch_audit(journal, source, new, "D44: synthetic test"):
        pass
    events = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()
    ]
    expected = hashlib.sha256(
        json.dumps(new, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    ).hexdigest()
    assert events[-2]["event"] == "launch_started"
    assert events[-2]["protocol_sha256"] == expected
    assert events[-3]["event"] == "protocol_change_acknowledged"
