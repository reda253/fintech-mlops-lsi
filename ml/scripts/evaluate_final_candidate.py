"""Évaluation agrégée du candidat D44 figé ; ne réentraîne aucun objet."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "ml" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ml.scripts.final_history import (
    HISTORY_DIR,
    REMEASUREMENT_NOTICE,
    history_report_lines,
    load_previous_evaluation,
)
from ml.scripts.final_journal import check_authorization, record_event, reserve_source
from ml.scripts.final_metrics import (
    BOOTSTRAP_SEED,
    N_BOOTSTRAP,
    bootstrap_intervals,
    decision_metrics,
    weighted_metrics,
)
from ml.scripts.final_tracking import publish_saved
from ml.src.data.load_data import split_chronologically
from ml.src.final.train_final import evaluate_sets, prediction_membership
from ml.src.validation.fold_data import guard_training_source

FINAL_DECISION_ID = "D48"
AGE_BINS = [0, 25, 35, 45, 55, 65, 120]
AGE_LABELS = ["0-25", "26-35", "36-45", "46-55", "56-65", "66-120"]
REQUIRED = [
    "trans_date_trans_time",
    "dob",
    "amt",
    "category",
    "gender",
    "state",
    "city_pop",
    "lat",
    "long",
    "merch_lat",
    "merch_long",
    "is_fraud",
]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_write(path: Path, content: bytes) -> None:
    """Un fichier incomplet ne remplace jamais sa destination."""
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_predictions(output: Path, details: dict) -> str:
    rows = pd.DataFrame(
        {
            "label": details["labels"],
            "fraud_probability": details["probabilities"],
            "include_0": details["members"][:, 0].astype(int),
            "include_1": details["members"][:, 1].astype(int),
            "gender": details["gender"],
            "age_group": details["age_group"],
        }
    )
    path = output / "predictions.csv"
    atomic_write(path, rows.to_csv(index=False).encode("utf-8"))
    digest = sha256(path)
    atomic_write(
        output / "artifact_manifest.json",
        json.dumps(
            {
                "status": "predictions_saved",
                "rows": len(rows),
                "artifacts": {"predictions.csv": digest},
            },
            indent=2,
        ).encode("utf-8"),
    )
    return digest


def preflight_output(output: Path, source: Path | None) -> None:
    parent = output.resolve().parent
    if not parent.is_dir():
        raise ValueError("Parent de sortie absent ou montage indisponible")
    # Réserve conservatrice pour CSV, prédictions et rapports ; pas une porte métier.
    required = max(1024 * 1024, 3 * source.stat().st_size if source else 0)
    if shutil.disk_usage(parent).free < required:
        raise ValueError("Espace disque insuffisant pour la sauvegarde avant analyse")
    fd, probe = tempfile.mkstemp(prefix=".write-check-", dir=parent)
    os.close(fd)
    Path(probe).unlink()


def validate_candidate(model, reference: dict) -> None:
    if not np.isclose(
        reference.get("selected_alpha", np.nan), 0.02, rtol=0, atol=1e-12
    ) or not np.isclose(model.alpha, 0.02, rtol=0, atol=1e-12):
        raise ValueError("Le candidat ou la référence ne correspond pas à alpha=0.02")
    row = next((x for x in reference["alpha_results"] if x["alpha"] == 0.02), None)
    if row is None or row.get("status") != "eligible":
        raise ValueError("Seuils du candidat absents de la référence D44")
    q = row["quantiles"]
    if (
        not np.isclose(model.threshold_legit, q["0"], rtol=1e-12, atol=1e-15)
        or not np.isclose(model.threshold_fraud, q["1"], rtol=1e-12, atol=1e-15)
        or model.preprocessor is None
        or model.classifier is None
    ):
        raise ValueError("Seuils ou composants du candidat différents de D44")


def synthetic_data() -> pd.DataFrame:
    base = {
        "trans_date_trans_time": "2020-06-01 12:00:00",
        "category": "shopping_net",
        "state": "NY",
        "city_pop": 50000,
        "lat": 40.0,
        "long": -73.0,
        "merch_lat": 40.1,
        "merch_long": -73.1,
    }
    return pd.DataFrame(
        [
            {**base, "dob": dob, "gender": gender, "amt": amt, "is_fraud": label}
            for dob, gender, amt, label in [
                ("2000-06-01", "F", 5.0, 0),
                ("1980-01-01", "M", 25.0, 0),
                ("1960-01-01", "F", 500.0, 1),
                ("1950-01-01", "M", 900.0, 1),
            ]
        ]
    )


def evaluate(
    model, frame: pd.DataFrame, *, return_details: bool = False, on_predictions=None
):
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes : {sorted(missing)}")
    labels = pd.to_numeric(frame["is_fraud"], errors="raise").to_numpy()
    if set(np.unique(labels)) != {0, 1}:
        raise ValueError("Les deux classes 0 et 1 sont requises")
    labels = labels.astype(int)
    trans = pd.to_datetime(
        frame["trans_date_trans_time"], format="%Y-%m-%d %H:%M:%S", errors="raise"
    )
    dob = pd.to_datetime(frame["dob"], format="%Y-%m-%d", errors="raise")
    before = (trans.dt.month < dob.dt.month) | (
        (trans.dt.month == dob.dt.month) & (trans.dt.day < dob.dt.day)
    )
    ages = trans.dt.year - dob.dt.year - before.astype(int)
    if ages.isna().any() or ((ages < 0) | (ages > 120)).any():
        raise ValueError("Âge invalide")
    bins = pd.cut(ages, bins=AGE_BINS, labels=AGE_LABELS, include_lowest=True)
    if bins.isna().any() or frame["gender"].isna().any():
        raise ValueError("Genre ou tranche d’âge manquant")
    features_frame = frame.drop(columns="is_fraud")
    batch = getattr(model, "batch_probabilities", None)
    if callable(batch):
        probabilities = np.asarray(batch(features_frame), dtype=float)
    else:
        if (
            getattr(model, "beta", None) is not None
            or getattr(model, "calibrator", None) is not None
        ):
            raise ValueError(
                "Correction ou calibrateur externe sans batch_probabilities : évaluation refusée"
            )
        features = model.preprocessor.transform(features_frame)
        probabilities = np.asarray(
            model.classifier.predict_proba(features)[:, 1], dtype=float
        )
    if (
        len(probabilities) != len(labels)
        or not np.isfinite(probabilities).all()
        or ((probabilities < 0) | (probabilities > 1)).any()
    ):
        raise ValueError("Probabilités invalides")
    members = prediction_membership(
        probabilities, {0: model.threshold_legit, 1: model.threshold_fraud}
    )
    details = {
        "labels": labels,
        "probabilities": probabilities,
        "members": members,
        "gender": frame["gender"].astype(str).to_numpy(),
        "age_group": bins.astype(str).to_numpy(),
    }
    if on_predictions is not None:
        on_predictions(
            details
        )  # Immédiatement après inférence, avant métriques et bootstrap.
    overall = evaluate_sets(members, labels)
    weighted = weighted_metrics(labels, probabilities, members, np.ones(len(labels)))
    expected_pr_auc = float(average_precision_score(labels, probabilities))
    if not np.isclose(weighted["pr_auc"], expected_pr_auc, rtol=1e-12, atol=1e-12):
        raise ValueError("Calcul PR-AUC incohérent")
    overall.update(weighted)
    overall["n_transactions"] = len(labels)
    overall["fraud_coverage_floor"] = (1 - model.alpha) - 0.02
    coverage = overall["coverage_by_class"]["1"]
    overall["fraud_coverage_floor_met"] = (
        coverage >= overall["fraud_coverage_floor"] if coverage is not None else None
    )
    overall["review_capacity_met"] = overall["review_rate"] <= 0.02

    predicted = probabilities >= 0.5  # convention existante de FraudDetectorModel
    review = members.sum(axis=1) != 1
    groups = []
    group_masks = {}
    for attribute, values, names in (
        (
            "gender",
            frame["gender"].astype(str).to_numpy(),
            sorted(frame["gender"].astype(str).unique()),
        ),
        ("age", bins.astype(str).to_numpy(), AGE_LABELS),
    ):
        for name in names:
            mask = values == name
            group_masks[f"{attribute}:{name}"] = mask
            positives = int(np.sum(mask & (labels == 1)))
            negatives = int(np.sum(mask & (labels == 0)))
            n = int(mask.sum())
            groups.append(
                {
                    "attribute": attribute,
                    "group": name,
                    "n": n,
                    **decision_metrics(labels, members, mask.astype(float)),
                    "frauds": positives,
                    "legitimate": negatives,
                    "recall_point_prediction": float(
                        np.sum(mask & (labels == 1) & predicted) / positives
                    )
                    if positives
                    else None,
                    "false_positive_rate_point_prediction": float(
                        np.sum(mask & (labels == 0) & predicted) / negatives
                    )
                    if negatives
                    else None,
                    "review_rate": float(review[mask].mean()) if n else None,
                }
            )
    result = (overall, pd.DataFrame(groups))
    if return_details:
        return (
            *result,
            {**details, "group_masks": group_masks},
        )
    return result


def load_latency_sample(source: Path, *, sample_size=100, seed=42) -> pd.DataFrame:
    """Dates seules hors development ; aucune étiquette chargée."""
    source = guard_training_source(source)
    date_column = "trans_date_trans_time"
    dates = pd.read_csv(source, usecols=[date_column])
    dates[date_column] = pd.to_datetime(
        dates[date_column], format="%Y-%m-%d %H:%M:%S", errors="raise"
    )
    splits = split_chronologically(dates, sort_if_needed=True)
    dev = splits["development"]
    if dev.empty or sample_size < 1:
        raise ValueError("Échantillon development vide ou taille invalide")
    if dev[date_column].max() >= splits["probability_calibration"][date_column].min():
        raise ValueError("Frontière development non strictement chronologique")
    chosen = np.random.default_rng(seed).choice(
        dev.index.to_numpy(), size=min(sample_size, len(dev)), replace=False
    )
    positions = {int(i) for i in chosen}
    frame = pd.read_csv(
        source,
        usecols=[c for c in REQUIRED if c != "is_fraud"],
        skiprows=lambda row: row > 0 and row - 1 not in positions,
    )
    if len(frame) != len(positions):
        raise ValueError("Effectif d'échantillon development incorrect")
    frame.attrs.update(zone="development", sample_seed=seed)
    return frame


def measure_latency(model, records=None, *, sample_size=100, seed=42) -> dict:
    """1 000 appels unitaires sur un échantillon déterministe ; aucun fit."""
    if not hasattr(model, "predict_one"):
        return {"status": "UNVERIFIED", "reason": "predict_one indisponible"}
    from threadpoolctl import threadpool_limits

    if sample_size < 1:
        raise ValueError("sample_size doit être positif")
    if records is None:
        records = synthetic_data().drop(columns="is_fraud").to_dict(orient="records")
    if not isinstance(records, pd.DataFrame):
        records = list(records)
    if len(records) == 0:
        raise ValueError("Échantillon de latence vide")
    indices = np.random.default_rng(seed).choice(
        len(records), min(sample_size, len(records)), replace=False
    )
    sample_records = (
        records.iloc[indices]
        .drop(columns="is_fraud", errors="ignore")
        .to_dict(orient="records")
        if isinstance(records, pd.DataFrame)
        else [records[int(i)] for i in indices]
    )
    samples = []
    with threadpool_limits(limits=1):
        for i in range(20):
            model.predict_one(sample_records[i % len(sample_records)])
        for i in range(1000):
            start = time.perf_counter_ns()
            model.predict_one(sample_records[i % len(sample_records)])
            samples.append((time.perf_counter_ns() - start) / 1_000_000)
    values = np.asarray(samples)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    bootstrap_latencies = np.empty((N_BOOTSTRAP, 2))
    for start in range(0, N_BOOTSTRAP, 200):
        end = min(start + 200, N_BOOTSTRAP)
        sample = values[rng.integers(0, len(values), size=(end - start, len(values)))]
        bootstrap_latencies[start:end] = np.percentile(sample, [50, 95], axis=1).T
    return {
        "status": "measured",
        "warmups": 20,
        "calls": 1000,
        "sample_rows": len(sample_records),
        "sample_seed": seed,
        "threads": 1,
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
        "p50_ci95_ms": [
            float(x) for x in np.quantile(bootstrap_latencies[:, 0], [0.025, 0.975])
        ],
        "p95_ci95_ms": [
            float(x) for x in np.quantile(bootstrap_latencies[:, 1], [0.025, 0.975])
        ],
        "bootstrap": {
            "resamples": N_BOOTSTRAP,
            "seed": BOOTSTRAP_SEED,
            "unit": "timed_call",
        },
        "scope": "pipeline local ; sans réseau ni service Docker",
    }


def quality_gates(overall, latency, comparison_kind, comparison_pr_auc):
    """Portes vérifiables ; comparaison et registry non supposés disponibles."""
    floor = overall["fraud_coverage_floor"]
    coverage = overall["coverage_by_class"]
    gates = {
        "coverage_by_class": {
            "status": "PASS"
            if all(
                coverage[str(c)] is not None and coverage[str(c)] >= floor
                for c in (0, 1)
            )
            else "FAIL",
            "floor": floor,
            "observed": coverage,
        },
        "review_capacity": {
            "status": "PASS" if overall["review_rate"] <= 0.02 else "FAIL",
            "limit": 0.02,
            "observed": overall["review_rate"],
        },
        "latency": {
            "status": ("PASS" if latency["p95_ms"] < 50 else "FAIL")
            if latency["status"] == "measured"
            else "UNVERIFIED",
            "limit_ms": 50,
            "observed_ms": latency.get("p95_ms"),
        },
        "registry_smoke": {
            "status": "UNVERIFIED",
            "reason": "chargement du registry et 100 transactions de référence non vérifiés",
        },
    }
    if comparison_kind is None:
        gates["non_regression"] = {
            "status": "UNVERIFIED",
            "reason": "champion ou baseline logistique non fournie",
        }
    else:
        threshold = (
            comparison_pr_auc - 0.01
            if comparison_kind == "champion"
            else comparison_pr_auc
        )
        gates["non_regression"] = {
            "status": "PASS" if overall["pr_auc"] >= threshold else "FAIL",
            "comparison_kind": comparison_kind,
            "reference_pr_auc": comparison_pr_auc,
            "threshold": threshold,
            "observed": overall["pr_auc"],
        }
    return gates


def resolve_journal(value: Path | None) -> Path | None:
    """Choix explicite prioritaire ; aucun chemin implicite propre à un poste."""
    configured = value or os.environ.get("FINAL_EVALUATION_JOURNAL")
    if not configured:
        return None
    path = Path(configured).expanduser().resolve()
    if path.is_relative_to(ROOT.resolve()):
        raise ValueError("Le journal central doit être hors dépôt")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument(
        "--previous-evaluation",
        type=Path,
        help="Dossier des métriques et du rapport du 10 novembre ; obligatoire pour D48",
    )
    parser.add_argument("--output-dir", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--synthetic", action="store_true")
    mode.add_argument("--republish", type=Path)
    mode.add_argument("--source", type=Path)
    parser.add_argument("--model-sha256")
    parser.add_argument("--source-sha256")
    parser.add_argument("--reason")
    parser.add_argument("--decision-id")
    parser.add_argument("--protocol-revision")
    parser.add_argument(
        "--protocol-file",
        type=Path,
        help="Texte du protocole approuvé, empreinte liée à l'autorisation",
    )
    parser.add_argument(
        "--authorization",
        type=Path,
        help="Autorisation explicite de l'équipe, JSON hors dépôt",
    )
    parser.add_argument("--latency-source", type=Path)
    parser.add_argument(
        "--journal",
        type=Path,
        help="Journal central persistant hors dépôt ; sinon FINAL_EVALUATION_JOURNAL",
    )
    parser.add_argument("--confirm-final-test", action="store_true")
    parser.add_argument("--tracking-uri")
    parser.add_argument(
        "--no-mlflow", action="store_true", help="Tests synthétiques uniquement"
    )
    parser.add_argument("--comparison-kind", choices=("champion", "logreg"))
    parser.add_argument("--comparison-pr-auc", type=float)
    parser.add_argument(
        "--code-revision", help="Révision fournie explicitement ; aucune commande Git"
    )
    args = parser.parse_args(argv)
    if args.republish is not None:
        if any(
            (
                args.model,
                args.reference,
                args.previous_evaluation,
                args.output_dir,
                args.source,
                args.journal,
                args.no_mlflow,
                args.confirm_final_test,
                args.decision_id,
                args.protocol_revision,
                args.latency_source,
                args.protocol_file,
                args.authorization,
                args.reason,
                args.source_sha256,
                args.model_sha256,
            )
        ):
            parser.error(
                "--republish utilise uniquement le dossier sauvegardé et éventuellement --tracking-uri"
            )
        state = publish_saved(args.republish, args.tracking_uri)
        print(json.dumps(state))
        return 0 if state["status"] == "published" else 2
    if not args.model or not args.reference or not args.output_dir:
        parser.error("--model, --reference et --output-dir sont requis")
    if args.no_mlflow and not args.synthetic:
        parser.error("--no-mlflow est réservé au contrôle synthétique")
    if (args.comparison_kind is None) != (args.comparison_pr_auc is None):
        parser.error("Fournir ensemble --comparison-kind et --comparison-pr-auc")
    if args.comparison_pr_auc is not None and (
        not np.isfinite(args.comparison_pr_auc) or not 0 <= args.comparison_pr_auc <= 1
    ):
        parser.error("La PR-AUC de référence doit être finie et dans [0,1]")
    if args.output_dir.exists() or args.output_dir.resolve().is_relative_to(
        ROOT.resolve()
    ):
        parser.error("Le dossier de sortie doit être neuf et hors dépôt")
    if args.source is not None:
        if args.decision_id and args.decision_id != FINAL_DECISION_ID:
            parser.error(
                f"Décision {args.decision_id} refusée : {FINAL_DECISION_ID} requise pour cette évaluation"
            )
        args.journal = resolve_journal(args.journal)
        required = {
            "--confirm-final-test": args.confirm_final_test,
            "--journal ou FINAL_EVALUATION_JOURNAL": args.journal,
            "--model-sha256": args.model_sha256,
            "--source-sha256": args.source_sha256,
            "--decision-id": args.decision_id,
            "--protocol-revision": args.protocol_revision,
            "--protocol-file": args.protocol_file,
            "--authorization": args.authorization,
            "--reason": args.reason,
            "--latency-source": args.latency_source,
        }
        if args.decision_id == "D48":
            required["--previous-evaluation"] = args.previous_evaluation
        missing = [key for key, value in required.items() if not value]
        if missing:
            parser.error("Test final : arguments manquants : " + ", ".join(missing))
        if args.source.name.lower() != "fraudtest.csv":
            parser.error("Nom de source finale non autorisé")
        args.source_sha256 = args.source_sha256.lower()
        if args.authorization.resolve().is_relative_to(ROOT.resolve()):
            parser.error("L'autorisation doit être hors dépôt")
    if args.decision_id == "D48" and args.previous_evaluation is None:
        parser.error("D48 : --previous-evaluation est obligatoire avant lecture")
    model_hash = sha256(args.model)
    if args.model_sha256 and model_hash.lower() != args.model_sha256.lower():
        raise ValueError("SHA-256 du modèle différent de celui demandé")
    model = joblib.load(args.model)
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    validate_candidate(model, reference)
    previous = None
    previous_payloads = {}
    if args.previous_evaluation is not None:
        previous, previous_payloads = load_previous_evaluation(
            args.previous_evaluation,
            model_hash,
            args.source_sha256,
            model.alpha,
        )
    authorization = None
    protocol_hash = None
    if args.synthetic:
        latency_frame = synthetic_data()
    else:
        protocol_hash = sha256(args.protocol_file)
        authorization = json.loads(args.authorization.read_text(encoding="utf-8"))
        check_authorization(
            args.journal,
            authorization,
            source_sha256=args.source_sha256,
            model_sha256=model_hash,
            decision_id=args.decision_id,
            protocol_sha256=protocol_hash,
            reason=args.reason,
        )
        latency_frame = load_latency_sample(args.latency_source)
        # Valide la frame de latence avec le preprocessing figé, sans aucun fit.
        transformed = model.preprocessor.transform(latency_frame)
        if not np.isfinite(np.asarray(transformed)).all():
            raise ValueError("Source de latence invalide : valeurs non finies")
    preflight_output(args.output_dir, args.source)
    latency = measure_latency(model, latency_frame)
    latency["sample_source"] = "synthetic" if args.synthetic else "development"
    args.output_dir.mkdir(exist_ok=False)
    if previous is not None:
        history_dir = args.output_dir / HISTORY_DIR
        history_dir.mkdir()
        for name, raw_bytes in previous_payloads.items():
            atomic_write(history_dir / name, raw_bytes)
    if args.synthetic:
        frame = latency_frame
        source_hash = None
    else:
        launch_id = reserve_source(
            args.journal,
            args.source.name,
            args.source_sha256,
            model_hash,
            args.reason,
            decision_id=args.decision_id,
            protocol_revision=args.protocol_revision,
            protocol_sha256=protocol_hash,
            authorization=authorization,
        )
        with args.source.open("rb") as stream:
            raw = stream.read()
        source_hash = hashlib.sha256(raw).hexdigest()
        if source_hash != args.source_sha256:
            raise ValueError(
                "SHA-256 source différent de l'empreinte déclarée ; aucune analyse"
            )
        frame = pd.read_csv(io.BytesIO(raw), usecols=REQUIRED)
        del raw
    saved = {}

    def persist(details):
        saved["sha256"] = save_predictions(args.output_dir, details)
        if not args.synthetic:
            record_event(
                args.journal,
                launch_id,
                "predictions_saved",
                predictions_sha256=saved["sha256"],
            )

    overall, groups, details = evaluate(
        model, frame, return_details=True, on_predictions=persist
    )
    bootstrap = bootstrap_intervals(
        details["labels"],
        details["probabilities"],
        details["members"],
        details["group_masks"],
    )
    gates = quality_gates(
        overall, latency, args.comparison_kind, args.comparison_pr_auc
    )
    result = {
        "scope": "synthetic_only" if args.synthetic else "final_test",
        "model_status": "provisional",
        "decision_id": args.decision_id,
        "protocol_revision": args.protocol_revision,
        "protocol_sha256": protocol_hash,
        "model_sha256": model_hash,
        "source_sha256": source_hash,
        "reference_sha256": sha256(args.reference),
        "evaluation_script_sha256": sha256(Path(__file__)),
        "metrics_module_sha256": sha256(ROOT / "ml" / "scripts" / "final_metrics.py"),
        "tracking_module_sha256": sha256(ROOT / "ml" / "scripts" / "final_tracking.py"),
        "code_revision": args.code_revision,
        "versions": {
            "python": platform.python_version(),
            **{
                name: importlib.metadata.version(name)
                for name in ("numpy", "pandas", "scikit-learn", "xgboost", "mlflow")
            },
        },
        "bootstrap": bootstrap["parameters"],
        "latency": latency,
        "quality_gates": gates,
        "promotion_ready": False,
        "alpha": model.alpha,
        "threshold_legit": model.threshold_legit,
        "threshold_fraud": model.threshold_fraud,
        "overall": overall,
        "point_metrics_role": "secondary_at_threshold_0.5",
        "fairness_metrics_role": "conformal_operational_decisions",
        "fairness": groups.replace({np.nan: None}).to_dict(orient="records"),
        "limitations": [
            "Les intervalles bootstrap percentile supposent des transactions indépendantes ; la dépendance entre transactions d'une carte et la dérive ne sont pas corrigées.",
            "Le seuil ponctuel 0.5 est celui de FraudDetectorModel ; le seuil F1 ajusté pour le modèle final n'est pas fourni et reste à clarifier.",
            "La latence locale n'inclut ni réseau ni conteneur ; la porte registry reste non vérifiée.",
            "Les métriques principales par groupe suivent les décisions conformes ; les métriques ponctuelles à 0.5 sont secondaires.",
            "La garde lie décision, source, modèle et texte du protocole ; elle protège contre les accidents, pas contre une édition volontaire du journal et de son autorisation.",
        ],
    }
    if previous is not None:
        result["previous_evaluation"] = previous
        result["measurement"] = {
            "number": 2,
            "post_hoc": True,
            "independent": False,
            "notice": REMEASUREMENT_NOTICE,
            "purpose": "missing_bootstrap_and_operational_fairness_no_selection",
        }
    result["predictions_sha256"] = saved["sha256"]
    atomic_write(
        args.output_dir / "final_metrics.json",
        (
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8"),
    )
    atomic_write(
        args.output_dir / "fairness_groups.csv",
        groups.to_csv(index=False).encode("utf-8"),
    )
    atomic_write(
        args.output_dir / "bootstrap_intervals.json",
        (
            json.dumps(bootstrap, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8"),
    )
    lines = [
        "# Évaluation du candidat",
        "",
        f"Périmètre : {result['scope']} ; modèle provisoire ; alpha = {model.alpha}.",
        "",
        f"PR-AUC : {overall['pr_auc']:.6f}",
        f"Couverture par classe : {overall['coverage_by_class']}",
        f"Taux de revue : {overall['review_rate']:.6f}",
        f"Erreur parmi les décisions automatiques : {overall['automatic_error_rate']}",
        "",
        "Audit par genre et âge : voir fairness_groups.csv (effectifs inclus).",
        f"Bootstrap : {N_BOOTSTRAP} tirages, seed {BOOTSTRAP_SEED}, percentile 95 %, unité transaction ; détails : bootstrap_intervals.json.",
        f"Portes de qualité : {gates}. Aucune promotion automatique.",
        "",
        *[f"- {x}" for x in result["limitations"]],
    ]
    if previous is not None:
        lines.extend(history_report_lines(previous, overall))
    lines.extend(
        [
            "",
            "## Métriques et intervalles bootstrap",
            "",
            "| Mesure | Valeur | IC 95 % | Tirages valides |",
            "|---|---:|---|---:|",
        ]
    )
    for name, interval in bootstrap["overall"].items():
        value = overall.get(name)
        display_name = (
            f"{name} (secondaire, seuil 0,5)"
            if name.endswith("_point_prediction")
            else name
        )
        lines.append(
            f"| {display_name} | {value} | {interval['ci95']} | {interval['valid_resamples']}/{N_BOOTSTRAP} |"
        )
    lines.extend(
        [
            "",
            "## Équité : intervalles bootstrap",
            "",
            "Décisions réelles : [1] bloque, [0] approuve, [] et [0,1] partent en revue. Les fraudes interceptées incluent blocage et revue.",
            "",
            "| Groupe | Effectif | Fraudes | Fraudes bloquées et IC | Fraudes interceptées et IC | Légitimes bloqués et IC | Revue et IC |",
            "|---|---:|---:|---|---|---|---|",
        ]
    )

    def show(value):
        if value is None or (
            isinstance(value, (float, np.floating)) and not np.isfinite(value)
        ):
            return "indéfini"
        return str(value)

    for _, group in groups.iterrows():
        intervals = bootstrap["groups"][f"{group['attribute']}:{group['group']}"]
        cells = [
            f"{show(group[name])} ; {show(intervals[name]['ci95'])}"
            for name in (
                "auto_block_fraud_rate",
                "fraud_interception_rate",
                "auto_block_legitimate_rate",
                "review_rate",
            )
        ]
        lines.append(
            f"| {group['attribute']}:{group['group']} | {group['n']} | {group['frauds']} | "
            + " | ".join(cells)
            + " |"
        )
    lines.extend(
        [
            "",
            "### Mesures secondaires au seuil ponctuel 0,5",
            "",
            "Ces mesures ne décrivent pas la politique de décision de la plateforme.",
            "",
            "| Groupe | Rappel et IC | Faux positifs et IC |",
            "|---|---|---|",
        ]
    )
    for _, group in groups.iterrows():
        intervals = bootstrap["groups"][f"{group['attribute']}:{group['group']}"]
        lines.append(
            f"| {group['attribute']}:{group['group']} | {show(group['recall_point_prediction'])} ; {show(intervals['recall_point_prediction']['ci95'])} | {show(group['false_positive_rate_point_prediction'])} ; {show(intervals['false_positive_rate_point_prediction']['ci95'])} |"
        )
    lines.extend(["", f"Latence locale et intervalles : {latency}."])
    atomic_write(
        args.output_dir / "final_report.md", ("\n".join(lines) + "\n").encode("utf-8")
    )
    artifacts = (
        "final_metrics.json",
        "final_report.md",
        "fairness_groups.csv",
        "bootstrap_intervals.json",
        "predictions.csv",
    )
    manifest = {
        "status": "complete",
        "artifacts": {name: sha256(args.output_dir / name) for name in artifacts},
    }
    if previous is not None:
        manifest["artifacts"].update(previous["artifacts"])
    atomic_write(
        args.output_dir / "artifact_manifest.json",
        (json.dumps(manifest, indent=2) + "\n").encode("utf-8"),
    )
    if args.journal and not args.synthetic:
        record_event(
            args.journal,
            launch_id,
            "completed",
            output=str(args.output_dir),
            predictions_sha256=saved["sha256"],
        )
    publication = (
        {"status": "skipped_synthetic"}
        if args.no_mlflow
        else publish_saved(args.output_dir, args.tracking_uri)
    )
    print(
        json.dumps(
            {
                "publication": publication,
                "status": "completed",
                "scope": result["scope"],
                "rows": overall["n_transactions"],
                "model_sha256": model_hash,
                "output": str(args.output_dir),
            }
        )
    )
    return 0 if publication["status"] in {"published", "skipped_synthetic"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
