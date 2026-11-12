"""Conservation des agrégats historiques, sans relire la source évaluée."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

HISTORY_FILES = ("final_metrics.json", "final_report.md")
HISTORY_DIR = "previous_evaluation"
REMEASUREMENT_NOTICE = "Seconde mesure post hoc, non indépendante"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate_finite_tree(value, location: str = "historique") -> None:
    """Vérifie aussi les métriques supplémentaires et les agrégats imbriqués."""
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_finite_tree(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_finite_tree(item, f"{location}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"Valeur historique non finie : {location}")


def _validate_count(value, name: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "strictement positif" if positive else "positif ou nul"
        raise ValueError(f"Effectif historique {name} : entier {qualifier} requis")
    return value


def _validate_counts(overall: dict) -> None:
    total = _validate_count(overall["n_transactions"], "n_transactions", positive=True)
    frauds = _validate_count(overall["fraud_count"], "fraud_count")
    if frauds > total:
        raise ValueError("Effectif historique fraud_count supérieur à n_transactions")
    classes = overall.get("class_counts")
    covered = overall.get("covered_counts")
    if "class_counts" in overall:
        if not isinstance(classes, dict) or set(classes) != {"0", "1"}:
            raise ValueError("Effectifs historiques class_counts invalides")
        for label, count in classes.items():
            _validate_count(count, f"class_counts.{label}")
        if sum(classes.values()) != total or classes["1"] != frauds:
            raise ValueError("Effectifs historiques class_counts incohérents")
    if "covered_counts" in overall:
        if not isinstance(covered, dict) or set(covered) != {"0", "1"}:
            raise ValueError("Effectifs historiques covered_counts invalides")
        expected_classes = {"0": total - frauds, "1": frauds}
        for label, count in covered.items():
            _validate_count(count, f"covered_counts.{label}")
            if count > expected_classes[label]:
                raise ValueError(
                    f"Effectif historique covered_counts.{label} supérieur à sa classe"
                )


def load_previous_evaluation(
    directory: Path, model_sha256: str, source_sha256: str | None, alpha: float
) -> tuple[dict, dict[str, bytes]]:
    """Vérifie les agrégats et conserve les octets exacts pour une copie fidèle."""
    try:
        payloads = {name: (directory / name).read_bytes() for name in HISTORY_FILES}
        previous = json.loads(payloads["final_metrics.json"])
        payloads["final_report.md"].decode("utf-8")
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError(
            "Évaluation précédente absente, illisible ou invalide"
        ) from exc
    if not isinstance(previous, dict) or previous.get("scope") != "final_test":
        raise ValueError(
            "La mesure précédente doit être une évaluation finale sauvegardée"
        )
    _validate_finite_tree(previous)
    if previous.get("model_sha256") != model_sha256:
        raise ValueError("Empreinte modèle différente dans l’évaluation précédente")
    if source_sha256 is not None and previous.get("source_sha256") != source_sha256:
        raise ValueError("Empreinte source différente dans l’évaluation précédente")
    try:
        alpha_matches = math.isclose(
            float(previous["alpha"]), alpha, rel_tol=0, abs_tol=1e-12
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Alpha précédent absent ou invalide") from exc
    if not alpha_matches:
        raise ValueError("Alpha différent dans l’évaluation précédente")
    overall = previous.get("overall")
    required = (
        "pr_auc",
        "coverage_by_class",
        "review_rate",
        "automatic_error_rate",
        "n_transactions",
        "fraud_count",
    )
    if not isinstance(overall, dict) or any(key not in overall for key in required):
        raise ValueError("Métriques précédentes incomplètes")
    _validate_counts(overall)
    if not isinstance(overall["coverage_by_class"], dict) or not {"0", "1"}.issubset(
        overall["coverage_by_class"]
    ):
        raise ValueError("Couvertures précédentes incomplètes")
    for value in (
        overall["pr_auc"],
        overall["review_rate"],
        overall["automatic_error_rate"],
        *overall["coverage_by_class"].values(),
    ):
        if value is not None and (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            raise ValueError("Métrique précédente non finie ou hors bornes")
    metadata = {
        "date": "2026-11-10",
        "date_basis": "Historique du protocole D47 ; date non déduite du fichier de métriques",
        "model_sha256": previous["model_sha256"],
        "source_sha256": previous.get("source_sha256"),
        "alpha": previous["alpha"],
        "overall": overall,
        "artifacts": {
            f"{HISTORY_DIR}/{name}": _sha(raw) for name, raw in payloads.items()
        },
        "role": "historical_record_only_no_selection_or_tuning",
    }
    return metadata, payloads


def history_report_lines(history: dict, current: dict) -> list[str]:
    previous = history["overall"]
    rows = [("PR-AUC", previous["pr_auc"], current["pr_auc"])]
    rows += [
        (
            f"Couverture classe {c}",
            previous["coverage_by_class"][c],
            current["coverage_by_class"][c],
        )
        for c in ("0", "1")
    ]
    rows += [
        (label, previous[key], current[key])
        for label, key in (
            ("Taux de revue", "review_rate"),
            ("Erreur automatique", "automatic_error_rate"),
            ("Transactions", "n_transactions"),
            ("Fraudes", "fraud_count"),
        )
    ]
    return [
        "## " + REMEASUREMENT_NOTICE,
        "",
        "Les résultats du 10 novembre 2026 sont conservés ci-dessous. La seconde mesure réutilise le même jeu et le même candidat figé ; elle n’est pas une confirmation indépendante.",
        "Cette présentation ne sert à aucune sélection, réglage ou promotion. Les définitions d’équité corrigées ne rendent pas l’ancien audit ponctuel comparable aux décisions conformes.",
        "",
        "| Mesure | Première mesure — 10 novembre 2026 | Seconde mesure |",
        "|---|---:|---:|",
        *[
            f"| {label} | {old if old is not None else 'indéfini'} | {new if new is not None else 'indéfini'} |"
            for label, old, new in rows
        ],
        "",
        "Les anciens IC ne sont pas reconstruits ni inventés. Les valeurs sont reprises des agrégats sauvegardés, sans nouvelle inférence.",
        "",
        f"[Rapport original]({HISTORY_DIR}/final_report.md) ; [métriques originales]({HISTORY_DIR}/final_metrics.json).",
        *[
            f"- SHA-256 `{name}` : `{digest}`"
            for name, digest in history["artifacts"].items()
        ],
        "",
    ]


def verify_previous_evaluation(output: Path, result: dict, manifest: dict) -> None:
    history = result.get("previous_evaluation")
    if history is None:
        if result.get("decision_id") == "D47":
            raise ValueError("D47 : historique de première mesure absent")
        return
    expected_names = {f"{HISTORY_DIR}/{name}" for name in HISTORY_FILES}
    if set(history.get("artifacts", {})) != expected_names:
        raise ValueError("Archives précédentes absentes du résultat")
    archived, _ = load_previous_evaluation(
        output / HISTORY_DIR,
        result["model_sha256"],
        result["source_sha256"],
        result["alpha"],
    )
    if archived != history:
        raise ValueError("Historique précédent incohérent avec les archives")
    for name, digest in history["artifacts"].items():
        if manifest["artifacts"].get(name) != digest:
            raise ValueError(f"Archive précédente absente du manifeste : {name}")
    measurement = result.get("measurement", {})
    if measurement.get("number") != 2 or measurement.get("independent") is not False:
        raise ValueError("Statut de seconde mesure incohérent")
