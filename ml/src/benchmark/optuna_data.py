"""Lecture selective Optuna : dates globales, puis donnees Optuna seulement."""

import hashlib
import json

import numpy as np
import pandas as pd
from benchmark.partition import (
    assert_disjoint,
    partition_development,
    partition_timestamps,
)
from data.load_data import DATE_COLUMN, TRAIN_COLUMNS
from preprocessing.pipeline import split_features_target
from sklearn.model_selection import StratifiedShuffleSplit
from validation.fold_data import guard_training_source


def _sample_positions(positions, y, count, seed):
    if count >= len(positions):
        return positions
    splitter = StratifiedShuffleSplit(n_splits=1, train_size=count, random_state=seed)
    selected, _ = next(splitter.split(np.zeros((len(positions), 1)), y.iloc[positions]))
    return positions[selected]


def load_optuna_data(source, settings, *, smoke=False):
    """Ne parse aucune etiquette ni feature du benchmark ou des calibrations.

    Le smoke conserve les frontieres chronologiques reelles et selectionne
    au plus 3200 lignes du train et 800 du holdout, sans changer leurs classes.
    Les deux zones sont echantillonnees separement et de facon stratifiee.
    """
    path = guard_training_source(source)
    if not path.is_file():
        raise FileNotFoundError("Place fraudTrain.csv dans data/raw/.")
    dates = pd.read_csv(
        path,
        usecols=[DATE_COLUMN],
        parse_dates=[DATE_COLUMN],
        date_format={DATE_COLUMN: "%Y-%m-%d %H:%M:%S"},
    )
    values = dates[DATE_COLUMN]
    if not pd.api.types.is_datetime64_any_dtype(values) or values.isna().any():
        raise ValueError("Dates de transaction invalides.")
    if values.dt.tz is not None:
        raise ValueError("Dates locales naives requises.")
    ordered = values.sort_values(kind="mergesort").index.to_numpy()
    n_dev = len(ordered) * 70 // 100
    if (
        n_dev < 2
        or values.iloc[ordered[:n_dev]].max() >= values.iloc[ordered[n_dev:]].min()
    ):
        raise ValueError("Frontiere development ambigue ou source trop petite.")
    metadata = dates.loc[ordered[:n_dev]].copy()
    optuna, benchmark = partition_timestamps(
        metadata, settings["partition"]["optuna_fraction"]
    )
    assert_disjoint(metadata, optuna, benchmark)
    optuna_dates = metadata.iloc[optuna].copy()
    selected = optuna_dates.index.to_numpy()
    mask = np.zeros(len(dates), dtype=bool)
    mask[selected] = True
    labels = pd.read_csv(
        path,
        usecols=["is_fraud"],
        skiprows=lambda row: row > 0 and not mask[row - 1],
    )["is_fraud"]
    if len(labels) != len(selected):
        raise ValueError("Effectif Optuna incorrect.")
    labels.index = np.flatnonzero(mask)
    labels = labels.loc[selected]
    provenance = {"zone": "development", "source": "data/raw/fraudTrain.csv"}
    optuna_dates.attrs.update(provenance)
    labels.attrs.update(provenance)
    train, valid = partition_development(
        optuna_dates, labels, settings["partition"]["internal_train_fraction"]
    )
    if labels.iloc[train].nunique() != 2 or labels.iloc[valid].nunique() != 2:
        raise ValueError("Train et holdout Optuna doivent contenir les deux classes.")
    audit = {
        "global_dates_rows": len(dates),
        "development_rows": n_dev,
        "optuna_rows": len(optuna),
        "benchmark_dates_rows": len(benchmark),
        "optuna_frauds": int(labels.sum()),
        "optuna_internal_train_rows": len(train),
        "optuna_internal_validation_rows": len(valid),
        "optuna_internal_validation_frauds": int(labels.iloc[valid].sum()),
        "benchmark_labels_features_loaded": 0,
        "calibration_labels_features_loaded": 0,
        "smoke": smoke,
    }
    if smoke and len(selected) > 4000:
        seed = settings["sampler"]["seed"]
        chosen_train = _sample_positions(train, labels, 3200, seed)
        chosen_valid = _sample_positions(valid, labels, 800, seed)
        selected = optuna_dates.index.take(
            np.concatenate([chosen_train, chosen_valid])
        ).to_numpy()
        selected = values.loc[selected].sort_values(kind="mergesort").index.to_numpy()
    feature_mask = np.zeros(len(dates), dtype=bool)
    feature_mask[selected] = True
    data = pd.read_csv(
        path,
        usecols=TRAIN_COLUMNS,
        skiprows=lambda row: row > 0 and not feature_mask[row - 1],
    )
    if len(data) != len(selected):
        raise ValueError("Lecture des features Optuna incomplete.")
    data.index = np.flatnonzero(feature_mask)
    data = data.loc[selected]
    X, y = split_features_target(data)
    X.attrs.update(provenance)
    y.attrs.update(provenance)
    if not y.equals(labels.loc[selected]):
        raise ValueError("Etiquettes Optuna desynchronisees.")
    # Le sous-echantillonnage smoke reste de part et d'autre de la vraie coupure.
    cutoff = optuna_dates[DATE_COLUMN].iloc[train].max()
    train_ready = np.flatnonzero(values.loc[selected].to_numpy() <= cutoff)
    valid_ready = np.flatnonzero(values.loc[selected].to_numpy() > cutoff)
    assert_disjoint(X, train_ready, valid_ready)
    if y.iloc[train_ready].nunique() != 2 or y.iloc[valid_ready].nunique() != 2:
        raise ValueError("Echantillon sans les deux classes.")
    digest = hashlib.sha256(json.dumps(list(X.columns)).encode())
    digest.update(pd.util.hash_pandas_object(X, index=True).to_numpy().tobytes())
    digest.update(pd.util.hash_pandas_object(y, index=True).to_numpy().tobytes())
    digest.update(values.to_numpy().tobytes())
    audit.update(
        loaded_rows=len(X),
        train_rows=len(train_ready),
        validation_rows=len(valid_ready),
        train_frauds=int(y.iloc[train_ready].sum()),
        validation_frauds=int(y.iloc[valid_ready].sum()),
        data_hash=digest.hexdigest(),
        train_end=str(cutoff),
        validation_start=str(values.loc[X.index[valid_ready]].min()),
    )
    return X, y, train_ready, valid_ready, audit
