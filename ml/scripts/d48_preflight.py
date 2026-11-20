"""Précontrôle en lecture seule de l'unique exécution officielle D48.

Le script rejoue, sans rien écrire, la séquence de contrôles que
``evaluate_final_candidate.py`` exécute avant d'ouvrir la source finale :
empreintes, référence D44, mesure précédente, protocole, autorisation, journal
et frame de latence. Il ne réserve rien dans le journal, ne crée pas le dossier
de sortie, ne lit pas le contenu du test final et n'ouvre aucun run MLflow.

Un précontrôle réussi ne remplace pas l'exécution : il certifie seulement que
les préconditions sont satisfaites et que l'invocation unique peut être lancée.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np

from ml.scripts.evaluate_final_candidate import (
    FINAL_DECISION_ID,
    ROOT,
    load_latency_sample,
    resolve_journal,
    sha256,
    validate_candidate,
)
from ml.scripts.final_history import load_previous_evaluation
from ml.scripts.final_journal import check_authorization, read_journal
from ml.src.evaluation.final_artifacts import (
    APPROVED_D48_MODEL_SHA256,
    APPROVED_D48_SOURCE_SHA256,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _outside_repository(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    _require(
        not resolved.is_relative_to(ROOT.resolve()),
        f"{label} doit rester hors du dépôt",
    )
    return resolved


def _inspect_output(output: Path, source: Path) -> None:
    """Contrôle du montage et de l'espace sans créer de fichier sonde."""

    parent = output.resolve().parent
    _require(parent.is_dir(), "Parent de sortie absent ou montage indisponible")
    required = max(1024 * 1024, 3 * source.stat().st_size)
    free = shutil.disk_usage(parent).free
    _require(
        free >= required,
        "Espace disque insuffisant pour la sauvegarde avant analyse",
    )


def preflight(args: argparse.Namespace) -> list[str]:
    """Renvoie la liste des contrôles réussis ; lève sinon."""

    checks: list[str] = []

    _require(
        args.decision_id == FINAL_DECISION_ID,
        f"Décision {args.decision_id} refusée : {FINAL_DECISION_ID} requise",
    )

    journal = resolve_journal(args.journal)
    _require(journal is not None, "Journal D48 obligatoire (--journal)")
    _require(journal.parent.is_dir(), "Parent du journal absent : montage indisponible")
    _require(journal.is_file(), "Journal central absent ; refus de continuer")
    _raw, entries = read_journal(journal)
    checks.append(f"journal lisible : {len(entries)} entrées, sha256={sha256(journal)}")

    source = args.source.expanduser().resolve()
    _require(
        source.name.lower() == "fraudtest.csv",
        "Nom de source finale non autorisé (fraudTest.csv attendu)",
    )
    source_sha = sha256(source)
    _require(
        source_sha == str(args.expected_source_sha256).lower(),
        "SHA-256 de la source différent de la source approuvée pour D48",
    )
    checks.append(f"source finale : {source_sha}")

    model_sha = sha256(args.model)
    _require(
        model_sha == str(args.expected_model_sha256).lower(),
        "SHA-256 du modèle différent du candidat D44 figé",
    )
    model = joblib.load(args.model)
    checks.append(f"candidat figé : {model_sha}")

    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    validate_candidate(model, reference)
    checks.append(f"référence D44 : {sha256(args.reference)}")

    previous, _payloads = load_previous_evaluation(
        args.previous_evaluation,
        model_sha,
        source_sha,
        model.alpha,
    )
    checks.append(
        "mesure du 10 novembre : "
        f"{int(previous['overall']['n_transactions'])} transactions, "
        f"{int(previous['overall']['fraud_count'])} fraudes"
    )

    protocol_sha = sha256(args.protocol_file)
    checks.append(f"protocole : {protocol_sha}")

    authorization_path = _outside_repository(args.authorization, "L'autorisation")
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    check_authorization(
        journal,
        authorization,
        source_sha256=source_sha,
        model_sha256=model_sha,
        decision_id=args.decision_id,
        protocol_sha256=protocol_sha,
        reason=args.reason,
    )
    checks.append("autorisation : approuvée et liée au journal courant")

    latency = load_latency_sample(args.latency_source)
    transformed = model.preprocessor.transform(latency)
    _require(
        bool(np.isfinite(np.asarray(transformed)).all()),
        "Source de latence invalide : valeurs non finies",
    )
    checks.append(f"frame de latence : {len(latency)} lignes development")

    output = _outside_repository(args.output_dir, "Le dossier de sortie")
    _require(not output.exists(), f"Dossier de sortie déjà présent : {output}")
    _inspect_output(output, source)
    checks.append(f"sortie : {output} (parent accessible, espace suffisant)")

    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--previous-evaluation", type=Path, required=True)
    parser.add_argument("--latency-source", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--protocol-file", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--decision-id", default=FINAL_DECISION_ID)
    parser.add_argument("--reason", default="précontrôle D48 en lecture seule")
    parser.add_argument(
        "--expected-model-sha256",
        default=APPROVED_D48_MODEL_SHA256,
        help="Ne pas surcharger pour la mesure officielle D48.",
    )
    parser.add_argument(
        "--expected-source-sha256",
        default=APPROVED_D48_SOURCE_SHA256,
        help="Ne pas surcharger pour la mesure officielle D48.",
    )
    args = parser.parse_args(argv)

    try:
        checks = preflight(args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"[ECHEC] {exc}", file=sys.stderr)
        return 2
    for check in checks:
        print(f"[OK] {check}")
    print("[PRET] préconditions satisfaites ; l'exécution unique reste à lancer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
