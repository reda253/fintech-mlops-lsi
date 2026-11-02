"""Tirage et evaluation partages entre smoke et recherche Optuna P2."""

import json
import warnings
from time import perf_counter

import numpy as np
from models.factory import build_model
from models.search_spaces import model_parameters
from preprocessing.pipeline import build_preprocessing_pipeline
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits
from validation.fold_data import correct_proba, make_fold_data


def suggest_parameters(trial, name, spaces):
    """Echantillonne le YAML, y compris les architectures encodees en JSON."""
    params = model_parameters(name, spaces)
    for key, spec in spaces[name]["parameters"].items():
        kind = spec["type"]
        if kind == "categorical":
            choices = spec["choices"]
            structured = any(isinstance(value, list) for value in choices)
            options = (
                [json.dumps(value) for value in choices] if structured else choices
            )
            value = trial.suggest_categorical(key, options)
            params[key] = json.loads(value) if structured else value
        else:
            suggest = trial.suggest_int if kind == "int" else trial.suggest_float
            params[key] = suggest(
                key, spec["low"], spec["high"], log=spec.get("log", False)
            )
    return params


def trial_worker(name, params, X, y, train, valid, seed):
    """Ajuste exclusivement le train interne ; renvoie des mesures reelles."""
    with threadpool_limits(limits=1), warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        start = perf_counter()
        X_tr, y_tr, X_va, y_va, beta, counts = make_fold_data(
            X, y, train, valid, build_preprocessing_pipeline, ratio=10, seed=seed
        )
        preparation = perf_counter() - start
        model = build_model(name, params, seed)
        start = perf_counter()
        model.fit(X_tr, y_tr)
        fit = perf_counter() - start
        start = perf_counter()
        corrected = correct_proba(model.predict_proba(X_va)[:, 1], beta)
        predict = perf_counter() - start
        if not np.isfinite(corrected).all():
            raise ValueError("Probabilites non finies.")
        return {
            "average_precision": float(average_precision_score(y_va, corrected)),
            "preparation_seconds": preparation,
            "fit_seconds": fit,
            "predict_seconds": predict,
            "beta": beta,
            "counts": counts,
            "warning_categories": sorted({type(w.message).__name__ for w in captured}),
        }
