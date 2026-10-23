"""Chronometrage diagnostique borne, jamais un tuning ou un benchmark officiel."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import warnings
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

import mlflow
import numpy as np
import pandas as pd
from benchmark.config import MODEL_NAMES, ROOT, load_configuration
from benchmark.partition import partition_development
from data.load_data import DATE_COLUMN, TRAIN_COLUMNS
from models.factory import build_model
from models.search_spaces import model_parameters
from preprocessing.pipeline import build_preprocessing_pipeline, split_features_target
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedKFold, StratifiedShuffleSplit
from threadpoolctl import threadpool_limits
from validation.fold_data import correct_proba, guard_training_source, make_fold_data

from ml.tracking_smoke import _private_client_calls, _safe_error, get_tracking_uri


def _provenance(X, y):
    for frame in (X, y):
        frame.attrs.update(zone="development", source="data/raw/fraudTrain.csv")


def sample_development(source, *, limit=4000, seed=42):
    """Lit les dates globales autorisees, puis labels dev et petit echantillon.

    Les etiquettes de calibration ne sont jamais parsees : skiprows les exclut.
    Les features ne sont chargees que pour <= 4000 lignes du TRAIN interne
    Optuna 20/80. Aucune matrice complete de features development n'est creee.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 20 <= limit <= 4000:
        raise ValueError("Le diagnostic exige entre 20 et 4000 lignes maximum.")
    path = guard_training_source(source)
    dates = pd.read_csv(
        path,
        usecols=[DATE_COLUMN],
        parse_dates=[DATE_COLUMN],
        date_format={DATE_COLUMN: "%Y-%m-%d %H:%M:%S"},
    )[DATE_COLUMN]
    if (
        not pd.api.types.is_datetime64_any_dtype(dates)
        or dates.isna().any()
        or dates.dt.tz is not None
    ):
        raise ValueError("Dates locales naives valides requises.")
    order = dates.sort_values(kind="mergesort").index.to_numpy()
    n_dev = len(dates) * 70 // 100
    if n_dev < 2 or dates.iloc[order[:n_dev]].max() >= dates.iloc[order[n_dev:]].min():
        raise ValueError("Frontiere development ambigue ou source trop petite.")
    positions = order[:n_dev]
    mask = np.zeros(len(dates), dtype=bool)
    mask[positions] = True
    pieces = []
    for chunk in pd.read_csv(
        path,
        usecols=["is_fraud"],
        chunksize=10000,
        skiprows=lambda row: row > 0 and not mask[row - 1],
    ):
        if not chunk["is_fraud"].isin([0, 1]).all():
            raise ValueError("Cible development invalide.")
        pieces.append(chunk["is_fraud"].to_numpy(dtype=np.uint8))
    labels = np.concatenate(pieces)
    if len(labels) != n_dev:
        raise ValueError("Effectif development incorrect.")
    y = pd.Series(labels, index=np.flatnonzero(mask)).loc[positions]
    metadata = pd.DataFrame(
        {DATE_COLUMN: dates.iloc[positions].to_numpy()}, index=positions
    )
    _provenance(metadata, y)
    optuna, benchmark = partition_development(metadata, y, 0.2)
    inner_X, inner_y = metadata.iloc[optuna], y.iloc[optuna]
    train, holdout = partition_development(inner_X, inner_y, 0.8)
    pool = optuna[train]
    n_sample = min(limit, len(pool))
    if n_sample < 20:
        raise ValueError("Train interne trop petit pour le diagnostic.")
    if n_sample < len(pool):
        splitter = StratifiedShuffleSplit(
            n_splits=1, train_size=n_sample, random_state=seed
        )
        chosen, _ = next(splitter.split(np.zeros((len(pool), 1)), y.iloc[pool]))
        selected = positions[pool[chosen]]
    else:
        selected = positions[pool]
    sample_mask = np.zeros(len(dates), dtype=bool)
    sample_mask[selected] = True
    sample = pd.read_csv(
        path,
        usecols=TRAIN_COLUMNS,
        nrows=n_sample,
        skiprows=lambda row: row > 0 and not sample_mask[row - 1],
    )
    if len(sample) != n_sample:
        raise ValueError("Echantillon incomplet.")
    sample.index = np.flatnonzero(sample_mask)
    sample = sample.loc[dates.loc[selected].sort_values(kind="mergesort").index]
    X_sample, y_sample = split_features_target(sample)
    _provenance(X_sample, y_sample)

    def counts(indices):
        return {"rows": len(indices), "frauds": int(y.iloc[indices].sum())}

    audit = {
        "development": counts(np.arange(n_dev)),
        "optuna": counts(optuna),
        "optuna_train": counts(pool),
        "optuna_validation": counts(optuna[holdout]),
        "benchmark": counts(benchmark),
        "sample_rows": n_sample,
        "sample_frauds": int(y_sample.sum()),
        "dates_only_global_rows": len(dates),
        "calibration_labels_features_loaded": 0,
        "source": "data/raw/fraudTrain.csv",
        "seed": seed,
    }
    return X_sample, y_sample, audit


def measure_models(X, y, audit, configs, *, seed=42):
    """Mesure cinq fits diagnostiques sur un seul petit pli, sans Optuna."""
    if len(X) > 4000:
        raise ValueError("Diagnostic limite a 4000 lignes.")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    train, valid = next(cv.split(X, y))
    results = []
    with threadpool_limits(limits=1):
        start = perf_counter()
        X_tr, y_tr, X_va, y_va, beta, counts = make_fold_data(
            X,
            y,
            train,
            valid,
            build_preprocessing_pipeline,
            ratio=10,
            seed=seed,
        )
        preprocessing_seconds = perf_counter() - start
        full_rows = audit["benchmark"]["rows"]
        estimated_train_rows = audit["benchmark"]["frauds"] * 4 / 5 * 11
        optuna_train_rows = audit["optuna_train"]["frauds"] * 11
        for name in MODEL_NAMES:
            params = model_parameters(
                name, configs["search_spaces"]["models"], smoke=True
            )
            model = build_model(name, params, seed)
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always")
                start = perf_counter()
                model.fit(X_tr, y_tr)
                fit_seconds = perf_counter() - start
                start = perf_counter()
                raw = model.predict_proba(X_va)[:, 1]
                predict_seconds = perf_counter() - start
            corrected = correct_proba(raw, beta)
            if not np.isfinite(corrected).all():
                raise ValueError("Probabilites non finies.")
            results.append(
                {
                    "model": name,
                    "params": params,
                    "fit_seconds": fit_seconds,
                    "predict_validation_seconds": predict_seconds,
                    "estimated_full_fold_fit_seconds": fit_seconds
                    * estimated_train_rows
                    / len(y_tr),
                    "estimated_full_fold_total_seconds": (
                        fit_seconds * estimated_train_rows / len(y_tr)
                        + preprocessing_seconds * full_rows / len(X)
                        + predict_seconds * (full_rows / 5) / len(y_va)
                    ),
                    "estimated_30_trials_fit_seconds_smoke_params_only": fit_seconds
                    * optuna_train_rows
                    / len(y_tr)
                    * 30,
                    "pr_auc_raw": float(average_precision_score(y_va, raw)),
                    "pr_auc_corrected": float(average_precision_score(y_va, corrected)),
                    "warning_categories": sorted(
                        {type(w.message).__name__ for w in captured}
                    ),
                }
            )
    return {
        "scope": "diagnostic_only_not_benchmark",
        "seed": seed,
        "single_thread": True,
        "counts": counts,
        "audit": audit,
        "beta": beta,
        "features": X_tr.shape[1],
        "preprocessing_seconds": preprocessing_seconds,
        "estimated_full_fold_model_fit_rows": estimated_train_rows,
        "models": results,
        "versions": {
            "python": platform.python_version(),
            **{
                name: version(name)
                for name in ["numpy", "pandas", "scikit-learn", "xgboost", "mlflow"]
            },
        },
        "machine": {
            "system": platform.system(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "interpretation": "Extrapolation lineaire indicative des parametres smoke uniquement ; pas une borne, ni un budget Optuna valide. Pas de decision de selection.",
    }


def log_models_smoke(result):
    """Journalise sans repli implicite ni demarrage de Docker ; erreurs masquees."""
    uri = get_tracking_uri()
    previous = mlflow.get_tracking_uri()
    with _private_client_calls(5):
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip()
            mlflow.set_tracking_uri(uri)
            mlflow.set_experiment("models_smoke")
            with mlflow.start_run(
                run_name="p2-five-models-diagnostic",
                tags={
                    "git_commit": commit,
                    "official_benchmark": "false",
                    "scope": "development_only",
                },
            ) as parent:
                mlflow.log_params(
                    {
                        "sample_rows": result["audit"]["sample_rows"],
                        "seed": result["seed"],
                        "beta": result["beta"],
                    }
                )
                mlflow.log_dict(result, "diagnostic_summary.json")
                for row in result["models"]:
                    with mlflow.start_run(
                        run_name=row["model"],
                        nested=True,
                        tags={"git_commit": commit, "official_benchmark": "false"},
                    ):
                        mlflow.log_params(row["params"])
                        mlflow.log_metrics(
                            {
                                key: value
                                for key, value in row.items()
                                if isinstance(value, (float, int))
                            }
                        )
                return {
                    "status": "PASS",
                    "run_id": parent.info.run_id,
                    "experiment": "models_smoke",
                }
        except (
            mlflow.exceptions.MlflowException,
            ConnectionError,
            OSError,
            ValueError,
        ) as exc:
            return {
                "status": "FAIL",
                "error": _safe_error(exc),
                "docker_started": False,
            }
        finally:
            mlflow.set_tracking_uri(previous)


def main():
    """Sans --diagnostic-smoke, le prevol strict bloque toute config incomplete."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostic-smoke", action="store_true")
    parser.add_argument("--sample-rows", type=int, default=4000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        configs = load_configuration(allow_incomplete=args.diagnostic_smoke)
        if not args.diagnostic_smoke:
            parser.error("Ce module ne lance que le diagnostic explicitement autorise.")
        if args.output is not None and (
            args.output.resolve().is_relative_to(ROOT.resolve())
            or args.output.suffix != ".json"
        ):
            raise ValueError(
                "Sortie diagnostic JSON autorisee uniquement hors du depot."
            )
        X, y, audit = sample_development(
            ROOT / "data/raw/fraudTrain.csv", limit=args.sample_rows
        )
        result = measure_models(X, y, audit, configs)
        result["mlflow"] = log_models_smoke(result)
    except ValueError as exc:
        parser.exit(2, str(exc) + "\n")
    text = json.dumps(result, indent=2, allow_nan=False)
    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
