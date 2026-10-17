"""Preprocessing par pli, sous-echantillonnage et correction d'a priori."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from numbers import Integral
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from data.load_data import DATE_COLUMN, TRAIN_COLUMNS
from preprocessing.pipeline import split_features_target
from sklearn.base import BaseEstimator, clone


def guard_training_source(source: str | Path) -> Path:
    """Refuse toute source autre que data/raw/fraudTrain.csv avant lecture."""

    path = Path(source).resolve()
    expected = ("data", "raw", "fraudtrain.csv")
    actual = tuple(part.lower() for part in path.parts[-3:])
    if actual != expected:
        raise ValueError(
            "Source interdite : seule data/raw/fraudTrain.csv est autorisee."
        )
    return path


def load_development_data(source: str | Path) -> tuple[pd.DataFrame, pd.Series]:
    """Charge seulement les lignes development, apres un reperage par dates."""

    path = guard_training_source(source)
    if not path.is_file():
        raise FileNotFoundError("Place fraudTrain.csv dans data/raw/.")
    dates = pd.read_csv(
        path, usecols=[DATE_COLUMN], parse_dates=[DATE_COLUMN],
        date_format={DATE_COLUMN: "%Y-%m-%d %H:%M:%S"},
    )[DATE_COLUMN]
    if not pd.api.types.is_datetime64_any_dtype(dates) or dates.isna().any():
        raise ValueError("Dates de transaction invalides.")
    if dates.dt.tz is not None:
        raise ValueError("Les dates doivent etre locales et naives.")
    n_dev = len(dates) * 70 // 100
    if n_dev < 2:
        raise ValueError("Source trop petite pour preparer development.")
    ordered = dates.sort_values(kind="mergesort").index.to_numpy()
    selected = ordered[:n_dev]
    if dates.iloc[selected].max() >= dates.iloc[ordered[n_dev:]].min():
        raise ValueError(
            "Dates communes a la frontiere development : verifier le decoupage."
        )
    selected_mask = np.zeros(len(dates), dtype=bool)
    selected_mask[selected] = True

    # La seconde lecture ignore les enregistrements hors development.
    data = pd.read_csv(
        path, usecols=TRAIN_COLUMNS,
        skiprows=lambda row: row > 0 and not selected_mask[row - 1],
        dtype={name: "category" for name in ["category", "gender", "state"]},
        parse_dates=[DATE_COLUMN, "dob"],
        date_format={DATE_COLUMN: "%Y-%m-%d %H:%M:%S", "dob": "%Y-%m-%d"},
    )
    if len(data) != n_dev:
        raise ValueError("Effectif development incorrect apres selection des lignes.")
    data.index = np.flatnonzero(selected_mask)
    data = data.loc[selected]
    if data["trans_num"].isna().any() or not data["trans_num"].is_unique:
        raise ValueError("Identifiants de transaction manquants ou dupliques.")
    X, y = split_features_target(data)
    provenance = {"zone": "development", "source": "data/raw/fraudTrain.csv"}
    X.attrs.update(provenance)
    y.attrs.update(provenance)
    return X, y


def _check_development(X: pd.DataFrame, y: pd.Series) -> None:
    """Controle le contrat de provenance et l'alignement des entrees."""

    if not isinstance(X, pd.DataFrame) or not isinstance(y, pd.Series):
        # Le contrat P2 expose ValueError pour toutes les entrees invalides.
        raise ValueError("X doit etre un DataFrame et y une Series.")  # noqa: TRY004
    for data in [X, y]:
        if data.attrs.get("zone") != "development":
            raise ValueError("Seule la zone development est autorisee.")
        guard_training_source(data.attrs.get("source", ""))
    if not X.index.equals(y.index) or not X.index.is_unique:
        raise ValueError("Index X/y desalignes ou dupliques.")
    if "is_fraud" in X.columns:
        raise ValueError("La cible doit etre separee des entrees X.")
    if y.isna().any() or not y.isin([0, 1]).all():
        raise ValueError("La cible doit contenir uniquement 0 et 1, sans NaN.")


def _positions(indices: Sequence[int], size: int, name: str) -> np.ndarray:
    """Valide des positions entieres, distinctes et dans les bornes."""

    values = np.asarray(indices)
    if values.ndim != 1 or values.size == 0 or values.dtype.kind not in "iu":
        raise ValueError(f"{name} doit contenir des positions entieres non vides.")
    if np.any(values < 0) or np.any(values >= size):
        raise ValueError(f"{name} contient une position hors limites.")
    if np.unique(values).size != values.size:
        raise ValueError(f"{name} contient des doublons.")
    return values


def _take_rows(values: Any, positions: np.ndarray) -> Any:
    """Selectionne des lignes dans une matrice dense, sparse ou pandas."""

    if isinstance(values, pd.DataFrame):
        return values.iloc[positions]
    return values[positions]


def make_fold_data(
    X: pd.DataFrame,
    y: pd.Series,
    train_idx: Sequence[int],
    val_idx: Sequence[int],
    preproc_factory: Callable[[], BaseEstimator],
    *,
    ratio: int = 10,
    seed: int,
) -> tuple[Any, pd.Series, Any, pd.Series, float, dict[str, int | float]]:
    """Ajuste un clone sur train naturel, puis sous-echantillonne train seul."""

    _check_development(X, y)
    if isinstance(ratio, bool) or not isinstance(ratio, Integral) or ratio <= 0:
        raise ValueError("ratio doit etre un entier strictement positif.")
    if isinstance(seed, bool) or not isinstance(seed, Integral) or seed < 0:
        raise ValueError("Une seed entiere positive ou nulle est obligatoire.")
    train_idx = _positions(train_idx, len(X), "train_idx")
    val_idx = _positions(val_idx, len(X), "val_idx")
    if np.intersect1d(train_idx, val_idx).size:
        raise ValueError("Chevauchement entre train et validation.")
    X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
    y_train, y_val = y.iloc[train_idx], y.iloc[val_idx].copy()
    if "trans_num" in X.columns:
        overlap = pd.Index(X_train["trans_num"]).intersection(X_val["trans_num"])
        if overlap.size:
            raise ValueError("Transactions communes entre train et validation.")
    fraud_positions = np.flatnonzero(y_train.to_numpy() == 1)
    legit_positions = np.flatnonzero(y_train.to_numpy() == 0)
    n_fraud, n_legit = len(fraud_positions), len(legit_positions)
    if n_fraud == 0 or n_legit == 0:
        raise ValueError("Le pli d'entrainement doit contenir les deux classes.")

    preprocessor = clone(preproc_factory())
    X_train_all = preprocessor.fit_transform(X_train, y_train)
    X_val_ready = preprocessor.transform(X_val)
    if X_train_all.shape[0] != len(y_train) or X_val_ready.shape[0] != len(y_val):
        raise ValueError("Le preprocessing ne doit pas supprimer de lignes.")
    n_kept = min(n_legit, int(ratio) * n_fraud)
    rng = np.random.default_rng(int(seed))
    sampled_legit = rng.choice(legit_positions, size=n_kept, replace=False)
    kept = rng.permutation(np.concatenate([fraud_positions, sampled_legit]))
    beta = n_kept / n_legit
    counts = {
        "n_train_before": len(y_train), "n_train_after": len(kept),
        "n_fraud_before": n_fraud, "n_fraud_after": n_fraud,
        "n_legit_before": n_legit, "n_legit_after": n_kept,
        "training_prevalence_before": float(y_train.mean()),
        "training_prevalence_after": float(y_train.iloc[kept].mean()),
        "n_validation": len(y_val),
        "validation_n_fraud": int(y_val.sum()),
        "validation_prevalence": float(y_val.mean()),
        "preproc_fit_rows": len(y_train), "seed": int(seed),
        "legit_per_fraud": int(ratio),
    }
    return (
        _take_rows(X_train_all, kept), y_train.iloc[kept].copy(),
        X_val_ready, y_val, beta, counts,
    )


def correct_proba(p: Any, beta: float) -> np.ndarray:
    """Corrige le posterior sous-echantillonne avec le beta reel du pli."""

    values = np.asarray(p, dtype=np.float64)
    if np.ndim(beta) != 0 or not np.isfinite(beta) or not 0 < beta <= 1:
        raise ValueError("beta doit etre fini dans ]0, 1].")
    if not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
        raise ValueError("Les probabilites doivent etre finies dans [0, 1].")
    weighted = beta * values
    return np.asarray(weighted / (weighted + (1.0 - values)))
