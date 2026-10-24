"""Partitions temporelles de development, sans chargement ni ajustement."""

from fractions import Fraction

import numpy as np
import pandas as pd
from data.load_data import DATE_COLUMN
from validation.fold_data import _check_development, _positions


def _dates(X):
    if DATE_COLUMN not in X:
        raise ValueError("Date de transaction manquante.")
    dates = pd.to_datetime(X[DATE_COLUMN], format="%Y-%m-%d %H:%M:%S", errors="raise")
    if dates.isna().any() or dates.dt.tz is not None:
        raise ValueError("Dates locales naives et non manquantes requises.")
    return dates


def assert_disjoint(X, left, right):
    """Leve ValueError si index, positions ou timestamps se chevauchent."""
    left = _positions(left, len(X), "left")
    right = _positions(right, len(X), "right")
    if np.intersect1d(left, right).size or not X.index.is_unique:
        raise ValueError("Index communs ou dupliques entre les parties.")
    if X.index.take(left).intersection(X.index.take(right)).size:
        raise ValueError("Index source communs entre les parties.")
    dates = _dates(X)
    if pd.Index(dates.iloc[left]).intersection(dates.iloc[right]).size:
        raise ValueError("Timestamps communs entre les parties.")
    if dates.iloc[left].max() >= dates.iloc[right].min():
        raise ValueError("Les parties ne respectent pas l'ordre chronologique strict.")


def partition_development(X, y, fraction=0.2):
    """Renvoie deux tableaux de positions ; tous les timestamps egaux vont a gauche.

    Le meme contrat sert a separer Optuna/benchmark, puis train/holdout dans
    Optuna. Les metadonnees development sont controlees par le helper existant.
    La fonction ne confirme pas la fiabilite statistique des effectifs.
    """
    _check_development(X, y)
    if (
        isinstance(fraction, bool)
        or not isinstance(fraction, (int, float))
        or not 0 < fraction < 1
    ):
        raise ValueError("fraction doit etre finie dans ]0,1[.")
    if len(X) < 2:
        raise ValueError("Au moins deux lignes sont necessaires.")
    dates = _dates(X)
    order = np.argsort(dates.to_numpy(), kind="stable")
    ratio = Fraction(str(fraction))
    cut = len(X) * ratio.numerator // ratio.denominator
    if cut == 0:
        raise ValueError("La partie initiale serait vide.")
    while cut < len(X) and dates.iloc[order[cut]] == dates.iloc[order[cut - 1]]:
        cut += 1
    if cut == len(X):
        raise ValueError("Timestamps egaux : la partie finale serait vide.")
    left, right = order[:cut], order[cut:]
    assert_disjoint(X, left, right)
    return left, right
