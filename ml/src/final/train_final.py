"""Entraînement final P2 ; la CLI ne lit que data/raw/fraudTrain.csv."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from math import ceil
from numbers import Integral
from pathlib import Path
from uuid import uuid4

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.special import logit
from scipy.stats import binomtest
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

ML_SRC = Path(__file__).resolve().parents[1]
if str(ML_SRC) not in sys.path:
    sys.path.insert(0, str(ML_SRC))

ROOT = ML_SRC.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.load_data import (
    DATE_COLUMN,
    TRAIN_COLUMNS,
    load_training_dataset,
    split_chronologically,
)
from models.factory import build_model
from validation.fold_data import correct_proba, guard_training_source

from ml.src.preprocessing.pipeline import (
    build_preprocessing_pipeline,
    split_features_target,
)

ALPHAS = (0.01, 0.05, 0.10)
SEED = 42
REVIEW_CAPACITY = 0.02
PROBABILITY_WEIGHTS = (1, 1)
CONFORMAL_WEIGHTS = (2, 1, 1)
ZONE_NAMES = ("development", "probability_calibration", "conformal_calibration")


def protocol_snapshot(params: dict, digest: str) -> dict:
    """Identité du protocole comparée AVANT toute lecture de la source."""
    return {
        "version": 1,
        "alphas": list(ALPHAS),
        "outer_fractions": [0.70, 0.15, 0.15],
        "probability_weights": list(PROBABILITY_WEIGHTS),
        "conformal_weights": list(CONFORMAL_WEIGHTS),
        "review_capacity": REVIEW_CAPACITY,
        "xgb_params": params,
        "best_params_sha256": digest,
        "seed": SEED,
        "undersampling_ratio": 10,
    }


@contextmanager
def launch_audit(journal: Path, source: Path, protocol: dict, change_reason: str = ""):
    """Journal append-only, verrou exclusif et accord motivé pour tout changement.

    Le même chemin doit être conservé entre lancements ; ce journal local n'est
    pas un dispositif anti-altération contre la suppression volontaire du fichier.
    """
    source = guard_training_source(source)
    journal = journal.resolve()
    if journal.is_relative_to(ROOT.resolve()):
        raise ValueError("Le journal doit rester hors du dépôt")
    journal.parent.mkdir(parents=True, exist_ok=True)
    lock = journal.with_suffix(journal.suffix + ".lock")
    try:
        lock_file = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError(
            "Un lancement utilise déjà ce journal (verrou présent)"
        ) from exc
    with lock_file:
        try:
            entries = (
                [
                    json.loads(line)
                    for line in journal.read_text(encoding="utf-8").splitlines()
                ]
                if journal.exists()
                else []
            )
            previous = [e for e in entries if e.get("event") == "launch_started"]
            current = {"source": str(source), "protocol": protocol}
            changed = bool(previous) and previous[-1]["configuration"] != current
            if changed and not change_reason.strip():
                raise ValueError(
                    "Protocole modifié : --protocol-change-reason requis avant lecture"
                )
            launch_id = uuid4().hex

            def record(event, **details):
                entry = {
                    "utc": datetime.now(UTC).isoformat(),
                    "launch_id": launch_id,
                    "event": event,
                    **details,
                }
                with journal.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(entry, ensure_ascii=False, allow_nan=False) + "\n"
                    )
                    stream.flush()
                    os.fsync(stream.fileno())

            if changed:
                record(
                    "protocol_change_acknowledged",
                    reason=change_reason.strip(),
                    previous=previous[-1]["configuration"],
                    replacement=current,
                )
            record("launch_started", configuration=current)
            try:
                yield record
            except BaseException as exc:
                record("launch_failed", exception_type=type(exc).__name__)
                raise
            else:
                record("launch_completed")
        finally:
            lock_file.close()
            lock.unlink()


def load_final_zones(source: Path, record) -> tuple[dict, str]:
    """Lecture réelle explicite des trois zones ; interdiction du test avant I/O."""
    source = guard_training_source(source)
    record(
        "source_read_started",
        zones=list(ZONE_NAMES),
        columns=TRAIN_COLUMNS,
        includes_labels=True,
        includes_features=True,
    )
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    data, _ = load_training_dataset(source)
    splits = split_chronologically(data)
    record(
        "source_read_completed",
        zones=list(ZONE_NAMES),
        rows={name: len(zone) for name, zone in splits.items()},
        source_sha256=digest,
    )
    return splits, digest


def calibration_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    """Même ECE (10 bins uniformes) que le benchmark, sur données hors fit."""
    from benchmark.run_benchmark import expected_calibration_error

    values = _proba(p)
    return {
        "brier": float(brier_score_loss(y, values)),
        "ece": expected_calibration_error(y, values, bins=10),
    }


def chronological_parts(
    frame: pd.DataFrame, weights: tuple[int, ...]
) -> list[pd.DataFrame]:
    """Découpe uniquement à partir des dates et des positions."""
    if (
        not frame[DATE_COLUMN].is_monotonic_increasing
        or not weights
        or any(weight <= 0 for weight in weights)
    ):
        raise ValueError("Zone non chronologique ou fractions invalides")
    cuts = [0]
    for weight in weights[:-1]:
        cuts.append(cuts[-1] + len(frame) * weight // sum(weights))
    cuts.append(len(frame))
    parts = [frame.iloc[a:b].copy() for a, b in pairwise(cuts)]
    if any(part.empty for part in parts):
        raise ValueError("Sous-zone chronologique vide")
    if any(
        left[DATE_COLUMN].iloc[-1] >= right[DATE_COLUMN].iloc[0]
        for left, right in pairwise(parts)
    ):
        raise ValueError("Dates communes à une frontière interne")
    return parts


def _proba(p: np.ndarray) -> np.ndarray:
    values = np.asarray(p, dtype=float)
    if (
        values.ndim != 1
        or not np.isfinite(values).all()
        or ((values < 0) | (values > 1)).any()
    ):
        raise ValueError("Probabilités finies dans [0,1] requises")
    return values


def _logit(p: np.ndarray) -> np.ndarray:
    return logit(np.clip(p, 1e-12, 1 - 1e-12)).reshape(-1, 1)


@dataclass
class Calibrator:
    method: str
    estimator: object

    def predict(self, p: np.ndarray) -> np.ndarray:
        values = _proba(p)
        output = (
            self.estimator.predict_proba(_logit(values))[:, 1]
            if self.method == "sigmoid"
            else self.estimator.predict(values)
        )
        return _proba(output)


def fit_calibrators(p: np.ndarray, y: np.ndarray) -> dict[str, Calibrator]:
    values, labels = _proba(p), np.asarray(y, dtype=int)
    if len(values) != len(labels) or set(np.unique(labels)) != {0, 1}:
        raise ValueError("Calibration : deux classes alignées requises")
    return {
        "sigmoid": Calibrator(
            "sigmoid", LogisticRegression(random_state=SEED).fit(_logit(values), labels)
        ),
        "isotonic": Calibrator(
            "isotonic", IsotonicRegression(out_of_bounds="clip").fit(values, labels)
        ),
    }


def choose_calibrator(
    calibrators: dict[str, Calibrator], p: np.ndarray, y: np.ndarray
) -> tuple[str, dict[str, float]]:
    scores = {
        name: float(brier_score_loss(y, model.predict(p)))
        for name, model in calibrators.items()
    }
    return min(scores, key=lambda name: (scores[name], name)), scores


def mondrian_quantiles(p: np.ndarray, y: np.ndarray, alpha: float) -> dict[int, float]:
    """Quantile fini par classe, rang ceil((n+1)(1-alpha)); jamais de repli."""
    values, labels = _proba(p), np.asarray(y, dtype=int)
    if (
        len(values) != len(labels)
        or set(np.unique(labels)) != {0, 1}
        or not 0 < alpha < 1
    ):
        raise ValueError("Mondrian : entrées invalides")
    result = {}
    for cls in (0, 1):
        scores = np.sort(values[labels == 0] if cls == 0 else 1 - values[labels == 1])
        rank = ceil((len(scores) + 1) * (1 - alpha))
        if rank > len(scores):
            raise ValueError(
                f"Quantile fini impossible : classe={cls}, alpha={alpha}, n={len(scores)}"
            )
        result[cls] = float(scores[rank - 1])
    return result


def prediction_membership(p: np.ndarray, quantiles: dict[int, float]) -> np.ndarray:
    values = _proba(p)
    if set(quantiles) != {0, 1} or not np.isfinite(list(quantiles.values())).all():
        raise ValueError("Deux quantiles finis requis")
    return np.column_stack((values <= quantiles[0], values >= 1 - quantiles[1]))


def review_rate(members: np.ndarray) -> float:
    return float(np.mean(members.sum(axis=1) != 1))


def coverage_summary(members: np.ndarray | None, y: np.ndarray) -> dict:
    """Compteurs observés ; None signifie classe absente ou alpha inapplicable."""
    labels = np.asarray(y)
    if labels.ndim != 1 or not np.isin(labels, [0, 1]).all():
        raise ValueError("Cibles binaires requises pour les couvertures")
    if members is not None:
        members = np.asarray(members)
        if members.shape != (len(labels), 2) or members.dtype != np.dtype(bool):
            raise ValueError("Ensembles booléens alignés requis")
    counts = {str(c): int((labels == c).sum()) for c in (0, 1)}
    covered = {
        str(c): int(members[labels == c, c].sum()) if members is not None else None
        for c in (0, 1)
    }
    return {
        "fraud_count": counts["1"],
        "class_counts": counts,
        "covered_counts": covered,
        "coverage_by_class": {
            key: covered[key] / count if count and covered[key] is not None else None
            for key, count in counts.items()
        },
    }


def exact_fraud_coverage_test(covered: int | None, total: int, alpha: float) -> dict:
    """Diagnostic bilatéral ; famille fixe des trois alpha, jamais une sélection."""
    if (
        not isinstance(total, Integral)
        or total < 0
        or not 0 < alpha < 1
        or (
            covered is not None
            and (not isinstance(covered, Integral) or not 0 <= covered <= total)
        )
    ):
        raise ValueError("Effectifs de couverture ou alpha invalides")
    result = {
        "covered": covered,
        "total": total,
        "nominal_coverage": 1 - alpha,
        "alternative": "two-sided",
        "comparisons": 3,
        "status": "unavailable",
        "p_raw": None,
        "p_bonferroni": None,
        "ci95_clopper_pearson": None,
    }
    if covered is None or total == 0:
        return result
    test = binomtest(covered, total, p=1 - alpha, alternative="two-sided")
    interval = test.proportion_ci(confidence_level=0.95, method="exact")
    result.update(
        status="available",
        p_raw=float(test.pvalue),
        p_bonferroni=min(1.0, 3 * float(test.pvalue)),
        ci95_clopper_pearson=[float(interval.low), float(interval.high)],
    )
    return result


def record_choice_metrics(report: dict, record) -> None:
    """Journalise les agrégats seulement, jamais les labels individuels."""
    for row in report["alpha_results"]:
        record(
            "choice_block_metrics",
            alpha=row["alpha"],
            status=row["status"],
            **row["choice"],
        )


def evaluate_sets(members: np.ndarray, y: np.ndarray) -> dict:
    labels = np.asarray(y, dtype=int)
    if len(labels) != len(members) or set(np.unique(labels)) != {0, 1}:
        raise ValueError("Evaluation : deux classes alignées requises")
    automatic = members.sum(axis=1) == 1
    error = (members[:, 1] != (labels == 1)) & automatic
    return {
        **coverage_summary(members, labels),
        "review_rate": review_rate(members),
        "automation_rate": float(automatic.mean()),
        "automatic_error_rate": float(error[automatic].mean())
        if automatic.any()
        else None,
    }


@dataclass
class CalibratedPriorClassifier:
    classifier: object
    beta: float
    calibrator: Calibrator

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        raw = self.classifier.predict_proba(X)[:, 1]
        fraud = self.calibrator.predict(correct_proba(raw, self.beta))
        return np.column_stack((1 - fraud, fraud))


def _zone_proba(
    zone: pd.DataFrame, preproc: object, classifier: object, beta: float
) -> tuple[np.ndarray, np.ndarray]:
    X, y = split_features_target(zone)
    return correct_proba(
        classifier.predict_proba(preproc.transform(X))[:, 1], beta
    ), y.to_numpy(dtype=int)


def _figures(
    output: Path,
    y: np.ndarray,
    raw: np.ndarray,
    calibrated: np.ndarray,
    rows: list[dict],
) -> None:
    from sklearn.calibration import calibration_curve

    fig, ax = plt.subplots()
    for name, p in (("avant", raw), ("après", calibrated)):
        observed, predicted = calibration_curve(y, p, n_bins=10, strategy="quantile")
        ax.plot(predicted, observed, marker="o", label=name)
    ax.plot([0, 1], [0, 1], "--", color="grey")
    ax.legend()
    ax.set(xlabel="Probabilité prédite", ylabel="Fréquence observée")
    fig.savefig(output / "reliability.png", dpi=160)
    plt.close(fig)
    valid = [row for row in rows if row["status"] == "eligible"]
    fig, ax = plt.subplots()
    ax.plot(
        [row["alpha"] for row in valid],
        [row["selection_review_rate"] for row in valid],
        marker="o",
    )
    ax.axhline(REVIEW_CAPACITY, color="red", linestyle="--")
    ax.set(xlabel="alpha", ylabel="Taux de revue (choix)")
    fig.savefig(output / "alpha_review.png", dpi=160)
    plt.close(fig)


def run_workflow(splits: dict[str, pd.DataFrame], params: dict, output: Path) -> dict:
    """Ajuste uniquement development, compare et évalue sur sous-zones disjointes."""
    names = ZONE_NAMES
    if set(splits) != set(names) or output.exists():
        raise ValueError("Trois zones exactes et un dossier de sortie neuf requis")
    dev, prob, conf = (splits[name] for name in names)
    if any(not zone[DATE_COLUMN].is_monotonic_increasing for zone in (dev, prob, conf)):
        raise ValueError("Zones non chronologiques")
    if any(
        zone.empty or not zone.is_fraud.isin([0, 1]).all() for zone in splits.values()
    ):
        raise ValueError("Zone vide ou cible invalide")
    if all("trans_num" in zone for zone in splits.values()):
        ids = pd.concat([zone.trans_num for zone in splits.values()])
        if ids.isna().any() or not ids.is_unique:
            raise ValueError("Transactions manquantes ou dupliquées")
    if not (
        dev[DATE_COLUMN].iloc[-1] < prob[DATE_COLUMN].iloc[0]
        and prob[DATE_COLUMN].iloc[-1] < conf[DATE_COLUMN].iloc[0]
    ):
        raise ValueError("Frontières chronologiques non disjointes")
    if len(set(dev.index) | set(prob.index) | set(conf.index)) != len(dev) + len(
        prob
    ) + len(conf):
        raise ValueError("Index des zones chevauchants")
    prob_fit, prob_choice = chronological_parts(prob, PROBABILITY_WEIGHTS)
    conf_fit, conf_choice, conf_eval = chronological_parts(conf, CONFORMAL_WEIGHTS)
    X_dev, y_dev = split_features_target(dev)
    preproc = build_preprocessing_pipeline()
    X_ready = preproc.fit_transform(X_dev, y_dev)
    labels = y_dev.to_numpy(dtype=int)
    fraud, legit = np.flatnonzero(labels == 1), np.flatnonzero(labels == 0)
    if not len(fraud) or not len(legit):
        raise ValueError("Development doit contenir deux classes")
    n_legit = min(len(legit), 10 * len(fraud))
    rng = np.random.default_rng(SEED)
    kept = rng.permutation(
        np.concatenate((fraud, rng.choice(legit, n_legit, replace=False)))
    )
    beta = n_legit / len(legit)
    classifier = build_model("xgb", params, SEED)
    classifier.fit(X_ready[kept], labels[kept])
    p_fit, y_fit = _zone_proba(prob_fit, preproc, classifier, beta)
    calibrators = fit_calibrators(p_fit, y_fit)
    p_choice, y_choice = _zone_proba(prob_choice, preproc, classifier, beta)
    method, brier = choose_calibrator(calibrators, p_choice, y_choice)
    calibrator = calibrators[method]
    p_q, y_q = _zone_proba(conf_fit, preproc, classifier, beta)
    p_alpha, y_alpha = _zone_proba(conf_choice, preproc, classifier, beta)
    p_q, p_alpha = (calibrator.predict(p) for p in (p_q, p_alpha))
    rows = []
    for alpha in ALPHAS:
        try:
            q = mondrian_quantiles(p_q, y_q, alpha)
        except ValueError as exc:
            rows.append({"alpha": alpha, "status": "inapplicable", "reason": str(exc)})
            continue
        rows.append(
            {
                "alpha": alpha,
                "status": "eligible",
                "quantiles": q,
                "selection_review_rate": review_rate(prediction_membership(p_alpha, q)),
            }
        )
    selected = next(
        (
            row
            for row in rows
            if row["status"] == "eligible"
            and row["selection_review_rate"] <= REVIEW_CAPACITY
        ),
        None,
    )
    # Score the evaluation block only after freezing the capacity decision.
    p_eval, y_eval = _zone_proba(conf_eval, preproc, classifier, beta)
    p_eval_before = p_eval.copy()
    p_eval = calibrator.predict(p_eval)
    for row in rows:
        # Reporting only: labels cannot influence the already frozen alpha.
        row["choice"] = coverage_summary(
            prediction_membership(p_alpha, row["quantiles"])
            if row["status"] == "eligible"
            else None,
            y_alpha,
        )
        if row["status"] == "eligible":
            row["evaluation"] = evaluate_sets(
                prediction_membership(p_eval, row["quantiles"]), y_eval
            )
        row["fraud_coverage_test"] = exact_fraud_coverage_test(
            row.get("evaluation", {}).get("covered_counts", {}).get("1"),
            int((y_eval == 1).sum()),
            row["alpha"],
        )
    output.mkdir(parents=True, exist_ok=False)
    _figures(output, y_choice, p_choice, calibrator.predict(p_choice), rows)
    report = {
        "candidate": "xgb",
        "model_status": "provisional",
        "seed": SEED,
        "beta": beta,
        "train_counts": {
            "fraud": len(fraud),
            "legit_total": len(legit),
            "legit_kept": n_legit,
        },
        "xgb_params": params,
        "conformal_fit_counts": {str(c): int((y_q == c).sum()) for c in (0, 1)},
        "calibrator": method,
        "brier_before_calibration": float(brier_score_loss(y_choice, p_choice)),
        "brier_comparison": brier,
        "calibration_metrics": {
            "definition": "ECE: 10 bins uniformes sur [0,1], pondérés par effectif",
            "probability_choice_before": calibration_metrics(y_choice, p_choice),
            "probability_choice_methods": {
                name: calibration_metrics(y_choice, model.predict(p_choice))
                for name, model in calibrators.items()
            },
            "conformal_evaluation_before": calibration_metrics(y_eval, p_eval_before),
            "conformal_evaluation_after": calibration_metrics(y_eval, p_eval),
        },
        "alpha_results": rows,
        "selected_alpha": selected["alpha"] if selected else None,
        "capacity_met": selected is not None,
        "zone_rows": {name: len(splits[name]) for name in names},
        "internal_rows": {
            "prob_fit": len(prob_fit),
            "prob_choice": len(prob_choice),
            "conf_fit": len(conf_fit),
            "conf_choice": len(conf_choice),
            "conf_eval": len(conf_eval),
        },
    }
    (output / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Calibration et conforme P2",
        "",
        "XGBoost reste provisoire.",
        f"Beta mesuré : {beta:.10f}.",
        f"Brier hors ajustement : {brier} ; méthode : {method}.",
        f"Brier/ECE avant/après (évaluation finale interne) : {report['calibration_metrics']['conformal_evaluation_before']} / {report['calibration_metrics']['conformal_evaluation_after']}.",
        "ECE : 10 bins uniformes, pondérés par effectif (convention benchmark).",
        f"Effectifs Mondrian par classe : {report['conformal_fit_counts']}.",
        "",
        "| alpha | statut | revue choix | couverture 0 | couverture 1 | revue évaluation | automatisation | erreur automatique |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        metrics = row.get("evaluation", {})
        coverage = metrics.get("coverage_by_class", {})
        lines.append(
            f"| {row['alpha']} | {row['status']} | {row.get('selection_review_rate', '—')} | {coverage.get('0', '—')} | {coverage.get('1', '—')} | {metrics.get('review_rate', '—')} | {metrics.get('automation_rate', '—')} | {metrics.get('automatic_error_rate', '—')} |"
        )
    lines.extend(
        [
            "",
            "Couvertures du bloc de choix : descriptives, calculées après la décision d'alpha.",
            "None signifie classe absente ou alpha inapplicable ; aucun taux n'est imputé.",
            "| alpha | statut | fraudes choix | légitimes choix | couverture choix 0 | couverture choix 1 |",
            "|---:|---|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        choice = row["choice"]
        lines.append(
            f"| {row['alpha']} | {row['status']} | {choice['fraud_count']} | {choice['class_counts']['0']} | {choice['coverage_by_class']['0']} | {choice['coverage_by_class']['1']} |"
        )
    lines.extend(
        [
            "",
            "Tests binomiaux exacts bilatéraux : couverture fraude du bloc d'évaluation contre 1-alpha.",
            "Bonferroni : p ajusté = min(1, 3 × p brut), famille fixe des trois alpha, même si un alpha est inapplicable.",
            "Les intervalles Clopper-Pearson à 95 % sont marginaux, non ajustés ; les intervalles et tests supposent des transactions indépendantes et une probabilité de couverture commune.",
            "La dépendance entre cartes/transactions et l'incertitude de réajustement ne sont pas prises en compte.",
            "Diagnostics descriptifs : ils ne modifient ni la sélection d'alpha ni le statut provisoire du modèle.",
            "| alpha | statut test | fraudes couvertes | fraudes évaluées | cible | IC 95 % marginal | p exact brut | p Bonferroni (3) |",
            "|---:|---|---:|---:|---:|---|---:|---:|",
        ]
    )
    for row in rows:
        test = row["fraud_coverage_test"]
        lines.append(
            f"| {row['alpha']} | {test['status']} | {test['covered']} | {test['total']} | {test['nominal_coverage']} | {test['ci95_clopper_pearson']} | {test['p_raw']} | {test['p_bonferroni']} |"
        )
    lines.extend(
        [
            "",
            f"Alpha choisi : {selected['alpha'] if selected else 'aucun : capacité non satisfaite ou quantile inapplicable'}.",
            "Evaluation sur un quart distinct du fit et du choix d'alpha.",
            "![Fiabilité](reliability.png)",
            "![Compromis](alpha_review.png)",
        ]
    )
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# Candidat P2 provisoire\n\n[Rapport détaillé](report.md)\n\n"
        "![Compromis alpha/revue, capacité 2 %](alpha_review.png)\n",
        encoding="utf-8",
    )
    if selected is not None:
        from ml.src.model.fraud_detector import FraudDetectorModel

        artifact = FraudDetectorModel(
            classifier=CalibratedPriorClassifier(classifier, beta, calibrator),
            preprocessor=preproc,
            feature_names=list(preproc.get_feature_names_out()),
            threshold_legit=selected["quantiles"][0],
            threshold_fraud=selected["quantiles"][1],
            alpha=selected["alpha"],
        )
        joblib.dump(artifact, output / "candidate_model.joblib")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--best-params", type=Path, required=True)
    parser.add_argument(
        "--local-report-only",
        action="store_true",
        help="Produire les artefacts locaux sans journalisation MLflow",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--journal",
        type=Path,
        required=True,
        help="Journal JSONL hors dépôt, même fichier à chaque lancement",
    )
    parser.add_argument(
        "--protocol-change-reason",
        default="",
        help="Décision explicite motivant un changement depuis le dernier lancement",
    )
    args = parser.parse_args(argv)
    guard_training_source(args.source)
    if args.output_dir.exists():
        parser.error("Le dossier de sortie doit être neuf")
    content = args.best_params.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != "f0ced06a7e2f863406aa55f891b10f337f1163cf6d6c0f08e584c18a3f6bfd41":
        raise ValueError("Empreinte des paramètres différente du handoff #22")
    params = json.loads(content)["models"]["xgb"]["params"]
    with launch_audit(
        args.journal,
        args.source,
        protocol_snapshot(params, digest),
        args.protocol_change_reason,
    ) as record:
        if args.local_report_only:
            splits, _ = load_final_zones(args.source, record)
            result = run_workflow(splits, params, args.output_dir)
            record_choice_metrics(result, record)
        else:
            import mlflow

            from ml.tracking_smoke import _git_commit, get_tracking_uri

            mlflow.set_tracking_uri(get_tracking_uri())
            mlflow.set_experiment("p2_final_calibration")
            with mlflow.start_run(
                tags={
                    "git_commit": _git_commit(),
                    "model_status": "provisional",
                    "best_params_sha256": digest,
                }
            ) as run:
                record("mlflow_run", run_id=run.info.run_id)
                splits, source_digest = load_final_zones(args.source, record)
                mlflow.set_tag("data_sha256", source_digest)
                result = run_workflow(splits, params, args.output_dir)
                record_choice_metrics(result, record)
                mlflow.log_params(
                    {**params, "seed": SEED, "calibrator": result["calibrator"]}
                )
                mlflow.log_metric("beta", result["beta"])
                mlflow.log_metrics(
                    {"brier_" + k: v for k, v in result["brier_comparison"].items()}
                )
                mlflow.log_metrics(
                    {
                        "evaluation_" + k: v
                        for k, v in result["calibration_metrics"][
                            "conformal_evaluation_after"
                        ].items()
                    }
                )
                for row in result["alpha_results"]:
                    if row["status"] == "eligible":
                        metrics = row["evaluation"]
                        mlflow.log_metrics(
                            {
                                f"alpha_{row['alpha']}_{key}": value
                                for key, value in metrics.items()
                                if key
                                in {
                                    "review_rate",
                                    "automation_rate",
                                    "automatic_error_rate",
                                }
                                and value is not None
                            }
                        )
                        mlflow.log_metrics(
                            {
                                f"alpha_{row['alpha']}_coverage_{cls}": value
                                for cls, value in metrics["coverage_by_class"].items()
                            }
                        )
                mlflow.set_tag("selected_alpha", str(result["selected_alpha"]))
                record(
                    "workflow_completed",
                    selected_alpha=result["selected_alpha"],
                    model_status="provisional",
                    output_dir=str(args.output_dir.resolve()),
                )
                mlflow.log_artifacts(str(args.output_dir))
                mlflow.log_artifact(str(args.journal), artifact_path="audit")
    print(
        json.dumps(
            {
                "candidate": result["candidate"],
                "selected_alpha": result["selected_alpha"],
                "capacity_met": result["capacity_met"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    from ml.src.final.train_final import main as cli

    raise SystemExit(cli())
