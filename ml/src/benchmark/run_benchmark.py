"""Benchmark P2 : 10 x 5 plis partages, sans tuning ni zones reservees."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import pandas as pd
from benchmark.benchmark_data import load_benchmark_data
from benchmark.config import MODEL_NAMES, ROOT, load_configuration
from mlflow import MlflowClient
from models.factory import ALLOWED, build_model
from models.search_spaces import model_parameters
from preprocessing.pipeline import build_preprocessing_pipeline
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    f1_score,
    log_loss,
    matthews_corrcoef,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from threadpoolctl import threadpool_limits
from validation.fold_data import _check_development, correct_proba, make_fold_data

from ml.tracking_smoke import (
    _private_client_calls,
    check_tracking_connection,
    get_tracking_uri,
)


def _finish_run(tracker, run_id, status):
    """MLflow imprime une URL avec emoji a la fermeture (CP1252 sur Windows)."""
    with _private_client_calls(10):
        tracker.set_terminated(run_id, status=status)


def load_best_params(path, spaces):
    """Charge les cinq essais figes, complets et compatibles avec les factories."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or set(document.get("models", {})) != set(
        MODEL_NAMES
    ):
        raise ValueError("best_params.json : cinq modeles canoniques requis.")
    for name, item in document["models"].items():
        if item.get("model") != name or item.get("study_name") != f"full-{name}":
            raise ValueError(f"Provenance Optuna incoherente : {name}.")
        if not isinstance(item.get("trial_number"), int) or item["trial_number"] < 0:
            raise ValueError(f"Numero d'essai invalide : {name}.")
        score = item.get("average_precision")
        if (
            not isinstance(score, (int, float))
            or not np.isfinite(score)
            or not 0 <= score <= 1
        ):
            raise ValueError(f"PR-AUC invalide : {name}.")
        if item.get("seed") != 42 or not isinstance(item.get("params"), dict):
            raise ValueError(f"Seed ou parametres invalides : {name}.")
        fixed = model_parameters(name, spaces)
        if not set(fixed).issubset(item["params"]) or any(
            item["params"][key] != value for key, value in fixed.items()
        ):
            raise ValueError(f"Parametres fixes modifies : {name}.")
        if set(item["params"]) - (set(spaces[name]["parameters"]) | set(fixed)):
            raise ValueError(f"Parametres non recherches : {name}.")
        if set(item["params"]) != set(fixed) | set(spaces[name]["parameters"]):
            raise ValueError(f"Parametres incomplets : {name}.")
        if set(item["params"]) - ALLOWED[name]:
            raise ValueError(f"Parametres incompatibles avec la factory : {name}.")
        build_model(name, item["params"], 0)
    return document


def shared_splits(X, y, settings, *, smoke=False):
    """Materialise une fois les memes partitions pour les cinq modeles."""
    _check_development(X, y)
    repeats = 1 if smoke else settings["repeats"]
    result = []
    for repeat, seed in enumerate(settings["seeds"][:repeats]):
        cv = StratifiedKFold(
            n_splits=settings["n_splits"], shuffle=True, random_state=seed
        )
        for fold, (train, valid) in enumerate(cv.split(X, y)):
            if np.intersect1d(train, valid).size or len(train) + len(valid) != len(X):
                raise ValueError(
                    "Collision ou perte de lignes entre train et validation."
                )
            result.append((repeat, fold, seed, train, valid))
            if smoke:
                break
    if not smoke and len(result) != 50:
        raise ValueError("Le benchmark exige exactement 50 partitions partagees.")
    return result


def choose_f1_threshold(y_true, probabilities, atol=1e-12):
    """Maximise F1 sur validation INTERNE ; departage par le seuil le plus bas."""
    if len(np.unique(y_true)) != 2:
        raise ValueError("Validation interne sans les deux classes.")
    precision, recall, thresholds = precision_recall_curve(y_true, probabilities)
    scores = np.divide(
        2 * precision[:-1] * recall[:-1],
        precision[:-1] + recall[:-1],
        out=np.zeros_like(precision[:-1]),
        where=(precision[:-1] + recall[:-1]) > 0,
    )
    best = np.max(scores)
    return float(thresholds[np.flatnonzero(np.abs(scores - best) <= atol)[0]])


def expected_calibration_error(y_true, probabilities, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    groups = np.clip(
        np.searchsorted(edges, probabilities, side="right") - 1, 0, bins - 1
    )
    return float(
        sum(
            np.count_nonzero(groups == i)
            / len(groups)
            * abs(
                float(np.mean(np.asarray(y_true)[groups == i]))
                - float(np.mean(probabilities[groups == i]))
            )
            for i in range(bins)
            if np.any(groups == i)
        )
    )


def evaluate_fold(name, params, X, y, train, valid, settings, seed):
    """Deux fits independants : seuil dans train, puis modele du pli externe.

    Ordre commun avec Optuna : fit preprocessing sur train naturel, transform
    train/validation, sous-echantillonner le train transforme, fit modele.
    """
    ratio = settings["legit_per_fraud"]
    inner_train, inner_valid = train_test_split(
        train,
        train_size=settings["threshold"]["internal_train_fraction"],
        stratify=y.iloc[train],
        random_state=seed,
    )
    if np.intersect1d(inner_train, inner_valid).size or not set(inner_valid).issubset(
        train
    ):
        raise ValueError("La validation du seuil doit rester dans le train externe.")
    with threadpool_limits(limits=1):
        start = perf_counter()
        X_it, y_it, X_iv, y_iv, inner_beta, inner_counts = make_fold_data(
            X,
            y,
            inner_train,
            inner_valid,
            build_preprocessing_pipeline,
            ratio=ratio,
            seed=seed,
        )
        inner_model = build_model(name, params, seed)
        inner_model.fit(X_it, y_it)
        inner_proba = correct_proba(inner_model.predict_proba(X_iv)[:, 1], inner_beta)
        threshold = choose_f1_threshold(
            y_iv, inner_proba, settings["threshold"]["equality_atol"]
        )
        inner_seconds = perf_counter() - start

        start = perf_counter()
        X_tr, y_tr, X_va, y_va, beta, counts = make_fold_data(
            X,
            y,
            train,
            valid,
            build_preprocessing_pipeline,
            ratio=ratio,
            seed=seed,
        )
        model = build_model(name, params, seed)
        model.fit(X_tr, y_tr)
        fit_seconds = perf_counter() - start
        start = perf_counter()
        proba = correct_proba(model.predict_proba(X_va)[:, 1], beta)
        predict_seconds = perf_counter() - start
    if not np.isfinite(proba).all():
        raise ValueError("Probabilites non finies.")
    prediction = (proba >= threshold).astype(int)
    clipped = np.clip(proba, 1e-15, 1 - 1e-15)
    metrics = {
        "average_precision": float(average_precision_score(y_va, proba)),
        "roc_auc": float(roc_auc_score(y_va, proba)),
        "mcc": float(matthews_corrcoef(y_va, prediction)),
        "precision": float(precision_score(y_va, prediction, zero_division=0)),
        "recall": float(recall_score(y_va, prediction, zero_division=0)),
        "f1": float(f1_score(y_va, prediction, zero_division=0)),
        "accuracy": float(accuracy_score(y_va, prediction)),
        "brier_score": float(brier_score_loss(y_va, proba)),
        "log_loss": float(log_loss(y_va, clipped, labels=[0, 1])),
        "ece": expected_calibration_error(y_va, proba, settings["ece"]["bins"]),
    }
    return {
        **metrics,
        "threshold": threshold,
        "beta": beta,
        "inner_beta": inner_beta,
        "inner_fit_rows": inner_counts["preproc_fit_rows"],
        "outer_fit_rows": counts["preproc_fit_rows"],
        "outer_validation_rows": counts["n_validation"],
        "outer_validation_frauds": counts["validation_n_fraud"],
        "inner_seconds": inner_seconds,
        "fit_seconds": fit_seconds,
        "predict_seconds": predict_seconds,
        "duration_seconds": inner_seconds + fit_seconds + predict_seconds,
    }


def aggregate_repeats(folds):
    """Une ligne par modele/repetition ; seuls ces moyens seront des blocs stats."""
    frame = pd.DataFrame(folds)
    if frame.empty:
        raise ValueError("Aucun pli a agreger.")
    metric_columns = [
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
    ]
    means = (
        frame.groupby(["model", "repeat"], sort=True)[metric_columns]
        .mean()
        .reset_index()
    )
    return means


def _external_directory(path):
    result = Path(path).expanduser().resolve()
    if result == ROOT or ROOT in result.parents or result in ROOT.parents:
        raise ValueError("Les resultats doivent rester HORS du depot.")
    return result


def _resume_rows(
    directory,
    splits,
    settings,
    frozen,
    tracker,
    commit,
    config_sha,
    data_sha256,
    smoke,
):
    """Accepte uniquement un préfixe intact des plis prévus et leurs runs terminés."""
    allowed = {".gitignore", "folds.parquet", "repeat_means.parquet", "parents.json"}
    if {path.name for path in directory.iterdir()} - allowed:
        raise ValueError("Dossier de reprise : fichiers inattendus.")
    if (directory / ".gitignore").read_text(encoding="utf-8") != "*\n":
        raise ValueError("Dossier de reprise non ignoré par Git.")
    path = directory / "folds.parquet"
    if not path.is_file():
        raise ValueError("Dossier de reprise sans folds.parquet.")
    frame = pd.read_parquet(path)
    expected = [
        (name, repeat, fold, seed)
        for name in MODEL_NAMES
        for repeat, fold, seed, _, _ in splits
    ]
    actual = list(
        frame[["model", "repeat", "fold", "seed"]].itertuples(index=False, name=None)
    )
    if actual != expected[: len(actual)] or not actual:
        raise ValueError("Les plis enregistrés ne forment pas le préfixe attendu.")
    parents = {}
    for row in frame.to_dict("records"):
        name = row["model"]
        if any(
            row[key] != value
            for key, value in {
                "model_seed": row["seed"] * 100 + row["fold"],
                "ratio": settings["legit_per_fraud"],
                "trial_number": frozen["models"][name]["trial_number"],
                "git_commit": commit,
                "config_hash": config_sha,
                "data_sha256": data_sha256,
            }.items()
        ):
            raise ValueError("Métadonnées de reprise incompatibles.")
        run = tracker.get_run(row["run_id"])
        parent = run.data.tags.get("mlflow.parentRunId")
        if run.info.status != "FINISHED" or not parent:
            raise ValueError("Un pli enregistré n'est pas terminé sur MLflow.")
        logged = run.data.metrics.get("average_precision")
        if logged is None or not np.isclose(
            logged, row["average_precision"], atol=1e-12, rtol=0
        ):
            raise ValueError("PR-AUC du pli différente entre MLflow et Parquet.")
        if name in parents and parents[name] != parent:
            raise ValueError("Plusieurs parents MLflow pour un même modèle.")
        parents[name] = parent
    for name, parent_id in parents.items():
        tags = tracker.get_run(parent_id).data.tags
        if any(
            tags.get(key) != value
            for key, value in {
                "model": name,
                "mode": "smoke" if smoke else "full",
                "git_commit": commit,
                "config_hash": config_sha,
                "data_sha256": data_sha256,
            }.items()
        ):
            raise ValueError("Parent MLflow incompatible avec cette reprise.")
    return frame.to_dict("records"), parents


def run_benchmark(
    X,
    y,
    settings,
    frozen,
    tracker,
    *,
    smoke=False,
    output_dir,
    data_sha256="synthetic",
    resume=False,
):
    """Execute le smoke ou le protocole officiel ; splits prepares une fois."""
    splits = shared_splits(X, y, settings, smoke=smoke)
    directory = _external_directory(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    if not resume:
        if list(directory.iterdir()):
            raise ValueError(
                "Dossier de resultats non vide ; choisir un nouveau dossier."
            )
        (directory / ".gitignore").write_text("*\n", encoding="utf-8")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    config_sha = hashlib.sha256(
        (ROOT / "configs/best_params.json").read_bytes()
    ).hexdigest()
    experiment = tracker.get_experiment_by_name("benchmark_p2")
    experiment_id = (
        experiment.experiment_id
        if experiment
        else tracker.create_experiment("benchmark_p2")
    )
    rows, parents = (
        _resume_rows(
            directory,
            splits,
            settings,
            frozen,
            tracker,
            commit,
            config_sha,
            data_sha256,
            smoke,
        )
        if resume
        else ([], {})
    )
    completed = {(row["model"], row["repeat"], row["fold"]) for row in rows}
    for name in MODEL_NAMES:
        item = frozen["models"][name]
        if all((name, repeat, fold) in completed for repeat, fold, *_ in splits):
            continue
        parent = (
            parents.get(name)
            or tracker.create_run(
                experiment_id,
                tags={
                    "mlflow.runName": f"{'smoke' if smoke else 'benchmark'}-{name}",
                    "model": name,
                    "git_commit": commit,
                    "config_hash": config_sha,
                    "data_sha256": data_sha256,
                    "mode": "smoke" if smoke else "full",
                },
            ).info.run_id
        )
        parents[name] = parent
        try:
            for repeat, fold, seed, train, valid in splits:
                if (name, repeat, fold) in completed:
                    continue
                fold_seed = seed * 100 + fold
                existing = []
                if resume and name in {row["model"] for row in rows}:
                    existing = [
                        run
                        for run in tracker.search_runs(
                            [experiment_id], max_results=1000
                        )
                        if run.data.tags.get("mlflow.parentRunId") == parent
                        and run.data.tags.get("repeat") == str(repeat)
                        and run.data.tags.get("fold") == str(fold)
                    ]
                    if len(existing) > 1 or (
                        existing and existing[0].info.status != "RUNNING"
                    ):
                        raise ValueError(
                            "Pli MLflow orphelin ambigu ; reprise refusée."
                        )
                child = (
                    existing[0].info.run_id
                    if existing
                    else tracker.create_run(
                        experiment_id,
                        tags={
                            "mlflow.parentRunId": parent,
                            "mlflow.runName": f"repeat-{repeat:02d}-fold-{fold:02d}",
                            "model": name,
                            "repeat": str(repeat),
                            "fold": str(fold),
                            "git_commit": commit,
                            "config_hash": config_sha,
                            "data_sha256": data_sha256,
                        },
                    ).info.run_id
                )
                try:
                    result = evaluate_fold(
                        name, item["params"], X, y, train, valid, settings, fold_seed
                    )
                    row = {
                        "model": name,
                        "repeat": repeat,
                        "fold": fold,
                        "seed": seed,
                        "model_seed": fold_seed,
                        "ratio": settings["legit_per_fraud"],
                        "trial_number": item["trial_number"],
                        "git_commit": commit,
                        "config_hash": config_sha,
                        "run_id": child,
                        **result,
                    }
                    row["data_sha256"] = data_sha256
                    for key, value in item["params"].items():
                        tracker.log_param(child, key, json.dumps(value))
                    tracker.log_param(child, "ratio", row["ratio"])
                    tracker.log_param(child, "seed", seed)
                    tracker.log_param(child, "repeat", repeat)
                    tracker.log_param(child, "fold", fold)
                    for key, value in result.items():
                        tracker.log_metric(child, key, value)
                    _finish_run(tracker, child, "FINISHED")
                    rows.append(row)
                    temporary = directory / "folds.pending.parquet"
                    pd.DataFrame(rows).to_parquet(temporary, index=False)
                    os.replace(temporary, directory / "folds.parquet")
                    print(
                        json.dumps(
                            {
                                "model": name,
                                "repeat": repeat,
                                "fold": fold,
                                "average_precision": result["average_precision"],
                            }
                        ),
                        flush=True,
                    )
                except Exception:
                    _finish_run(tracker, child, "FAILED")
                    raise
            _finish_run(tracker, parent, "FINISHED")
        except Exception:
            _finish_run(tracker, parent, "FAILED")
            raise
    means = aggregate_repeats(rows)
    means.to_parquet(directory / "repeat_means.parquet", index=False)
    if not smoke and (len(rows) != 250 or means.groupby("model").size().ne(10).any()):
        raise ValueError(
            "Resultats incomplets : 250 plis et 10 moyennes par modele requis."
        )
    (directory / "parents.json").write_text(
        json.dumps(parents, indent=2) + "\n", encoding="utf-8"
    )
    return rows, means, parents


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Un petit pli par modele ; non scientifique",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reprend les plis Parquet et runs MLflow vérifiés",
    )
    args = parser.parse_args(argv)
    configs = load_configuration()
    settings = configs["benchmark"]
    frozen = load_best_params(
        ROOT / "configs/best_params.json", configs["search_spaces"]["models"]
    )
    uri = get_tracking_uri()
    if not uri.startswith(("http://", "https://")):
        raise ValueError("Serveur MLflow HTTP requis, aucun repli SQLite.")
    connection = check_tracking_connection(uri, timeout_seconds=10)
    if connection["status"] != "PASS":
        raise RuntimeError(
            "MLflow indisponible ; aucun benchmark lance. " + json.dumps(connection)
        )
    directory = args.output_dir or (
        Path(os.environ.get("LOCALAPPDATA", Path.home()))
        / "fintech-benchmark"
        / ("smoke" if args.smoke else "full")
    )
    X, y, audit = load_benchmark_data(
        ROOT / "data/raw/fraudTrain.csv",
        configs["optuna"]["partition"]["optuna_fraction"],
        smoke=args.smoke,
    )
    print(
        json.dumps({"audit": audit, "mode": "smoke" if args.smoke else "full"}),
        flush=True,
    )
    rows, means, parents = run_benchmark(
        X,
        y,
        settings,
        frozen,
        MlflowClient(tracking_uri=uri),
        smoke=args.smoke,
        output_dir=directory,
        data_sha256=audit["data_sha256"],
        resume=args.resume,
    )
    print(
        json.dumps(
            {
                "folds": len(rows),
                "repeat_means": len(means),
                "parents": parents,
                "output_dir": str(directory),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
