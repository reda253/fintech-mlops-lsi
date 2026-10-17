"""Absence de fuite par pli et correction des probabilites."""

from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from data.load_data import TRAIN_COLUMNS
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.metrics import average_precision_score
from validation.fold_data import (
    correct_proba,
    guard_training_source,
    load_development_data,
    make_fold_data,
)


class RecordingPreprocessor(TransformerMixin, BaseEstimator):
    """Transformeur instrumente pour observer les seules lignes d'ajustement."""

    observations: ClassVar[list[dict]] = []

    def fit(self, X: pd.DataFrame, y: pd.Series | None = None):
        self.mean_ = float(X["value"].mean())
        type(self).observations.append({
            "index": X.index.tolist(), "mean": self.mean_, "rows": len(X),
        })
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        return (X[["value"]].to_numpy() - self.mean_)


@pytest.fixture
def development() -> tuple[pd.DataFrame, pd.Series]:
    X = pd.DataFrame({"value": np.arange(1000, dtype=float)})
    y = pd.Series([1] * 20 + [0] * 780 + [1] * 5 + [0] * 195, name="is_fraud")
    for frame in [X, y]:
        frame.attrs.update(zone="development", source="data/raw/fraudTrain.csv")
    return X, y


def test_sampling_validation_and_train_only_fit(development) -> None:
    X, y = development
    RecordingPreprocessor.observations.clear()
    fitted = RecordingPreprocessor().fit(X)  # Le clone doit oublier cet etat.
    RecordingPreprocessor.observations.clear()
    tr, yt, va, yv, beta, counts = make_fold_data(
        X, y, np.arange(800), np.arange(800, 1000), lambda: fitted, seed=42,
    )
    assert len(yt) == 11 * 20
    assert counts["n_legit_before"] == 780
    assert counts["n_legit_after"] == 200
    assert beta == 200 / 780
    assert beta != 0.1
    assert len(RecordingPreprocessor.observations) == 1
    observed = RecordingPreprocessor.observations[0]
    assert observed["index"] == list(range(800))
    assert observed["mean"] == X.iloc[:800]["value"].mean()
    assert fitted.mean_ == X["value"].mean()
    assert len(yt.index.intersection(yv.index)) == 0
    pd.testing.assert_series_equal(yv, y.iloc[800:])
    assert counts["validation_prevalence"] == 5 / 200
    np.testing.assert_allclose(va[:, 0], X.iloc[800:]["value"] - observed["mean"])
    assert tr.shape == (220, 1)


def test_seed_reproducibility(development) -> None:
    X, y = development
    args = (X, y, np.arange(800), np.arange(800, 1000), RecordingPreprocessor)
    first = make_fold_data(*args, seed=42)
    second = make_fold_data(*args, seed=42)
    third = make_fold_data(*args, seed=43)
    np.testing.assert_array_equal(first[0], second[0])
    pd.testing.assert_series_equal(first[1], second[1])
    assert first[4:] == second[4:]
    assert first[1].index.tolist() != third[1].index.tolist()


def test_no_sampling_when_not_enough_legitimate_rows(development) -> None:
    X, y = development
    result = make_fold_data(
        X, y, np.arange(30), np.arange(800, 1000), RecordingPreprocessor, seed=42,
    )
    assert result[4] == 1
    assert len(result[1]) == 30


def test_known_posterior_recovers_natural_prevalence() -> None:
    natural_prevalence = 20 / 800
    sampled_posterior = np.full(200, 20 / 220)
    corrected = correct_proba(sampled_posterior, 200 / 780)
    assert corrected.mean() == pytest.approx(natural_prevalence, abs=1e-12)


def test_monotonicity_and_average_precision() -> None:
    probabilities = np.linspace(0, 1, 101)
    labels = np.random.default_rng(42).integers(0, 2, len(probabilities))
    corrected = correct_proba(probabilities, 0.06)
    assert np.all(np.diff(corrected) > 0)
    assert np.all((corrected >= 0) & (corrected <= 1))
    assert average_precision_score(labels, corrected) == average_precision_score(
        labels, probabilities
    )
    np.testing.assert_array_equal(correct_proba(probabilities, 1), probabilities)


@pytest.mark.parametrize("beta", [0, -1, 1.1, np.nan, np.inf])
def test_invalid_beta(beta) -> None:
    with pytest.raises(ValueError, match="beta"):
        correct_proba([0.1, 0.5], beta)


@pytest.mark.parametrize("probabilities", [[np.nan], [np.inf], [-0.1], [1.1]])
def test_invalid_probabilities(probabilities) -> None:
    with pytest.raises(ValueError, match="probabilites"):
        correct_proba(probabilities, 0.1)


@pytest.mark.parametrize("train,valid", [
    ([0, 1], [1, 2]), ([0, 0], [2]), ([-1, 0], [2]), ([0, 1], [1000]),
])
def test_invalid_or_overlapping_positions(development, train, valid) -> None:
    X, y = development
    with pytest.raises(ValueError):
        make_fold_data(X, y, train, valid, RecordingPreprocessor, seed=42)


def test_non_development_and_unknown_origin_rejected(development) -> None:
    X, y = development
    for zone in ["probability_calibration", "conformal_calibration", None]:
        X.attrs["zone"] = zone
        with pytest.raises(ValueError, match="development"):
            make_fold_data(X, y, [0, 20], [800, 999], RecordingPreprocessor, seed=42)


def test_forbidden_paths_fail_before_reading(tmp_path: Path) -> None:
    with patch("validation.fold_data.pd.read_csv") as read:
        for name in [
            "probability_calibration.csv", "conformal_calibration.csv",
            "held_out.csv",
        ]:
            with pytest.raises(ValueError, match="Source interdite"):
                load_development_data(tmp_path / "data/raw" / name)
        read.assert_not_called()


@pytest.mark.parametrize("ratio,seed", [
    (0, 42), (-1, 42), (2.5, 42), (10, None), (10, -1),
])
def test_ratio_and_seed_are_explicit_and_valid(development, ratio, seed) -> None:
    X, y = development
    with pytest.raises(ValueError):
        make_fold_data(
            X, y, [0, 20], [800, 999], RecordingPreprocessor,
            ratio=ratio, seed=seed,
        )


def test_repeated_transaction_identifier_rejected(development) -> None:
    X, y = development
    X["trans_num"] = [f"t{i}" for i in range(len(X))]
    X.loc[800, "trans_num"] = X.loc[0, "trans_num"]
    with pytest.raises(ValueError, match="Transactions communes"):
        make_fold_data(
            X, y, [0, 20], [800, 999], RecordingPreprocessor, seed=42,
        )


def test_loader_loads_only_development_fields(tmp_path: Path) -> None:
    path = tmp_path / "data/raw/fraudTrain.csv"
    path.parent.mkdir(parents=True)
    rows = []
    for i in range(20):
        row = {name: 1 for name in TRAIN_COLUMNS}
        row.update(
            trans_date_trans_time=f"2020-01-{i + 1:02d} 00:00:00",
            dob="1980-01-01", gender="F", category="food", state="CA",
            trans_num=f"t{i}", is_fraud=i % 2,
        )
        # Ces valeurs ne doivent jamais etre chargees dans development.
        if i >= 14:
            row["dob"] = "not-loaded"
        rows.append(row)
    pd.DataFrame(rows[::-1]).to_csv(path, index=False)
    X, y = load_development_data(path)
    assert len(X) == 14
    assert X.index.tolist() == list(range(19, 5, -1))
    assert X["dob"].dtype.kind == "M"
    assert X.attrs["zone"] == y.attrs["zone"] == "development"
    assert X["trans_date_trans_time"].max() == pd.Timestamp("2020-01-14")
    assert guard_training_source(path) == path.resolve()
