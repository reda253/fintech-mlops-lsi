"""Contrats du benchmark P2 sur des donnees synthetiques exclusivement."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from benchmark import run_benchmark as bench
from benchmark.benchmark_data import load_benchmark_data
from benchmark.config import MODEL_NAMES, ROOT, load_configuration
from data.load_data import TRAIN_COLUMNS
from sklearn.metrics import f1_score
from validation.fold_data import guard_training_source


@pytest.fixture
def synthetic():
    size = 100
    X = pd.DataFrame(
        {
            "trans_date_trans_time": pd.date_range(
                "2019-01-01", periods=size, freq="h"
            ),
            "dob": ["1980-01-01"] * size,
            "amt": np.linspace(1, 200, size),
            "category": ["food", "gas"] * (size // 2),
            "gender": ["F", "M"] * (size // 2),
            "state": ["MA", "NY"] * (size // 2),
            "city_pop": [1000] * size,
            "lat": [40.0] * size,
            "long": [-70.0] * size,
            "merch_lat": [40.1] * size,
            "merch_long": [-70.1] * size,
            "trans_num": [f"synthetic-{i}" for i in range(size)],
        }
    )
    y = pd.Series((np.arange(size) % 5 == 0).astype(int), index=X.index)
    for data in (X, y):
        data.attrs.update(zone="development", source="data/raw/fraudTrain.csv")
    return X, y


def test_best_params_are_frozen_and_complete():
    configs = load_configuration()
    frozen = bench.load_best_params(
        ROOT / "configs/best_params.json", configs["search_spaces"]["models"]
    )
    assert list(frozen["models"]) == list(MODEL_NAMES)
    assert [frozen["models"][name]["trial_number"] for name in MODEL_NAMES] == [
        10,
        12,
        2,
        12,
        6,
    ]
    for name in MODEL_NAMES:
        item = frozen["models"][name]
        assert item["seed"] == 42
        model = bench.build_model(name, item["params"], 0)
        assert model is not None
    assert frozen["provenance"]["data_hash"]


def test_incomplete_or_changed_fixed_params_are_rejected(tmp_path):
    configs = load_configuration()
    spaces = configs["search_spaces"]["models"]
    original = json.loads((ROOT / "configs/best_params.json").read_text())
    original["models"]["rf"]["params"].pop("max_depth")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="incomplets"):
        bench.load_best_params(path, spaces)


def test_fifty_shared_splits_with_no_overlap(synthetic):
    X, y = synthetic
    settings = load_configuration()["benchmark"]
    splits = bench.shared_splits(X, y, settings)
    assert len(splits) == 50
    assert {(repeat, fold) for repeat, fold, *_ in splits} == {
        (repeat, fold) for repeat in range(10) for fold in range(5)
    }
    signatures = [tuple(sorted(train.tolist())) for _, _, _, train, _ in splits]
    assert len(set(signatures)) > 1
    for _, _, _, train, valid in splits:
        assert set(train).isdisjoint(valid)
        assert len(train) + len(valid) == len(X)
        assert y.iloc[valid].sum() == 4
    assert sum(len(splits) for _ in MODEL_NAMES) == 250


def test_preprocessing_sampling_and_threshold_stay_inside_train(synthetic, monkeypatch):
    X, y = synthetic
    train, valid = bench.shared_splits(X, y, load_configuration()["benchmark"])[0][3:5]
    settings = load_configuration()["benchmark"]
    original = bench.make_fold_data
    observed = []
    threshold_indexes = []

    def record(*args, **kwargs):
        result = original(*args, **kwargs)
        observed.append((set(args[2]), set(args[3]), result[5], result[3].copy()))
        return result

    monkeypatch.setattr(bench, "make_fold_data", record)
    original_threshold = bench.choose_f1_threshold

    def record_threshold(inner_y, probabilities, atol):
        threshold_indexes.extend(inner_y.index)
        return original_threshold(inner_y, probabilities, atol)

    monkeypatch.setattr(bench, "choose_f1_threshold", record_threshold)
    frozen = bench.load_best_params(
        ROOT / "configs/best_params.json",
        load_configuration()["search_spaces"]["models"],
    )
    result = bench.evaluate_fold(
        "logreg",
        frozen["models"]["logreg"]["params"],
        X,
        y,
        train,
        valid,
        settings,
        0,
    )
    assert len(observed) == 2
    inner_train, inner_valid, inner_counts, inner_y = observed[0]
    outer_train, outer_valid, outer_counts, outer_y = observed[1]
    assert inner_train.isdisjoint(inner_valid)
    assert inner_train | inner_valid == set(train)
    assert outer_train == set(train) and outer_valid == set(valid)
    assert inner_counts["preproc_fit_rows"] == len(inner_train)
    assert outer_counts["preproc_fit_rows"] == len(train)
    pd.testing.assert_series_equal(
        inner_y.sort_index(), y.iloc[list(inner_valid)].sort_index()
    )
    pd.testing.assert_series_equal(outer_y, y.iloc[valid])
    assert set(threshold_indexes) == inner_valid
    assert set(threshold_indexes).isdisjoint(valid)
    assert outer_counts["n_validation"] == len(valid)
    assert result["outer_validation_rows"] == len(valid)
    assert 0 <= result["threshold"] <= 1


def test_threshold_max_f1_lower_tie():
    y = np.array([0, 1, 0, 1, 0, 1])
    p = np.array([0.05, 0.9, 0.2, 0.8, 0.3, 0.7])
    t = bench.choose_f1_threshold(y, p)
    candidates = np.unique(p)
    scores = [f1_score(y, p >= value) for value in candidates]
    expected = candidates[
        np.flatnonzero(np.isclose(scores, max(scores), atol=1e-12))[0]
    ]
    assert t == expected


def test_repeat_aggregation_has_ten_independent_means():
    folds = [
        {
            "model": name,
            "repeat": repeat,
            "fold": fold,
            **{
                metric: float(fold)
                for metric in (
                    "average_precision",
                    "roc_auc",
                    "mcc",
                    "precision",
                    "recall",
                    "f1",
                    "accuracy",
                    "brier_score",
                    "log_loss",
                    "ece",
                )
            },
        }
        for name in MODEL_NAMES
        for repeat in range(10)
        for fold in range(5)
    ]
    means = bench.aggregate_repeats(folds)
    assert len(folds) == 250 and len(means) == 50
    assert means.groupby("model").size().eq(10).all()
    assert means["average_precision"].eq(2.0).all()


def test_forbidden_source_rejected_before_any_read(monkeypatch):
    read = Mock(side_effect=AssertionError("aucune lecture autorisee"))
    monkeypatch.setattr(pd, "read_csv", read)
    with pytest.raises(ValueError, match="Source interdite"):
        load_benchmark_data(Path("data/raw/fraudTest.csv"), 0.2)
    read.assert_not_called()
    with pytest.raises(ValueError, match="Source interdite"):
        guard_training_source("data/raw/fraudTest.csv")


def test_benchmark_loader_reads_only_its_labels_and_features(tmp_path, monkeypatch):
    source = tmp_path / "data/raw/fraudTrain.csv"
    source.parent.mkdir(parents=True)
    dates = pd.date_range("2019-01-01", periods=100, freq="h")
    frame = pd.DataFrame(
        {
            "trans_date_trans_time": dates.strftime("%Y-%m-%d %H:%M:%S"),
            "dob": ["1980-01-01"] * 100,
            "cc_num": [1000 + i for i in range(100)],
            "amt": [10.0] * 100,
            "category": ["food"] * 100,
            "gender": ["F"] * 100,
            "state": ["MA"] * 100,
            "city_pop": [1000] * 100,
            "lat": [40.0] * 100,
            "long": [-70.0] * 100,
            "merch_lat": [40.1] * 100,
            "merch_long": [-70.1] * 100,
            "is_fraud": (np.arange(100) % 5 == 0).astype(int),
            "trans_num": [f"t-{i}" for i in range(100)],
        }
    )[TRAIN_COLUMNS]
    frame.to_csv(source, index=False)
    reads = []
    original = pd.read_csv

    def record(*args, **kwargs):
        reads.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", record)
    X, y, audit = load_benchmark_data(source, 0.2)
    assert len(X) == len(y) == audit["benchmark_rows"] == 56
    assert X.index.min() == 14 and X.index.max() == 69
    assert len(reads) == 3
    assert reads[0]["usecols"] == ["trans_date_trans_time"]
    for call in reads[1:]:
        assert callable(call["skiprows"])
        assert all(not call["skiprows"](i + 1) for i in range(14, 70))
        assert all(
            call["skiprows"](i + 1) for i in list(range(14)) + list(range(70, 100))
        )
    assert reads[1]["usecols"] == ["is_fraud"]
    assert reads[2]["usecols"] == TRAIN_COLUMNS
    assert audit["calibration_labels_features_loaded"] == 0
    assert audit["optuna_labels_features_loaded"] == 0


class FakeTracking:
    def __init__(self):
        self.runs = []
        self.ended = []
        self.metrics = []
        self.params = []
        self.records = {}

    def get_experiment_by_name(self, _):
        return None

    def create_experiment(self, _):
        return "synthetic-experiment"

    def create_run(self, _, tags):
        self.runs.append(tags)
        run_id = f"run-{len(self.runs)}"
        run = SimpleNamespace(
            info=SimpleNamespace(run_id=run_id, status="RUNNING"),
            data=SimpleNamespace(tags=tags, metrics={}, params={}),
        )
        self.records[run_id] = run
        return run

    def get_run(self, run_id):
        return self.records[run_id]

    def search_runs(self, _, max_results):
        return list(self.records.values())[:max_results]

    def log_param(self, run_id, key, value):
        self.params.append((run_id, key, value))
        self.records[run_id].data.params[key] = value

    def log_metric(self, run_id, key, value):
        self.metrics.append((run_id, key, value))
        self.records[run_id].data.metrics[key] = value

    def set_terminated(self, run_id, *, status):
        self.ended.append((run_id, status))
        self.records[run_id].info.status = status


def test_smoke_tracking_and_aggregation(synthetic, tmp_path, monkeypatch):
    X, y = synthetic
    configs = load_configuration()
    frozen = bench.load_best_params(
        ROOT / "configs/best_params.json", configs["search_spaces"]["models"]
    )
    fake = FakeTracking()
    seen = []

    def evaluate(name, params, _X, _y, train, valid, _settings, _seed):
        seen.append((name, tuple(train), tuple(valid), params.copy()))
        return {
            **{
                metric: 0.5
                for metric in (
                    "average_precision",
                    "roc_auc",
                    "mcc",
                    "precision",
                    "recall",
                    "f1",
                    "accuracy",
                    "brier_score",
                    "log_loss",
                    "ece",
                )
            },
            "duration_seconds": 0.01,
        }

    monkeypatch.setattr(
        bench,
        "evaluate_fold",
        evaluate,
    )
    rows, means, parents = bench.run_benchmark(
        X,
        y,
        configs["benchmark"],
        frozen,
        fake,
        smoke=True,
        output_dir=tmp_path / "smoke",
        data_sha256="synthetic-hash",
    )
    assert len(rows) == len(means) == len(parents) == 5
    assert len(fake.runs) == 10
    assert all("provisional" not in tags for tags in fake.runs)
    assert len({(train, valid) for _, train, valid, _ in seen}) == 1
    assert all(
        params == frozen["models"][name]["params"] for name, _, _, params in seen
    )
    assert all(
        any(
            key == "ratio" and value == 10
            for run_id, key, value in fake.params
            if run_id == row["run_id"]
        )
        for row in rows
    )
    assert all(status == "FINISHED" for _, status in fake.ended)
    assert all(tag["data_sha256"] == "synthetic-hash" for tag in fake.runs)
    assert len(pd.read_parquet(tmp_path / "smoke/folds.parquet")) == 5
    assert len(pd.read_parquet(tmp_path / "smoke/repeat_means.parquet")) == 5


def test_resume_keeps_finished_folds_and_reuses_running_child(
    synthetic, tmp_path, monkeypatch
):
    X, y = synthetic
    configs = load_configuration()
    frozen = bench.load_best_params(
        ROOT / "configs/best_params.json", configs["search_spaces"]["models"]
    )
    splits = bench.shared_splits(X, y, configs["benchmark"])[:2]
    monkeypatch.setattr(bench, "shared_splits", lambda *_args, **_kwargs: splits)
    tracker = FakeTracking()
    seen = []
    interrupted = [False]

    def evaluate(name, params, _X, _y, train, valid, _settings, _seed):
        seen.append((name, tuple(train), tuple(valid)))
        if len(seen) == 2 and not interrupted[0]:
            interrupted[0] = True
            raise KeyboardInterrupt
        return {
            **{
                key: 0.5
                for key in (
                    "average_precision",
                    "roc_auc",
                    "mcc",
                    "precision",
                    "recall",
                    "f1",
                    "accuracy",
                    "brier_score",
                    "log_loss",
                    "ece",
                )
            },
            "duration_seconds": 0.01,
        }

    monkeypatch.setattr(bench, "evaluate_fold", evaluate)
    output = tmp_path / "partial"
    with pytest.raises(KeyboardInterrupt):
        bench.run_benchmark(
            X,
            y,
            configs["benchmark"],
            frozen,
            tracker,
            smoke=True,
            output_dir=output,
            data_sha256="sample",
        )
    assert len(pd.read_parquet(output / "folds.parquet")) == 1
    first_run_id = pd.read_parquet(output / "folds.parquet").iloc[0]["run_id"]
    rows, means, _ = bench.run_benchmark(
        X,
        y,
        configs["benchmark"],
        frozen,
        tracker,
        smoke=True,
        output_dir=output,
        data_sha256="sample",
        resume=True,
    )
    assert len(rows) == 10 and len(means) == 5
    assert len(tracker.records) == 15  # cinq parents, dix enfants
    assert rows[0]["run_id"] == first_run_id
    assert seen.count(("logreg", tuple(splits[0][3]), tuple(splits[0][4]))) == 1
    assert seen.count(("logreg", tuple(splits[1][3]), tuple(splits[1][4]))) == 2
    assert all(run.info.status == "FINISHED" for run in tracker.records.values())


def test_resume_rejects_changed_data_hash_without_new_fit(
    synthetic, tmp_path, monkeypatch
):
    X, y = synthetic
    configs = load_configuration()
    frozen = bench.load_best_params(
        ROOT / "configs/best_params.json", configs["search_spaces"]["models"]
    )
    tracker = FakeTracking()
    mock = Mock(
        return_value={
            **{
                key: 0.5
                for key in (
                    "average_precision",
                    "roc_auc",
                    "mcc",
                    "precision",
                    "recall",
                    "f1",
                    "accuracy",
                    "brier_score",
                    "log_loss",
                    "ece",
                )
            },
            "duration_seconds": 0.01,
        }
    )
    monkeypatch.setattr(bench, "evaluate_fold", mock)
    output = tmp_path / "completed"
    bench.run_benchmark(
        X,
        y,
        configs["benchmark"],
        frozen,
        tracker,
        smoke=True,
        output_dir=output,
        data_sha256="original",
    )
    count = mock.call_count
    with pytest.raises(ValueError, match="reprise incompatibles"):
        bench.run_benchmark(
            X,
            y,
            configs["benchmark"],
            frozen,
            tracker,
            smoke=True,
            output_dir=output,
            data_sha256="changed",
            resume=True,
        )
    assert mock.call_count == count
