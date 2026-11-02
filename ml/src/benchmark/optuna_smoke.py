"""Smoke Optuna explicite : trois essais par modele, aucun lancement complet."""

from __future__ import annotations

import argparse
import json
import subprocess
from time import monotonic

import mlflow
import numpy as np
import optuna
from benchmark.config import MODEL_NAMES, ROOT, load_configuration
from benchmark.models_smoke import sample_development
from benchmark.optuna_common import suggest_parameters
from benchmark.optuna_common import trial_worker as _trial_worker
from benchmark.trial_control import run_in_subprocess, timeout_summary
from optuna.trial import TrialState
from sklearn.model_selection import StratifiedKFold

from ml.tracking_smoke import (
    _private_client_calls,
    _safe_error,
    check_tracking_connection,
    get_tracking_uri,
)


def run_smoke_study(name, spaces, settings, evaluate):
    """Trois tentatives, echecs compris ; pas de selection sur un score smoke."""
    study = optuna.create_study(
        sampler=optuna.samplers.RandomSampler(seed=settings["sampler"]["seed"]),
        pruner=optuna.pruners.NopPruner(),
        direction=settings["direction"],
    )
    deadline = monotonic() + settings["study_timeout_seconds"]
    rows = []
    for _ in range(3):
        if monotonic() >= deadline:
            break
        trial = study.ask()
        params = suggest_parameters(trial, name, spaces)
        row = evaluate(params, deadline)
        row.update(number=trial.number, params=params)
        if row["status"] == "COMPLETE":
            value = row["result"]["average_precision"]
            if not np.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Score d'essai invalide.")
            study.tell(trial, value)
        else:
            trial.set_user_attr("failure_reason", row.get("reason", "worker_error"))
            study.tell(trial, state=TrialState.FAIL)
        rows.append(row)
    result = {
        "model": name,
        **timeout_summary(
            rows, alert_fraction=settings["trial_timeout"]["alert_fraction"]
        ),
        "trials": rows,
        "selected_trial": None,
        "selection_note": "Smoke uniquement : aucune configuration retenue.",
    }
    return result


def log_smoke(result, uri):
    """Conventions P3 : commit, run parent et enfants par modele, sans secret."""
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
    )
    previous = mlflow.get_tracking_uri()
    with _private_client_calls(5):
        try:
            mlflow.set_tracking_uri(uri)
            mlflow.set_experiment("optuna_smoke")
            with mlflow.start_run(
                run_name="p2-three-trials-per-model",
                tags={
                    "git_commit": commit,
                    "git_dirty": str(dirty).lower(),
                    "official_benchmark": "false",
                    "scope": "development_only",
                },
            ) as parent:
                mlflow.log_params({"trials_per_model": 3, "seed": 42})
                mlflow.log_dict(result, "smoke_summary.json")
                for row in result["models"]:
                    with mlflow.start_run(
                        run_name=row["model"],
                        nested=True,
                        tags={
                            "git_commit": commit,
                            "scope": "development_only",
                            "timeout_alert": str(row["timeout_alert"]).lower(),
                        },
                    ) as child:
                        metrics = {
                            key: row[key]
                            for key in (
                                "attempted",
                                "completed",
                                "timeout_count",
                                "timeout_fraction",
                            )
                        }
                        mlflow.log_metrics(metrics)
                        mlflow.log_dict(row, "trials.json")
                        stored = mlflow.MlflowClient().get_run(child.info.run_id)
                        if stored.data.metrics != metrics:
                            raise RuntimeError(
                                "Compteurs MLflow differents des mesures."
                            )
                return {"status": "PASS", "run_id": parent.info.run_id}
        finally:
            mlflow.set_tracking_uri(previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    try:
        configs = load_configuration()
        if not args.smoke:
            parser.error("Seul --smoke (3 essais par modele) est autorise ici.")
        print("PREFLIGHT PASS : aucun champ a confirmer.", flush=True)
        uri = get_tracking_uri()
        connection = check_tracking_connection(uri, timeout_seconds=5)
        print(json.dumps({"connectivity": connection}), flush=True)
        if connection["status"] != "PASS":
            raise RuntimeError(
                "MLflow indisponible : aucun essai lance, Docker non demarre."
            )
        X, y, audit = sample_development(ROOT / "data/raw/fraudTrain.csv")
        settings = configs["optuna"]
        seed = settings["sampler"]["seed"]
        train, valid = next(
            StratifiedKFold(n_splits=5, shuffle=True, random_state=seed).split(X, y)
        )
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        result = {
            "scope": "smoke_only_not_official_tuning",
            "audit": audit,
            "models": [],
        }
        for name in MODEL_NAMES:

            def evaluate(params, deadline, name=name):
                return run_in_subprocess(
                    _trial_worker,
                    (name, params, X, y, train, valid, seed),
                    seconds=settings["trial_timeout"]["seconds"],
                    deadline=deadline,
                )

            row = run_smoke_study(
                name, configs["search_spaces"]["models"], settings, evaluate
            )
            result["models"].append(row)
            print(
                json.dumps(
                    {key: value for key, value in row.items() if key != "trials"}
                ),
                flush=True,
            )
            if row["timeout_alert"]:
                print(f"ALERTE {name} : plus de 20 % d'essais interrompus.", flush=True)
        result["mlflow"] = log_smoke(result, uri)
        print(json.dumps(result, indent=2, allow_nan=False), flush=True)
        return 0 if all(row["completed"] == 3 for row in result["models"]) else 1
    except (ValueError, RuntimeError, mlflow.exceptions.MlflowException) as exc:
        print(json.dumps({"status": "FAIL", "error": _safe_error(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
