"""Validation statistique P2 sur les moyennes de répétition du benchmark.

Les plis servent uniquement au contrôle d'intégrité. Aucun test ne considère
les 50 plis comme des observations indépendantes.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

MODELS = ("logreg", "rf", "xgb", "nystroem_svc", "mlp")
METRIC = "average_precision"
ALPHA = 0.05
N_RESAMPLES = 10_000
SEED = 42
SECONDARY_METRICS = (
    "roc_auc",
    "mcc",
    "precision",
    "recall",
    "f1",
    "accuracy",
    "brier_score",
    "log_loss",
    "ece",
)


def load_results(
    repeat_path: Path, fold_path: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Exige 5 modèles × 10 répétitions × 5 plis et des moyennes cohérentes."""
    repeats = pd.read_csv(repeat_path)
    folds = pd.read_csv(fold_path)
    required_repeats = {"model", "repeat", METRIC, "brier_score"}
    required_folds = {"model", "repeat", "fold", METRIC, "brier_score"}
    for frame, required, name in (
        (repeats, required_repeats, "repeat_means"),
        (folds, required_folds, "fold_scores"),
    ):
        missing = required - set(frame)
        if missing:
            raise ValueError(f"{name}: colonnes manquantes: {sorted(missing)}")
        if frame[list(required)].isna().any().any():
            raise ValueError(f"{name}: valeur manquante dans les colonnes requises")
        for metric in (METRIC, "brier_score"):
            values = pd.to_numeric(frame[metric], errors="coerce")
            if not np.isfinite(values.to_numpy(dtype=float)).all():
                raise ValueError(f"{name}: {metric} non fini ou non numérique")
            if not values.between(0, 1).all():
                raise ValueError(f"{name}: {metric} hors [0, 1]")
            frame[metric] = values.astype(float)
        for column in ("repeat", "fold"):
            if column in frame:
                values = pd.to_numeric(frame[column], errors="coerce")
                if values.isna().any() or not np.array_equal(
                    values, values.astype(int)
                ):
                    raise ValueError(f"{name}: {column} doit être entier")
                frame[column] = values.astype(int)
        if set(frame["model"]) != set(MODELS):
            raise ValueError(f"{name}: les cinq modèles canoniques sont requis")
    if (
        repeats.duplicated(["model", "repeat"]).any()
        or folds.duplicated(["model", "repeat", "fold"]).any()
    ):
        raise ValueError("Clés modèle/répétition/pli dupliquées")
    expected_repeats = pd.MultiIndex.from_product(
        [MODELS, range(10)], names=["model", "repeat"]
    )
    expected_folds = pd.MultiIndex.from_product(
        [MODELS, range(10), range(5)], names=["model", "repeat", "fold"]
    )
    if set(repeats.set_index(["model", "repeat"]).index) != set(expected_repeats):
        raise ValueError("repeat_means: 10 répétitions par modèle requises")
    if set(folds.set_index(["model", "repeat", "fold"]).index) != set(expected_folds):
        raise ValueError("fold_scores: 5 plis par répétition et modèle requis")
    actual = folds.groupby(["model", "repeat"])[[METRIC, "brier_score"]].mean()
    given = repeats.set_index(["model", "repeat"])[[METRIC, "brier_score"]]
    if not np.allclose(
        given.loc[actual.index].to_numpy(), actual.to_numpy(), rtol=0, atol=1e-12
    ):
        raise ValueError("Les moyennes de répétition ne correspondent pas aux 5 plis")
    return repeats, folds


def holm_adjust(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni pas à pas, avec monotonie des p ajustés."""
    values = np.asarray(p_values, dtype=float)
    if (
        values.ndim != 1
        or not np.isfinite(values).all()
        or not ((0 <= values) & (values <= 1)).all()
    ):
        raise ValueError("Les p-values doivent être finies et dans [0, 1]")
    order = np.argsort(values, kind="stable")
    adjusted = np.empty(len(values), dtype=float)
    adjusted[order] = np.minimum(
        1.0,
        np.maximum.accumulate((len(values) - np.arange(len(values))) * values[order]),
    )
    return adjusted.tolist()


def bootstrap_interval(values: np.ndarray, rng: np.random.Generator) -> list[float]:
    """IC percentile 95 %, rééchantillonnage des 10 répétitions appariées."""
    values = np.asarray(values, dtype=float)
    if values.shape != (10,) or not np.isfinite(values).all():
        raise ValueError("Le bootstrap exige exactement 10 moyennes finies")
    indices = rng.integers(0, 10, size=(N_RESAMPLES, 10))
    return [float(x) for x in np.quantile(values[indices].mean(axis=1), [0.025, 0.975])]


def rank_biserial(differences: np.ndarray) -> float:
    """(W+ - W-) / (W+ + W-), rangs moyens des écarts absolus non nuls."""
    nonzero = np.asarray(differences, dtype=float)
    nonzero = nonzero[nonzero != 0]
    if not len(nonzero):
        return 0.0
    ranks = stats.rankdata(abs(nonzero))
    positive = ranks[nonzero > 0].sum()
    return float((2 * positive / ranks.sum()) - 1)


def nadeau_bengio_on_repeats(differences: np.ndarray, test_train_ratio: float) -> dict:
    """Sensibilité t corrigée sur n=10 moyennes, jamais sur les 50 plis.

    Facteur sqrt((1/n + n_test/n_train) * s²). Le test classique est dérivé
    pour les scores de plis ; appliqué aux moyennes de répétition, il reste
    une analyse de sensibilité approximative et peut sur/sous-corriger.
    Source : https://proceedings.neurips.cc/paper_files/paper/1999/file/7d12b66d3df6af8d429c1a357d8b9e1a-Paper.pdf
    """
    n = len(differences)
    if n != 10 or test_train_ratio <= 0:
        raise ValueError("Nadeau-Bengio: 10 répétitions et ratio positif requis")
    mean = float(np.mean(differences))
    variance = float(np.var(differences, ddof=1))
    denominator = float(np.sqrt((1 / n + test_train_ratio) * variance))
    if denominator == 0:
        return {"t": None, "p_value": None, "df": 9, "reason": "variance nulle"}
    t_stat = mean / denominator
    return {
        "t": float(t_stat),
        "p_value": float(2 * stats.t.sf(abs(t_stat), df=n - 1)),
        "df": n - 1,
        "test_train_ratio": test_train_ratio,
        "unit": "repeat_mean",
        "interpretation": "sensibilité approximative uniquement",
    }


def critical_difference_plot(matrix: pd.DataFrame, destination: Path) -> dict:
    """Rangs moyens et barre CD de Nemenyi, descriptive en plus de Holm."""
    n, k = matrix.shape
    ranks = matrix.rank(axis=1, ascending=False, method="average").mean().sort_values()
    q_alpha = stats.studentized_range.ppf(1 - ALPHA, k, np.inf) / np.sqrt(2)
    cd = float(q_alpha * np.sqrt(k * (k + 1) / (6 * n)))
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.set_xlim(0.7, k + 0.3)
    ax.set_ylim(-0.2, 2.0)
    ax.set_xticks(range(1, k + 1))
    ax.set_yticks([])
    ax.set_xlabel("Rang moyen (1 = meilleure PR-AUC)")
    for model, rank in ranks.items():
        ax.plot(rank, 1.0, "o", color="tab:blue")
        ax.text(rank, 1.17, model, ha="center", rotation=25)
    ax.hlines(0.55, 1, 1 + cd, color="tab:red", linewidth=3)
    ax.vlines([1, 1 + cd], 0.47, 0.63, color="tab:red")
    ax.text(1 + cd / 2, 0.28, f"CD Nemenyi = {cd:.3f}", ha="center")
    ax.set_title("Rangs des 10 répétitions ; décision par Wilcoxon-Holm")
    fig.tight_layout()
    fig.savefig(destination, dpi=160)
    plt.close(fig)
    return {
        "average_ranks": {key: float(value) for key, value in ranks.items()},
        "cd": cd,
    }


def _latencies(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}
    frame = pd.read_csv(path)
    if set(frame.columns) < {"model", "p95_ms"} or set(frame.model) != set(MODELS):
        raise ValueError("latency.csv exige model,p95_ms pour les cinq modèles")
    if frame.duplicated("model").any() or len(frame) != len(MODELS):
        raise ValueError("latency.csv: un p95 par modèle requis")
    values = pd.to_numeric(frame.p95_ms, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("latency.csv: p95_ms doit être fini et positif")
    return dict(zip(frame.model, values, strict=True))


def select_model(
    model_results: dict,
    comparisons: list[dict],
    friedman_p: float,
    latencies: dict[str, float],
) -> dict:
    """Préselection P2 ; n'effectue aucune promotion automatique."""
    order = sorted(MODELS, key=lambda x: (-model_results[x]["mean_pr_auc"], x))
    first = order[0]
    by_pair = {frozenset((x["model_a"], x["model_b"])): x for x in comparisons}
    significant = (
        friedman_p < ALPHA
        and len(order) > 1
        and by_pair[frozenset(order[:2])]["p_holm"] < ALPHA
        and by_pair[frozenset(order[:2])]["rank_biserial"] != 0
    )
    if significant:
        return {
            "model": first,
            "status": "provisional",
            "reason": "premier significativement meilleur que deuxième",
            "candidates": [first],
        }
    candidates = [first] + [
        name
        for name in order[1:]
        if friedman_p >= ALPHA or by_pair[frozenset((first, name))]["p_holm"] >= ALPHA
    ]
    best_brier = min(model_results[name]["mean_brier"] for name in candidates)
    candidates = [
        name
        for name in candidates
        if abs(model_results[name]["mean_brier"] - best_brier) <= 1e-12
    ]
    if len(candidates) > 1 and not all(name in latencies for name in candidates):
        return {
            "model": None,
            "status": "latency_required",
            "reason": "Brier égal : fournir p95 du pipeline complet",
            "candidates": candidates,
        }
    selected = min(candidates, key=lambda name: (latencies.get(name, np.inf), name))
    reason = (
        "Brier minimal"
        if len(candidates) == 1
        else "p95 minimal, puis identifiant stable"
    )
    return {
        "model": selected,
        "status": "provisional",
        "reason": reason,
        "candidates": candidates,
    }


def validate(
    repeats: pd.DataFrame,
    folds: pd.DataFrame,
    *,
    output_dir: Path,
    latency_path: Path | None = None,
    seed: int = SEED,
) -> dict:
    """Exécute l'analyse et écrit Markdown, JSON et PNG ; aucune donnée brute lue."""
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix = repeats.pivot(index="repeat", columns="model", values=METRIC)[list(MODELS)]
    brier = repeats.pivot(index="repeat", columns="model", values="brier_score")[
        list(MODELS)
    ]
    if matrix.shape != (10, 5) or not np.isfinite(matrix.to_numpy()).all():
        raise ValueError("Matrice appariée 10 × 5 incomplète")
    rng = np.random.default_rng(seed)
    if (matrix.nunique(axis=1) == 1).all():
        # Tous les modèles sont identiques dans chaque bloc : H0 ne peut être rejetée.
        friedman_statistic, friedman_p = 0.0, 1.0
    else:
        test = stats.friedmanchisquare(*(matrix[name].to_numpy() for name in MODELS))
        if not np.isfinite(test.statistic) or not np.isfinite(test.pvalue):
            raise ValueError("Friedman indéfini : vérifier les scores constants")
        friedman_statistic, friedman_p = float(test.statistic), float(test.pvalue)
    model_results = {
        name: {
            "mean_pr_auc": float(matrix[name].mean()),
            "pr_auc_ci95": bootstrap_interval(matrix[name].to_numpy(), rng),
            "mean_brier": float(brier[name].mean()),
        }
        for name in MODELS
    }
    secondary = {}
    for metric in SECONDARY_METRICS:
        if metric not in repeats:
            continue
        values = pd.to_numeric(repeats[metric], errors="coerce")
        if not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ValueError(f"repeat_means: métrique exploratoire {metric} non finie")
        secondary[metric] = {
            name: float(values.loc[repeats["model"] == name].mean()) for name in MODELS
        }
    comparisons = []
    for a, b in combinations(MODELS, 2):
        differences = (matrix[a] - matrix[b]).to_numpy()
        p_value = None
        if friedman_p < ALPHA:
            if not np.any(differences):
                p_value = 1.0
            else:
                p_value = float(
                    stats.wilcoxon(
                        differences, zero_method="wilcox", method="auto"
                    ).pvalue
                )
        comparisons.append(
            {
                "model_a": a,
                "model_b": b,
                "mean_difference": float(np.mean(differences)),
                "difference_ci95": bootstrap_interval(differences, rng),
                "rank_biserial": rank_biserial(differences),
                "p_raw": p_value,
                "p_holm": None,
            }
        )
    if friedman_p < ALPHA:
        adjusted = holm_adjust([item["p_raw"] for item in comparisons])
        for item, p_value in zip(comparisons, adjusted, strict=True):
            item["p_holm"] = p_value
    order = sorted(MODELS, key=lambda name: -model_results[name]["mean_pr_auc"])
    # Comparaisons du leader avec les quatre autres : n=10 moyennes appariées.
    sensitivity = {
        f"{order[0]}_vs_{name}": nadeau_bengio_on_repeats(
            (matrix[order[0]] - matrix[name]).to_numpy(),
            test_train_ratio=1 / 4,
        )
        for name in order[1:]
    }
    figure = output_dir / "figures" / "critical_difference.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    diagram = critical_difference_plot(matrix, figure)
    selection = select_model(
        model_results, comparisons, friedman_p, _latencies(latency_path)
    )
    result = {
        "primary_metric": METRIC,
        "unit": "repeat_mean",
        "n_repeats": 10,
        "n_folds_per_repeat": 5,
        "seed": seed,
        "bootstrap_resamples": N_RESAMPLES,
        "alpha": ALPHA,
        "fold_rows_checked": len(folds),
        "friedman": {
            "statistic": friedman_statistic,
            "p_value": friedman_p,
            "kendall_w": friedman_statistic / (10 * (len(MODELS) - 1)),
        },
        "models": model_results,
        "pairwise": comparisons,
        "nadeau_bengio_sensitivity": sensitivity,
        "critical_difference": diagram,
        "selection": selection,
        "secondary_metrics": {
            "scope": "exploratory; descriptive means only, no inferential tests",
            "means_by_model": secondary,
        },
        "figure": "figures/critical_difference.png",
    }
    (output_dir / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_report(result, output_dir / "stats_report.md")
    return result


def write_report(result: dict, destination: Path) -> None:
    friedman = result["friedman"]
    lines = [
        "# Validation statistique P2",
        "",
        "PR-AUC confirmatoire ; métriques secondaires exploratoires.",
        "Unité : 10 moyennes de répétition par modèle ; les 50 plis ne sont jamais traités comme indépendants.",
        "",
        f"Friedman : χ²={friedman['statistic']:.6g}, p={friedman['p_value']:.6g}, W de Kendall={friedman['kendall_w']:.6g}.",
        "",
        "| Modèle | PR-AUC moyenne | IC bootstrap 95 % | Brier moyen |",
        "|---|---:|---:|---:|",
    ]
    for name, item in result["models"].items():
        low, high = item["pr_auc_ci95"]
        lines.append(
            f"| {name} | {item['mean_pr_auc']:.6f} | [{low:.6f}, {high:.6f}] | {item['mean_brier']:.6f} |"
        )
    lines += [
        "",
        "## Métriques secondaires — exploratoires",
        "",
        "Moyennes des 10 répétitions, sans test d'hypothèse ni sélection après coup.",
        "",
        "| Métrique | logreg | rf | xgb | nystroem_svc | mlp |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for metric, by_model in result["secondary_metrics"]["means_by_model"].items():
        values = " | ".join(f"{by_model[name]:.6f}" for name in MODELS)
        lines.append(f"| {metric} | {values} |")
    lines += [
        "",
        "| Paire | Différence moyenne | IC 95 % | r rang-bisérial | p brute | p Holm |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in result["pairwise"]:
        low, high = item["difference_ci95"]
        raw = "—" if item["p_raw"] is None else f"{item['p_raw']:.6g}"
        holm = "—" if item["p_holm"] is None else f"{item['p_holm']:.6g}"
        lines.append(
            f"| {item['model_a']} − {item['model_b']} | {item['mean_difference']:.6f} | [{low:.6f}, {high:.6f}] | {item['rank_biserial']:.3f} | {raw} | {holm} |"
        )
    selected = result["selection"]
    lines += [
        "",
        f"Sélection provisoire : {selected['model'] or 'en attente'} ({selected['reason']}). Aucune promotion automatique.",
        "",
        "## Sensibilité Nadeau–Bengio",
        "",
        "Sur les 10 moyennes de répétition (ddl=9), correction 1/10 + 1/4 : approximation pouvant sur/sous-corriger ; le test original porte sur les plis. Ces p-values sont des analyses de sensibilité et ne changent pas la décision Wilcoxon–Holm.",
    ]
    for pair, item in result["nadeau_bengio_sensitivity"].items():
        value = (
            "indéfini (variance nulle)"
            if item["p_value"] is None
            else f"t={item['t']:.4f}, p={item['p_value']:.6g}"
        )
        lines.append(f"- {pair}: {value}")
    lines += [
        "",
        "![Diagramme de différence critique](figures/critical_difference.png)",
        "",
        "La barre CD est celle de Nemenyi, affichée à titre descriptif ; les conclusions reposent sur Wilcoxon–Holm.",
        "",
        "Limites : 10 blocs seulement, un seul jeu Sparkov, plis stratifiés non temporels, dépendance résiduelle entre répétitions ; aucune conclusion sur la zone de test final. La sélection reste provisoire et ne mesure pas encore la latence p95 du pipeline complet.",
        "",
    ]
    destination.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat-means", type=Path, required=True)
    parser.add_argument("--fold-scores", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--latency-csv",
        type=Path,
        help="Mesures externes model,p95_ms du pipeline complet",
    )
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--mlflow",
        action="store_true",
        help="Journalise le rapport et la figure sur l'URI configurée",
    )
    parser.add_argument(
        "--mlflow-run-id",
        help="Reprend un run MLflow RUNNING de statistical_validation après interruption",
    )
    args = parser.parse_args(argv)
    if args.mlflow_run_id and not args.mlflow:
        parser.error("--mlflow-run-id exige --mlflow")
    repeats, folds = load_results(args.repeat_means, args.fold_scores)
    result = validate(
        repeats,
        folds,
        output_dir=args.output_dir,
        latency_path=args.latency_csv,
        seed=args.seed,
    )
    if args.mlflow:
        import mlflow

        if __package__ in (None, ""):
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from ml.tracking_smoke import (
            _git_commit,
            _private_client_calls,
            get_tracking_uri,
        )

        mlflow.set_tracking_uri(get_tracking_uri())
        experiment = mlflow.set_experiment("statistical_validation")
        if args.mlflow_run_id:
            run_info = mlflow.get_run(args.mlflow_run_id).info
            if (
                run_info.experiment_id != experiment.experiment_id
                or run_info.status not in {"RUNNING", "FINISHED"}
            ):
                raise ValueError("Reprise MLflow : run ou statut incompatible")
        # MLflow imprime une URL avec emoji à la fermeture ; la console Windows
        # CP1252 ne sait pas l'encoder. Le contexte P3 masque cette sortie.
        with _private_client_calls(30):
            run_kwargs = (
                {"run_id": args.mlflow_run_id}
                if args.mlflow_run_id
                else {"run_name": "p2-repeat-statistics"}
            )
            with mlflow.start_run(**run_kwargs):
                mlflow.set_tag("git_commit", _git_commit())
                mlflow.log_param("unit", "repeat_mean")
                mlflow.log_param("seed", args.seed)
                mlflow.log_metric("friedman_p", result["friedman"]["p_value"])
                mlflow.log_artifact(str(args.output_dir / "results.json"))
                mlflow.log_artifact(str(args.output_dir / "stats_report.md"))
                mlflow.log_artifact(
                    str(args.output_dir / "figures" / "critical_difference.png"),
                    artifact_path="figures",
                )
    print(
        json.dumps(
            {"friedman": result["friedman"], "selection": result["selection"]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
