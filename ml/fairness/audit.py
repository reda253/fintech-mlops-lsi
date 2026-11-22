"""Descriptive fairness analysis from saved predictions; no final-test reader."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ml.scripts.evaluate_final_candidate import AGE_BINS, AGE_LABELS, atomic_write
from ml.scripts.final_journal import outside_repository, read_journal
from ml.scripts.final_metrics import decision_metrics
from ml.src.evaluation.final_artifacts import (
    APPROVED_D48_MODEL_SHA256,
    APPROVED_D48_SOURCE_SHA256,
    load_verified_final_evaluation,
)

METRICS = (
    "auto_block_fraud_rate",
    "fraud_interception_rate",
    "auto_block_legitimate_rate",
    "review_rate",
)
DECISIONS = ("APPROUVER", "BLOQUER", "REVUE HUMAINE")
ROOT = Path(__file__).resolve().parents[2]


def read_evaluation_journal(journal: Path) -> list[dict]:
    """Validate saved-run provenance without reusing a consumed authorization."""
    outside_repository(journal, "Le journal")
    _, entries = read_journal(journal)
    if any(entry.get("decision_id") == "D47" for entry in entries):
        raise ValueError(
            "Entrée D47 présente dans le journal : examen manuel requis avant D48"
        )
    return entries


def age_bands(ages: pd.Series) -> pd.Series:
    values = pd.to_numeric(ages, errors="raise")
    if (
        not np.isfinite(values).all()
        or ((values < 0) | (values > 120)).any()
        or (values % 1 != 0).any()
    ):
        raise ValueError("Âges révolus entiers dans [0,120] requis")
    return pd.cut(values, bins=AGE_BINS, labels=AGE_LABELS, include_lowest=True).astype(
        str
    )


def decision(prediction_set: list[int]) -> str:
    if prediction_set == [0]:
        return DECISIONS[0]
    if prediction_set == [1]:
        return DECISIONS[1]
    if prediction_set in ([], [0, 1]):
        return DECISIONS[2]
    raise ValueError("Ensemble invalide")


def normalize(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.rename(columns={"label": "is_fraud", "age_group": "age_band"}).copy()
    required = {"gender", "age_band", "is_fraud", "fraud_probability"}
    if required - set(frame):
        raise ValueError(f"Colonnes manquantes : {sorted(required - set(frame))}")
    if frame.empty or frame[list(required)].isna().any().any():
        raise ValueError("Prédictions vides ou manquantes")
    if (
        not frame.gender.isin(["F", "M"]).all()
        or not frame.age_band.isin(AGE_LABELS).all()
    ):
        raise ValueError("Genre ou tranche d'âge invalide")
    if not frame.is_fraud.isin([0, 1]).all():
        raise ValueError("Étiquettes binaires requises")
    p = pd.to_numeric(frame.fraud_probability, errors="raise")
    if not np.isfinite(p).all() or not p.between(0, 1).all():
        raise ValueError("Probabilités hors [0,1]")
    if {"include_0", "include_1"}.issubset(frame):
        if not frame[["include_0", "include_1"]].isin([0, 1]).all().all():
            raise ValueError("Appartenances binaires requises")
        sets = [
            [c for c in (0, 1) if row[f"include_{c}"]]
            for row in frame.to_dict("records")
        ]
    elif "prediction_set" in frame:
        sets = [
            json.loads(s) if isinstance(s, str) else list(s)
            for s in frame.prediction_set
        ]
    else:
        raise ValueError("Ensembles ou indicateurs d'appartenance requis")
    decisions = [decision(s) for s in sets]
    if "decision" in frame and frame.decision.tolist() != decisions:
        raise ValueError("Décisions incohérentes avec les ensembles")
    if "age" in frame and age_bands(frame.age).tolist() != frame.age_band.tolist():
        raise ValueError("Âge et tranche incohérents")
    frame["decision"] = decisions
    frame["include_0"] = [0 in s for s in sets]
    frame["include_1"] = [1 in s for s in sets]
    return frame


def interval(samples: np.ndarray, value: float | None, n_boot: int) -> dict:
    finite = samples[np.isfinite(samples)]
    return {
        "value": value,
        "undefined": value is None,
        "ci95": np.quantile(finite, [0.025, 0.975]).tolist() if len(finite) else None,
        "valid_resamples": len(finite),
        "total_resamples": n_boot,
    }


def analyze(
    frame: pd.DataFrame,
    *,
    alpha: float,
    age_reference: str | None = None,
    n_boot: int = 10_000,
    seed: int = 42,
) -> dict:
    """Exact iid bootstrap for categorical sufficient statistics, shared draws.

    Joint cells (gender, age band, label, decision) suffice for the four rates.
    Multinomial(N, observed cell frequencies) is the exact count distribution
    of resampling N transactions with replacement, with bounded memory.
    """
    if (
        isinstance(alpha, bool)
        or not isinstance(alpha, (int, float))
        or not np.isfinite(alpha)
        or not 0 < alpha < 1
    ):
        raise ValueError("Alpha doit être fini et strictement compris entre 0 et 1")
    if n_boot <= 0:
        raise ValueError("Nombre de tirages strictement positif requis")
    frame = normalize(frame)
    if age_reference is not None and age_reference not in AGE_LABELS:
        raise ValueError("Référence d'âge inconnue")
    cells = (
        frame.groupby(["gender", "age_band", "is_fraud", "decision"], observed=True)
        .size()
        .reset_index(name="n")
    )
    n = len(frame)
    counts = cells.n.to_numpy()
    draws = np.random.default_rng(seed).multinomial(n, counts / n, size=n_boot)
    y = cells.is_fraud.to_numpy()
    blocked = cells.decision.eq("BLOQUER").to_numpy()
    review = cells.decision.eq("REVUE HUMAINE").to_numpy()
    samples = {}
    groups = []
    definitions = [("overall", "all", np.ones(len(cells), dtype=bool))]
    for attr, names in (("gender", ["F", "M"]), ("age_band", AGE_LABELS)):
        definitions += [(attr, name, cells[attr].eq(name).to_numpy()) for name in names]
    members = np.column_stack([~blocked & ~review, blocked])
    # Review membership can be either [] or [0,1]; the rates only require review.
    for attr, name, mask in definitions:
        pos, neg = mask & (y == 1), mask & (y == 0)
        numerators = (
            pos & blocked,
            pos & (blocked | review),
            neg & blocked,
            mask & review,
        )
        denominators = (pos, pos, neg, mask)
        values = decision_metrics(y, members, counts * mask)
        row = {
            "attribute": attr,
            "group": name,
            "N": int(counts[mask].sum()),
            "N_pos": int(counts[pos].sum()),
            "N_neg": int(counts[neg].sum()),
            "metrics": {},
        }
        for metric, num, den in zip(METRICS, numerators, denominators, strict=True):
            denominator = draws[:, den].sum(axis=1)
            distribution = np.divide(
                draws[:, num].sum(axis=1),
                denominator,
                out=np.full(n_boot, np.nan),
                where=denominator != 0,
            )
            samples[(attr, name, metric)] = distribution
            row["metrics"][metric] = interval(distribution, values[metric], n_boot)
        groups.append(row)
    gaps = []
    index = {(r["attribute"], r["group"]): r for r in groups}
    for attr, names in (("gender", ["F", "M"]), ("age_band", AGE_LABELS)):
        pairs = (
            [(a, age_reference) for a in names if a != age_reference]
            if attr == "age_band" and age_reference
            else list(itertools.combinations(names, 2))
        )
        for a, b in pairs:
            for metric in METRICS:
                av, bv = (
                    index[(attr, a)]["metrics"][metric]["value"],
                    index[(attr, b)]["metrics"][metric]["value"],
                )
                value = None if av is None or bv is None else abs(av - bv)
                gaps.append(
                    {
                        "attribute": attr,
                        "group_a": a,
                        "group_b": b,
                        "metric": metric,
                        **interval(
                            np.abs(
                                samples[(attr, a, metric)] - samples[(attr, b, metric)]
                            ),
                            value,
                            n_boot,
                        ),
                    }
                )
    return {
        "model_status": "provisional",
        "alpha": float(alpha),
        "measurement": "seconde mesure post hoc, non indépendante",
        "bootstrap": {
            "n_boot": n_boot,
            "seed": seed,
            "method": "iid multinomial on joint sufficient statistics",
            "ci": 0.95,
        },
        "age_reference": age_reference,
        "groups": groups,
        "absolute_gaps": gaps,
    }


def render_metric(metric: dict) -> str:
    if metric["value"] is None:
        return "N/A (undefined)"
    ci = metric["ci95"]
    return (
        f"{100 * metric['value']:.3f}% [{100 * ci[0]:.3f}; {100 * ci[1]:.3f}]"
        if ci
        else f"{100 * metric['value']:.3f}% ; IC N/A"
    )


def write_outputs(result: dict, output: Path) -> None:
    if output.resolve().is_relative_to(ROOT) or output.exists():
        raise ValueError("Un dossier neuf hors dépôt est requis")
    output.mkdir(parents=True)
    atomic_write(
        output / "fairness_metrics.json",
        (
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode(),
    )
    lines = [
        "# Audit descriptif d'équité",
        "",
        "D48 : seconde mesure post hoc, non indépendante. Candidat provisoire, aucune promotion.",
        "Les IC supposent des transactions indépendantes ; les transactions répétées par carte (cc_num) peuvent être corrélées.",
        "",
        "| Attribut | Groupe | N | Fraudes | Légitimes | Fraudes bloquées | Fraudes interceptées | Légitimes bloqués | Revue |",
        "|---|---|---:|---:|---:|---|---|---|---|",
    ]
    for row in result["groups"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["attribute"],
                    row["group"],
                    str(row["N"]),
                    str(row["N_pos"]),
                    str(row["N_neg"]),
                    *[render_metric(row["metrics"][m]) for m in METRICS],
                ]
            )
            + " |"
        )
    lines += [
        "",
        "## Écarts absolus (points de pourcentage)",
        "| Attribut | Groupes | Mesure | Écart et IC95 % |",
        "|---|---|---|---|",
    ]
    for gap in result["absolute_gaps"]:
        lines.append(
            f"| {gap['attribute']} | {gap['group_a']} / {gap['group_b']} | {gap['metric']} | {render_metric(gap)} |"
        )
    lines += [
        "",
        "## Analyse critique à compléter",
        "- Groupes peu représentés : à discuter avec leurs effectifs.",
        "- Largeur des intervalles et réplications valides : voir JSON ; comparaisons descriptives multiples.",
        "- Aucun verdict binaire d'équité, aucun réglage du modèle après observation.",
    ]
    atomic_write(output / "fairness_report.md", ("\n".join(lines) + "\n").encode())
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures = output / "figures"
    figures.mkdir()
    for attr in ("gender", "age_band"):
        rows = [r for r in result["groups"] if r["attribute"] == attr]
        for metric in METRICS:
            fig, ax = plt.subplots(figsize=(8, 4))
            for i, row in enumerate(rows):
                value = row["metrics"][metric]
                if value["value"] is None:
                    ax.text(0, i, "N/A (undefined)")
                else:
                    ax.barh(i, 100 * value["value"])
                    if value["ci95"]:
                        lo, hi = value["ci95"]
                        ax.hlines(i, 100 * lo, 100 * hi, color="black")
            ax.set_yticks(range(len(rows)), [r["group"] for r in rows])
            ax.set_xlim(0, 105)
            ax.set_xlabel("Taux (%) et IC95 %")
            ax.set_title(metric)
            fig.tight_layout()
            fig.savefig(figures / f"{attr}_{metric}.png")
            plt.close(fig)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-predictions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--age-reference", choices=AGE_LABELS)
    parser.add_argument(
        "--journal",
        type=Path,
        required=True,
        help="Journal central hors dépôt, lu sans réservation",
    )
    parser.add_argument("--log-mlflow", action="store_true")
    parser.add_argument("--tracking-uri")
    parser.add_argument(
        "--code-revision",
        required=True,
        help="Révision courante fournie explicitement ; aucune commande Git",
    )
    parser.add_argument(
        "--model-metadata",
        type=Path,
        help="JSON de provenance du candidat : model_sha256, model_uri, model_version",
    )
    args = parser.parse_args(argv)
    source = args.from_predictions
    if source.name != "predictions.csv":
        parser.error("Seul predictions.csv produit par l'évaluateur est accepté")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", args.code_revision):
        parser.error("--code-revision doit contenir une empreinte Git complète")
    # Integrity and provenance only: a consumed authorization is not reused.
    directory = source.parent
    entries = read_evaluation_journal(args.journal)
    verified = load_verified_final_evaluation(
        directory,
        expected_model_sha256=APPROVED_D48_MODEL_SHA256,
        expected_source_sha256=APPROVED_D48_SOURCE_SHA256,
        expected_alpha=0.02,
    )
    saved = json.loads((directory / "final_metrics.json").read_text(encoding="utf-8"))
    if not any(
        e.get("status") == "completed"
        and e.get("decision_id") == "D48"
        and all(
            e.get(k) == verified.provenance[k]
            for k in ("source_sha256", "model_sha256", "protocol_sha256")
        )
        for e in entries
    ):
        raise ValueError("Achèvement D48 cohérent absent du journal")
    metadata = (
        json.loads(args.model_metadata.read_text(encoding="utf-8"))
        if args.model_metadata
        else {}
    )
    if metadata and metadata.get("model_sha256") != saved["model_sha256"]:
        raise ValueError("Métadonnées du modèle incohérentes")
    publication = directory / "mlflow_status.json"
    state = (
        json.loads(publication.read_text(encoding="utf-8"))
        if publication.exists()
        else {}
    )
    if (
        not metadata.get("model_uri")
        or not metadata.get("model_version")
        or not state.get("run_id")
        or state.get("status") != "published"
    ):
        raise ValueError(
            "Version/URI du modèle et publication MLflow vérifiée requises"
        )
    frame = pd.read_csv(source)
    if list(frame.columns) != [
        "label",
        "fraud_probability",
        "include_0",
        "include_1",
        "gender",
        "age_group",
    ]:
        raise ValueError(
            "Schéma minimal des prédictions différent de celui de l’évaluateur"
        )
    if hashlib.sha256(source.read_bytes()).hexdigest() != saved["predictions_sha256"]:
        raise ValueError("Prédictions modifiées pendant la lecture")
    result = analyze(
        frame, alpha=verified.metrics["alpha"], age_reference=args.age_reference
    )
    result["scope"] = "saved_d48_predictions"
    result["provenance"] = {
        "source_sha256": saved.get("source_sha256"),
        "model_sha256": saved["model_sha256"],
        "protocol_sha256": saved.get("protocol_sha256"),
        "evaluation_run_id": state.get("run_id"),
    }
    write_outputs(result, args.output_dir)
    artifacts = {
        str(p.relative_to(args.output_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in args.output_dir.rglob("*")
        if p.is_file()
    }
    manifest = {
        "status": "complete",
        "input_predictions_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "alpha": result["alpha"],
        "n_boot": 10000,
        "seed": 42,
        "artifacts": artifacts,
        "scope": result["scope"],
        "source_sha256": saved.get("source_sha256"),
        "model_sha256": saved["model_sha256"],
        "model_version": metadata.get("model_version"),
        "model_uri": metadata.get("model_uri"),
        "model_tags": {"source_model_sha256": saved["model_sha256"]},
        "model_tags_origin": "saved_candidate_metadata_not_live_registry",
        "run_id": state.get("run_id"),
        "git_commit": args.code_revision,
        "evaluation_git_commit": saved.get("code_revision"),
        "protocol_sha256": saved.get("protocol_sha256"),
        "evaluation_manifest_sha256": hashlib.sha256(
            (directory / "artifact_manifest.json").read_bytes()
        ).hexdigest(),
        "bootstrap_method": "exact iid multinomial of joint categorical counts",
    }
    atomic_write(
        args.output_dir / "manifest_d48.json",
        (json.dumps(manifest, indent=2) + "\n").encode(),
    )
    if args.log_mlflow:
        import mlflow

        from ml.tracking_smoke import get_tracking_uri

        mlflow.set_tracking_uri(get_tracking_uri(args.tracking_uri))
        mlflow.set_experiment("fairness_audit")
        with mlflow.start_run(run_name="saved-predictions-analysis") as run:
            mlflow.set_tag("model_status", "provisional")
            mlflow.log_artifacts(str(args.output_dir))
            print(f"MLflow run_id={run.info.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
