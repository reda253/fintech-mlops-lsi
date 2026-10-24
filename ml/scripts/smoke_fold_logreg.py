"""Smoke P2 : un seul pli LogReg sur development et journalisation MLflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import warnings
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any

import mlflow
import numpy as np
from mlflow import MlflowClient
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedKFold
from threadpoolctl import threadpool_limits

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "ml" / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from preprocessing.pipeline import build_preprocessing_pipeline
from validation.fold_data import (
    correct_proba,
    load_development_data,
    make_fold_data,
)

from ml.tracking_smoke import get_tracking_uri


def sha256_file(path: Path) -> str:
    """Empreinte d'un fichier sans chargement complet en memoire."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def log_fold_run(
    tracking_uri: str,
    result: dict[str, Any],
    experiment: str = "benchmark",
) -> str:
    """Enregistre parametres, metriques et artefacts, puis verifie le run."""

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    existing = client.get_experiment_by_name(experiment)
    if existing is None:
        kwargs = {}
        if tracking_uri.startswith("sqlite:"):
            artifacts = PROJECT_ROOT / ".mlflow" / "fold_smoke" / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            kwargs["artifact_location"] = artifacts.as_uri()
        experiment_id = client.create_experiment(experiment, **kwargs)
    else:
        experiment_id = existing.experiment_id
    with mlflow.start_run(
        experiment_id=experiment_id,
        run_name="p2_logreg_one_fold_smoke",
        tags={
            "smoke": "true",
            "scope": "development_only",
            "official_benchmark": "false",
            "step": "T4_fold_setup",
            "git_commit": result["git_commit"],
            "git_dirty": str(result["git_dirty"]).lower(),
            "source_sha256": result["source_sha256"],
        },
    ) as run:
        run_id = run.info.run_id
        mlflow.log_params(
            {
                **result["counts"],
                **result["model_params"],
                "beta": result["beta"],
                "cv_seed": result["seed"],
                "fold": 0,
                "n_splits": 5,
            }
        )
        mlflow.log_metrics(result["metrics"])
        mlflow.log_dict(result, "fold_summary.json")
        mlflow.log_dict(result["versions"], "dependency_versions.json")
        for relative in [
            "ml/src/validation/fold_data.py",
            "ml/src/preprocessing/pipeline.py",
            "ml/tracking_smoke.py",
            "ml/scripts/smoke_fold_logreg.py",
        ]:
            mlflow.log_artifact(str(PROJECT_ROOT / relative), artifact_path="code")
    stored = client.get_run(run_id)
    if stored.info.status != "FINISHED":
        raise RuntimeError("Le run MLflow n'est pas termine correctement.")
    for key, value in result["metrics"].items():
        if not np.isclose(stored.data.metrics[key], value, rtol=0, atol=1e-12):
            raise RuntimeError(f"Metrique MLflow incorrecte : {key}.")
    if not np.isclose(float(stored.data.params["beta"]), result["beta"]):
        raise RuntimeError("Beta MLflow incorrect.")
    artifacts = {item.path for item in client.list_artifacts(run_id)}
    if "fold_summary.json" not in artifacts:
        raise RuntimeError("Artefact de synthese absent de MLflow.")
    return run_id


def main() -> None:
    """Execute le premier des cinq plis, sans tuning ni autre modele."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ratio", type=int, default=10)
    parser.add_argument("--tracking-uri")
    parser.add_argument("--allow-local-sqlite", action="store_true")
    args = parser.parse_args()
    tracking_uri = get_tracking_uri(
        args.tracking_uri,
        allow_local_sqlite=args.allow_local_sqlite,
    )
    print("[1/4] Chargement des seules lignes development...", flush=True)
    source = PROJECT_ROOT / "data" / "raw" / "fraudTrain.csv"
    X, y = load_development_data(source)
    print(f"Development : {len(X):,} lignes.", flush=True)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=args.seed)
    train_idx, val_idx = next(cv.split(X, y))
    start = perf_counter()
    print(
        "[2/4] Preprocessing sur train naturel, puis sous-echantillonnage...",
        flush=True,
    )
    with threadpool_limits(limits=1):
        X_tr, y_tr, X_va, y_va, beta, counts = make_fold_data(
            X,
            y,
            train_idx,
            val_idx,
            build_preprocessing_pipeline,
            ratio=args.ratio,
            seed=args.seed,
        )
        print("[3/4] LogisticRegression : un seul ajustement...", flush=True)
        model_params = {
            "C": 1.0,
            "solver": "lbfgs",
            "max_iter": 2000,
            "random_state": args.seed,
        }
        model = LogisticRegression(**model_params)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            model.fit(X_tr, y_tr)
        raw = model.predict_proba(X_va)[:, 1]
    corrected = correct_proba(raw, beta)
    ap_raw = float(average_precision_score(y_va, raw))
    ap_corrected = float(average_precision_score(y_va, corrected))
    if not np.isclose(ap_raw, ap_corrected, rtol=0, atol=1e-12):
        raise RuntimeError("La correction monotone a change la PR-AUC.")
    git = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = {
        "source": "data/raw/fraudTrain.csv",
        "zone": "development",
        "seed": args.seed,
        "fold": 0,
        "beta": beta,
        "counts": counts,
        "n_features": int(X_tr.shape[1]),
        "model_params": model_params,
        "git_commit": git.stdout.strip(),
        "git_dirty": bool(status.stdout),
        "source_sha256": sha256_file(source),
        "versions": {
            "python": platform.python_version(),
            **{
                name: version(name)
                for name in [
                    "numpy",
                    "pandas",
                    "scikit-learn",
                    "mlflow",
                ]
            },
        },
        "metrics": {
            "pr_auc_raw": ap_raw,
            "pr_auc_corrected": ap_corrected,
            "validation_prevalence": float(y_va.mean()),
            "mean_proba_raw": float(raw.mean()),
            "mean_proba_corrected": float(corrected.mean()),
            "elapsed_seconds": perf_counter() - start,
        },
        "interpretation": (
            "Smoke only, not the 10x5 benchmark. Prior correction preserves "
            "ranking but does not guarantee calibrated probabilities."
        ),
        "tracking_backend": (
            "local_sqlite"
            if tracking_uri.startswith("sqlite:")
            else "configured_server"
        ),
    }
    print("[4/4] Journalisation et verification MLflow...", flush=True)
    result["run_id"] = log_fold_run(tracking_uri, result)
    result["mlflow_verified"] = True
    reports = PROJECT_ROOT / "reports"
    reports.mkdir(exist_ok=True)
    path = reports / "fold_logreg_smoke.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
