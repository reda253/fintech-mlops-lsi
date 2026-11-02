"""Charge exclusivement la partie benchmark de development."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
from benchmark.partition import assert_disjoint, partition_timestamps
from data.load_data import DATE_COLUMN, TRAIN_COLUMNS
from preprocessing.pipeline import split_features_target
from sklearn.model_selection import StratifiedShuffleSplit
from validation.fold_data import guard_training_source


def load_benchmark_data(source, fraction, *, smoke=False, seed=42):
    """Lit les dates globales, puis labels/features des seuls rangs benchmark.

    Le smoke tire 8000 lignes de benchmark après lecture de ses labels ; il ne
    consulte jamais les labels/features Optuna ou des zones de calibration.
    """
    path = guard_training_source(source)
    if not path.is_file():
        raise FileNotFoundError("Place fraudTrain.csv dans data/raw/.")
    dates = pd.read_csv(
        path,
        usecols=[DATE_COLUMN],
        parse_dates=[DATE_COLUMN],
        date_format={DATE_COLUMN: "%Y-%m-%d %H:%M:%S"},
    )[DATE_COLUMN]
    if not pd.api.types.is_datetime64_any_dtype(dates) or dates.isna().any():
        raise ValueError("Dates de transaction invalides.")
    if dates.dt.tz is not None:
        raise ValueError("Dates locales naives requises.")
    ordered = dates.sort_values(kind="mergesort").index.to_numpy()
    n_dev = len(ordered) * 70 // 100
    if (
        n_dev < 2
        or dates.iloc[ordered[:n_dev]].max() >= dates.iloc[ordered[n_dev:]].min()
    ):
        raise ValueError("Frontiere development ambigue.")
    metadata = pd.DataFrame(
        {DATE_COLUMN: dates.loc[ordered[:n_dev]].to_numpy()}, index=ordered[:n_dev]
    )
    optuna, benchmark = partition_timestamps(metadata, fraction)
    assert_disjoint(metadata, optuna, benchmark)
    selected = metadata.index.to_numpy()[benchmark]
    mask = np.zeros(len(dates), dtype=bool)
    mask[selected] = True
    labels = pd.read_csv(
        path,
        usecols=["is_fraud"],
        skiprows=lambda row: row > 0 and not mask[row - 1],
    )["is_fraud"]
    if len(labels) != len(selected) or not labels.isin([0, 1]).all():
        raise ValueError("Etiquettes benchmark invalides.")
    labels.index = np.flatnonzero(mask)
    labels = labels.loc[selected]
    full_rows = len(selected)
    full_frauds = int(labels.sum())
    if smoke and full_rows > 8000:
        splitter = StratifiedShuffleSplit(
            n_splits=1, train_size=8000, random_state=seed
        )
        chosen, _ = next(splitter.split(np.zeros((full_rows, 1)), labels))
        selected = selected[chosen]
        selected = dates.loc[selected].sort_values(kind="mergesort").index.to_numpy()
    feature_mask = np.zeros(len(dates), dtype=bool)
    feature_mask[selected] = True
    data = pd.read_csv(
        path,
        usecols=TRAIN_COLUMNS,
        skiprows=lambda row: row > 0 and not feature_mask[row - 1],
    )
    if len(data) != len(selected):
        raise ValueError("Lecture des features benchmark incomplete.")
    data.index = np.flatnonzero(feature_mask)
    data = data.loc[selected]
    X, y = split_features_target(data)
    provenance = {"zone": "development", "source": "data/raw/fraudTrain.csv"}
    X.attrs.update(provenance)
    y.attrs.update(provenance)
    if not y.equals(labels.loc[selected]):
        raise ValueError("Etiquettes benchmark desynchronisees.")
    digest = hashlib.sha256()
    digest.update(pd.util.hash_pandas_object(X, index=True).to_numpy().tobytes())
    digest.update(pd.util.hash_pandas_object(y, index=True).to_numpy().tobytes())
    return (
        X,
        y,
        {
            "development_rows": n_dev,
            "optuna_dates_rows": len(optuna),
            "benchmark_rows": full_rows,
            "benchmark_frauds": full_frauds,
            "loaded_rows": len(X),
            "loaded_frauds": int(y.sum()),
            "calibration_labels_features_loaded": 0,
            "optuna_labels_features_loaded": 0,
            "data_sha256": digest.hexdigest(),
            "smoke": smoke,
        },
    )
