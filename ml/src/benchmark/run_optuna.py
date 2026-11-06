"""Recherche P2 persistante ; --smoke reste une validation courte, pas un tuning."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import unicodedata
import uuid
from importlib.metadata import version
from pathlib import Path
from time import monotonic

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import mlflow
import optuna
import pandas as pd
from benchmark.config import (
    MODEL_NAMES,
    ROOT,
    load_configuration,
    validate_configuration,
)
from benchmark.optuna_common import suggest_parameters, trial_worker
from benchmark.optuna_data import load_optuna_data
from benchmark.optuna_tracking import SearchTracking
from benchmark.trial_control import run_in_subprocess, timeout_summary
from models.search_spaces import model_parameters
from optuna.trial import TrialState
from sqlalchemy.pool import NullPool

from ml.tracking_smoke import (
    _safe_error,
    check_tracking_connection,
    get_tracking_uri,
)


def external_directory(path):
    """Refuse un etat dans le depot du projet ou un de ses parents."""
    path = Path(path).expanduser().resolve()
    if path == ROOT or ROOT in path.parents or path in ROOT.parents:
        raise ValueError("Le stockage Optuna doit etre HORS du depot.")
    return path


def config_hash(root=ROOT):
    """Empreinte des trois fichiers valides, sans exposer leur environnement."""
    digest = hashlib.sha256()
    for name in ("optuna", "search_spaces", "benchmark"):
        digest.update(name.encode())
        digest.update((Path(root) / "configs" / f"{name}.yaml").read_bytes())
    return digest.hexdigest()


def preflight_configuration(configs):
    """Refuse aussi les marqueurs en attente dans les champs facultatifs."""
    validate_configuration(configs)

    def inspect(value):
        if isinstance(value, dict):
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
        elif isinstance(value, str):
            normalized = (
                unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
            )
            if normalized.strip().lower() == "a confirmer":
                raise ValueError("Configuration incomplete : champ a confirmer.")

    inspect(configs)
    if configs["optuna"]["n_trials"] != 30:
        raise ValueError("Le budget valide est de 30 essais par modele.")
    partition = configs["optuna"]["partition"]
    if (
        partition["optuna_fraction"] != 0.2
        or partition["internal_train_fraction"] != 0.8
    ):
        raise ValueError("Le decoupage Optuna valide est 20/80 puis 80/20.")


def execution_metadata(audit, *, smoke):
    """Identifie code, donnees autorisees, configuration et versions de reprise."""
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            text=True,
        ).strip()
    )
    code = hashlib.sha256()
    for directory in ("benchmark", "models", "preprocessing", "validation", "data"):
        for path in sorted((ROOT / "ml" / "src" / directory).glob("*.py")):
            code.update(str(path.relative_to(ROOT)).encode())
            code.update(path.read_bytes())
    return {
        "git_commit": commit,
        "git_dirty": str(dirty).lower(),
        "config_hash": config_hash(),
        "code_hash": code.hexdigest(),
        "data_hash": audit["data_hash"],
        "mode": "smoke" if smoke else "full",
        "versions": {
            name: version(name)
            for name in (
                "optuna",
                "mlflow",
                "scikit-learn",
                "numpy",
                "pandas",
                "xgboost",
            )
        },
    }


def _parameters(frozen, name, spaces):
    params = model_parameters(name, spaces)
    for key, value in frozen.params.items():
        spec = spaces[name]["parameters"][key]
        if spec["type"] == "categorical" and any(
            isinstance(v, list) for v in spec["choices"]
        ):
            value = json.loads(value)
        params[key] = value
    return params


def restore_random_sequence(study, sampler, name, spaces):
    """Rejoue les tirages historiques via l'API publique, jamais les fits.

    RandomSampler n'enregistre pas son RNG dans SQLite. Repartir de seed 42
    sans ce rejeu repeterait le debut de la sequence apres une interruption.
    """
    for frozen in study.get_trials(deepcopy=False):
        for key in spaces[name]["parameters"]:
            if key in frozen.distributions:
                value = sampler.sample_independent(
                    study, frozen, key, frozen.distributions[key]
                )
                if value != frozen.params[key]:
                    raise ValueError("Sequence RNG incompatible : reprise refusee.")


def _row(result, number, params, free_bytes):
    row = {**result, "number": number, "params": params, "disk_free_bytes": free_bytes}
    row.setdefault("seconds", 0.0)
    if not math.isfinite(row["seconds"]) or row["seconds"] < 0:
        raise ValueError("Duree d'essai invalide.")
    if row["status"] == "COMPLETE":
        score = row.get("result", {}).get("average_precision")
        if score is None or not math.isfinite(score) or not 0 <= score <= 1:
            row = {key: value for key, value in row.items() if key != "result"}
            row.update(status="FAIL", reason="invalid_score")
    elif row["status"] != "FAIL":
        raise ValueError("Statut d'essai inconnu.")
    return row


def _tell(study, number, row):
    if row["status"] == "COMPLETE":
        study.tell(number, row["result"]["average_precision"])
    else:
        study.tell(number, state=TrialState.FAIL)


def simplicity_key(name, params):
    """Ordre de proposition explicite, jamais une selection finale automatique."""
    if name == "logreg":
        return (params["C"],)
    if name == "rf":
        return (
            params["n_estimators"],
            params["max_depth"],
            -params["min_samples_leaf"],
        )
    if name == "xgb":
        return (params["n_estimators"], params["max_depth"])
    if name == "nystroem_svc":
        return (params["n_components"], params["C"])
    sizes = params["hidden_layer_sizes"]
    return (sum(sizes), len(sizes), -params["alpha"])


def selection_proposal(name, rows, margin, *, smoke):
    """Liste les essais a <= marge du maximum, le plus simple d'abord."""
    complete = [row for row in rows if row["status"] == "COMPLETE"]
    best = max((row["result"]["average_precision"] for row in complete), default=None)
    candidates = (
        []
        if best is None
        else [
            row
            for row in complete
            if best - row["result"]["average_precision"] <= margin + 1e-12
        ]
    )
    candidates.sort(
        key=lambda row: (simplicity_key(name, row["params"]), row["number"])
    )
    return {
        "model": name,
        "margin": margin,
        "best_average_precision": best,
        "status": "smoke_only_not_for_selection"
        if smoke
        else "awaiting_Basma_validation",
        "final_parameters_written": False,
        "candidates": [
            {
                "number": row["number"],
                "average_precision": row["result"]["average_precision"],
                "params": row["params"],
            }
            for row in candidates
        ],
    }


def export_model(directory, name, summary, margin, *, smoke):
    """Ecrit des resultats agreges hors depot, sans transaction ni modele."""
    directory = external_directory(directory)
    rows = summary["trials"]
    columns = [
        "number",
        "status",
        "reason",
        "average_precision",
        "seconds",
        "params",
        "child_run_id",
        "beta",
        "winerror",
    ]
    table = [
        {
            "number": row["number"],
            "status": row["status"],
            "reason": row.get("reason"),
            "average_precision": row.get("result", {}).get("average_precision"),
            "seconds": row["seconds"],
            "params": json.dumps(row["params"], sort_keys=True),
            "child_run_id": row.get("child_run_id"),
            "beta": row.get("result", {}).get("beta"),
            "winerror": row.get("winerror"),
        }
        for row in rows
    ]
    pd.DataFrame(table, columns=columns).to_csv(
        directory / f"trials_{name}.csv", index=False
    )
    proposal = selection_proposal(name, rows, margin, smoke=smoke)
    (directory / f"proposal_{name}.json").write_text(
        json.dumps(proposal, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    (directory / f"summary_{name}.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return proposal


def run_model(
    name,
    configs,
    data,
    directory,
    tracker,
    metadata,
    *,
    smoke=False,
    resume=False,
    evaluate=None,
):
    """Execute au plus le budget total, echecs compris, avec reprise idempotente."""
    preflight_configuration(configs)
    directory = external_directory(directory)
    directory.mkdir(parents=True, exist_ok=True)
    tracked = subprocess.run(
        ["git", "-C", str(directory), "ls-files", "--", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.stdout.strip():
        raise ValueError("Le dossier d'etat contient deja des fichiers suivis par Git.")
    ignore = directory / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    elif ignore.read_text(encoding="utf-8").strip() != "*":
        raise ValueError("Le dossier externe doit etre integralement ignore par Git.")
    manifest = directory / "execution.json"
    if manifest.exists():
        if json.loads(manifest.read_text(encoding="utf-8")) != metadata:
            raise ValueError("Identite globale modifiee : reprise refusee.")
    else:
        manifest.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    settings, spaces = configs["optuna"], configs["search_spaces"]["models"]
    limit = 3 if smoke else settings["n_trials"]
    X, y, train, valid = data
    seed = settings["sampler"]["seed"]
    sampler = optuna.samplers.RandomSampler(seed=seed)
    storage = optuna.storages.RDBStorage(
        f"sqlite:///{(directory / 'studies.db').as_posix()}",
        engine_kwargs={"poolclass": NullPool, "connect_args": {"timeout": 30}},
    )
    study = None
    try:
        study = optuna.create_study(
            study_name=f"{metadata['mode']}-{name}",
            storage=storage,
            load_if_exists=resume,
            sampler=sampler,
            pruner=optuna.pruners.NopPruner(),
            direction=settings["direction"],
        )
        identity = {**metadata, "model": name, "trial_limit": limit}
        old_identity = study.user_attrs.get("identity")
        if old_identity is not None and old_identity != identity:
            raise ValueError(
                "Config, code, commit, donnees ou versions modifies : reprise refusee."
            )
        if len(study.trials) > limit:
            raise ValueError("L'etude depasse deja le budget valide.")
        study.set_user_attr("identity", identity)
        key = study.user_attrs.get("study_key") or uuid.uuid4().hex
        study.set_user_attr("study_key", key)
        tags = {key: str(value) for key, value in identity.items() if key != "versions"}
        tags["study_key"] = key
        parent = tracker.parent(study, tags)
        consumed = float(study.user_attrs.get("elapsed_seconds", 0.0))
        reservation = float(study.user_attrs.get("inflight_seconds", 0.0))
        if any(
            not math.isfinite(value) or value < 0 for value in (consumed, reservation)
        ):
            raise ValueError("Compteurs persistants de duree invalides.")
        if reservation:
            consumed += reservation
            study.set_user_attr("elapsed_seconds", consumed)
            study.set_user_attr("inflight_seconds", 0.0)
        # Un processus perdu ne recoit pas un score et ne consomme pas un nouvel essai.
        for frozen in study.get_trials(deepcopy=False):
            attr = f"record_{frozen.number}"
            row = study.user_attrs.get(attr)
            if frozen.state == TrialState.RUNNING:
                if row is None:
                    row = _row(
                        {
                            "status": "FAIL",
                            "reason": "interrupted_without_result",
                            "seconds": reservation,
                        },
                        frozen.number,
                        _parameters(frozen, name, spaces),
                        shutil.disk_usage(directory).free,
                    )
                    study.set_user_attr(attr, row)
                _tell(study, frozen.number, row)
            if row is None:
                raise ValueError("Resultat persistant manquant : reprise refusee.")
            child = tracker.child(study, frozen.number, parent, tags)
            row["child_run_id"] = child
            study.set_user_attr(attr, row)
            tracker.finish_trial(child, row)
        restore_random_sequence(study, sampler, name, spaces)
        started = monotonic()
        deadline = started + max(0, settings["study_timeout_seconds"] - consumed)
        stopped = False

        def snapshot():
            trials = study.get_trials(deepcopy=False)
            rows = [
                study.user_attrs[f"record_{trial.number}"]
                for trial in trials
                if trial.state.is_finished()
            ]
            scores = [
                row["result"]["average_precision"]
                for row in rows
                if row["status"] == "COMPLETE"
            ]
            result = {
                "model": name,
                "mode": metadata["mode"],
                "parent_run_id": parent,
                **timeout_summary(
                    rows, alert_fraction=settings["trial_timeout"]["alert_fraction"]
                ),
                "failed_count": sum(row["status"] == "FAIL" for row in rows),
                "other_failures": sum(
                    row["status"] == "FAIL"
                    and row.get("reason") not in {"trial_timeout", "study_timeout"}
                    for row in rows
                ),
                "best_average_precision": max(scores, default=None),
                "elapsed_seconds": consumed + monotonic() - started,
                "study_timeout": stopped,
                "trials": rows,
            }
            return result

        try:
            while len(study.trials) < limit:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    stopped = True
                    break
                trial = study.ask()
                params = suggest_parameters(trial, name, spaces)
                child = tracker.child(study, trial.number, parent, tags)
                free_bytes = shutil.disk_usage(directory).free
                print(
                    json.dumps(
                        {
                            "model": name,
                            "trial": trial.number,
                            "disk_free_bytes": free_bytes,
                        }
                    ),
                    flush=True,
                )
                study.set_user_attr(
                    "inflight_seconds",
                    min(settings["trial_timeout"]["seconds"], remaining),
                )
                result = (
                    evaluate(params, deadline)
                    if evaluate is not None
                    else run_in_subprocess(
                        trial_worker,
                        (name, params, X, y, train, valid, seed),
                        seconds=settings["trial_timeout"]["seconds"],
                        deadline=deadline,
                    )
                )
                row = _row(result, trial.number, params, free_bytes)
                row["child_run_id"] = child
                study.set_user_attr(f"record_{trial.number}", row)
                _tell(study, trial.number, row)
                # Enregistrer le resultat local AVANT l'appel reseau permet sa reprise.
                elapsed = consumed + monotonic() - started
                study.set_user_attr("elapsed_seconds", elapsed)
                study.set_user_attr("inflight_seconds", 0.0)
                tracker.finish_trial(child, row)
                if row.get("exception_type") is not None:
                    print(
                        json.dumps(
                            {
                                "model": name,
                                "trial": trial.number,
                                "error": row["exception_type"],
                                "errno": row.get("errno"),
                                "winerror": row.get("winerror"),
                            }
                        ),
                        flush=True,
                    )
                if row.get("errno") == 28:
                    raise OSError(28, "Espace disque insuffisant ; recherche arretee.")
                if row.get("winerror") is not None:
                    print(
                        f"ALERTE {name} essai {trial.number}: WinError {row['winerror']}",
                        flush=True,
                    )
                if row.get("result", {}).get("average_precision", 0) > 0.5:
                    print(
                        f"ALERTE {name}: PR-AUC > 0.5, verifier une fuite possible (smoke non conclusif).",
                        flush=True,
                    )
                current = snapshot()
                study.set_user_attr("elapsed_seconds", current["elapsed_seconds"])
                export_model(
                    directory,
                    name,
                    current,
                    settings["selection"]["min_pr_auc_gap"],
                    smoke=smoke,
                )
                print(
                    json.dumps(
                        {
                            key: value
                            for key, value in current.items()
                            if key != "trials"
                        }
                    ),
                    flush=True,
                )
                if current["timeout_alert"]:
                    print(f"ALERTE {name}: plus de 20 % de timeouts.", flush=True)
                if row.get("reason") == "study_timeout":
                    stopped = True
                    break
            stopped = stopped or monotonic() >= deadline
            summary = snapshot()
            study.set_user_attr("elapsed_seconds", summary["elapsed_seconds"])
            export_model(
                directory,
                name,
                summary,
                settings["selection"]["min_pr_auc_gap"],
                smoke=smoke,
            )
            tracker.finish_parent(
                parent, summary, status="KILLED" if stopped else "FINISHED"
            )
            return summary
        except (
            KeyboardInterrupt,
            OSError,
            RuntimeError,
            ValueError,
            mlflow.exceptions.MlflowException,
        ) as exc:
            summary = snapshot()
            study.set_user_attr("elapsed_seconds", summary["elapsed_seconds"])
            export_model(
                directory,
                name,
                summary,
                settings["selection"]["min_pr_auc_gap"],
                smoke=smoke,
            )
            try:
                tracker.finish_parent(
                    parent,
                    summary,
                    status="KILLED" if isinstance(exc, KeyboardInterrupt) else "FAILED",
                )
            except mlflow.exceptions.MlflowException:
                print(
                    "MLflow indisponible : statut parent non synchronise ; reprendre avec --resume.",
                    flush=True,
                )
            raise
    finally:
        storage.remove_session()
        storage.engine.dispose()


def main(argv=None):
    """Prevol, donnees filtrees, puis modeles sequentiels ; jamais de benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke", action="store_true", help="3 essais/modele, 4000 lignes maximum"
    )
    parser.add_argument("--model", choices=MODEL_NAMES)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--state-dir",
        type=Path,
        help="Dossier persistant hors du projet, ignore par Git",
    )
    args = parser.parse_args(argv)
    try:
        configs = load_configuration()
        preflight_configuration(configs)
        uri = get_tracking_uri()
        if not uri.startswith(("http://", "https://")):
            raise ValueError("Serveur MLflow HTTP requis ; aucun repli SQLite.")
        connection = check_tracking_connection(uri, timeout_seconds=10)
        print(json.dumps({"connectivity": connection}), flush=True)
        if connection["status"] != "PASS":
            raise RuntimeError(
                "MLflow indisponible : aucun essai lance, Docker non demarre."
            )
        mode = "smoke" if args.smoke else "full"
        default = (
            Path(os.environ.get("LOCALAPPDATA", Path.home()))
            / "fintech-optuna"
            / f"{mode}-{config_hash()[:12]}"
        )
        directory = external_directory(args.state_dir or default)
        X, y, train, valid, audit = load_optuna_data(
            ROOT / "data/raw/fraudTrain.csv", configs["optuna"], smoke=args.smoke
        )
        print(
            json.dumps(
                {"data_audit": audit, "external_state_directory": str(directory)}
            ),
            flush=True,
        )
        metadata = execution_metadata(audit, smoke=args.smoke)
        summaries = []
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        tracker = SearchTracking(uri)
        for name in MODEL_NAMES:
            if args.model is not None and name != args.model:
                continue
            summary = run_model(
                name,
                configs,
                (X, y, train, valid),
                directory,
                tracker,
                metadata,
                smoke=args.smoke,
                resume=args.resume,
            )
            summaries.append(summary)
            if summary["study_timeout"]:
                print(
                    "ARRET : budget de 3 h epuise. Demander une reduction identique pour les cinq modeles.",
                    flush=True,
                )
                return 2
        proposals = [
            json.loads(path.read_text(encoding="utf-8"))
            for name in MODEL_NAMES
            if (path := directory / f"proposal_{name}.json").is_file()
        ]
        path = directory / "selection_proposal.json"
        path.write_text(
            json.dumps(
                {"metadata": metadata, "proposals": proposals},
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "proposal_file": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "best_params_written": False,
                }
            ),
            flush=True,
        )
        return 0 if all(summary["completed"] > 0 for summary in summaries) else 1
    except KeyboardInterrupt:
        print(
            "Interruption : etat conserve hors depot. Reprendre avec --resume.",
            flush=True,
        )
        return 130
    except (
        ValueError,
        RuntimeError,
        OSError,
        mlflow.exceptions.MlflowException,
        optuna.exceptions.DuplicatedStudyError,
    ) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "exception_type": type(exc).__name__,
                    "winerror": getattr(exc, "winerror", None),
                    "error": _safe_error(exc),
                }
            ),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
