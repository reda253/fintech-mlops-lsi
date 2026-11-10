"""Validation statistique P2 sur les moyennes de répétition du benchmark.

Friedman, Wilcoxon et bootstrap utilisent les 10 moyennes de répétition.
Les 50 plis servent au contrôle d'intégrité et au test de sensibilité
Nadeau–Bengio avec correction du chevauchement entre plis.
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
SCORE_BOUNDS = {
    METRIC: (0.0, 1.0),
    "roc_auc": (0.0, 1.0),
    "mcc": (-1.0, 1.0),
    "precision": (0.0, 1.0),
    "recall": (0.0, 1.0),
    "f1": (0.0, 1.0),
    "accuracy": (0.0, 1.0),
    "brier_score": (0.0, 1.0),
    "log_loss": (0.0, np.inf),
    "ece": (0.0, 1.0),
}


def load_results(
    repeat_path: Path, fold_path: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Exige 5 modèles × 10 répétitions × 5 plis et des moyennes cohérentes."""
    repeats = pd.read_csv(repeat_path)
    folds = pd.read_csv(fold_path)
    score_columns = set(SCORE_BOUNDS)
    required_repeats = {"model", "repeat"} | score_columns
    required_folds = {
        "model",
        "repeat",
        "fold",
        "outer_fit_rows",
        "outer_validation_rows",
    } | score_columns
    for frame, required, name in (
        (repeats, required_repeats, "repeat_means"),
        (folds, required_folds, "fold_scores"),
    ):
        missing = required - set(frame)
        if missing:
            raise ValueError(f"{name}: colonnes manquantes: {sorted(missing)}")
        missing_values = frame[list(required)].isna().any()
        if missing_values.any():
            raise ValueError(
                f"{name}: valeur manquante dans {sorted(missing_values[missing_values].index)}"
            )
        for metric, (lower, upper) in SCORE_BOUNDS.items():
            values = pd.to_numeric(frame[metric], errors="coerce")
            if not np.isfinite(values.to_numpy(dtype=float)).all():
                raise ValueError(f"{name}: {metric} non fini ou non numérique")
            if not values.between(lower, upper).all():
                raise ValueError(f"{name}: {metric} hors [{lower}, {upper}]")
            frame[metric] = values.astype(float)
        for column in ("repeat", "fold"):
            if column in frame:
                values = pd.to_numeric(frame[column], errors="coerce")
                if not np.isfinite(
                    values.to_numpy(dtype=float)
                ).all() or not np.array_equal(values, values.astype(int)):
                    raise ValueError(f"{name}: {column} doit être entier")
                frame[column] = values.astype(int)
        if set(frame["model"]) != set(MODELS):
            raise ValueError(f"{name}: les cinq modèles canoniques sont requis")
    for column in ("outer_fit_rows", "outer_validation_rows"):
        values = pd.to_numeric(folds[column], errors="coerce")
        if (
            not np.isfinite(values.to_numpy(dtype=float)).all()
            or (values <= 0).any()
            or not np.array_equal(values, values.astype(int))
        ):
            raise ValueError(f"fold_scores: {column} doit être un entier positif")
        folds[column] = values.astype(int)
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
    for column in ("outer_fit_rows", "outer_validation_rows"):
        sizes = folds.pivot(index=["repeat", "fold"], columns="model", values=column)
        if not (sizes.nunique(axis=1) == 1).all():
            raise ValueError(
                f"{column}: effectifs différents entre modèles pour un pli"
            )
    actual = folds.groupby(["model", "repeat"])[list(SCORE_BOUNDS)].mean()
    given = repeats.set_index(["model", "repeat"])[list(SCORE_BOUNDS)]
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


def nadeau_bengio_on_folds(
    differences: np.ndarray, test_train_ratios: np.ndarray
) -> dict:
    """Test t corrigé sur 50 différences appariées de plis répétés.

    Variance corrigée : (1/n + moyenne(n_validation/n_train)) * s².
    Les tailles sont celles du train naturel avant sous-échantillonnage.
    Les plis partagent des observations : cette correction les suppose
    suffisamment comparables ; elle ne rend pas les répétitions indépendantes.
    Source : https://proceedings.neurips.cc/paper_files/paper/1999/file/7d12b66d3df6af8d429c1a357d8b9e1a-Paper.pdf
    """
    differences = np.asarray(differences, dtype=float)
    ratios = np.asarray(test_train_ratios, dtype=float)
    n = len(differences)
    if (
        differences.shape != (50,)
        or ratios.shape != (50,)
        or not np.isfinite(differences).all()
        or not np.isfinite(ratios).all()
        or (ratios <= 0).any()
    ):
        raise ValueError(
            "Nadeau-Bengio: 50 différences et ratios finis positifs requis"
        )
    test_train_ratio = float(ratios.mean())
    mean = float(np.mean(differences))
    variance = float(np.var(differences, ddof=1))
    denominator = float(np.sqrt((1 / n + test_train_ratio) * variance))
    if denominator == 0:
        return {
            "t": None,
            "p_value": None,
            "df": n - 1,
            "test_train_ratio": test_train_ratio,
            "unit": "paired_fold",
            "n_folds": n,
            "reason": "variance nulle",
        }
    t_stat = mean / denominator
    return {
        "t": float(t_stat),
        "p_value": float(2 * stats.t.sf(abs(t_stat), df=n - 1)),
        "df": n - 1,
        "test_train_ratio": test_train_ratio,
        "unit": "paired_fold",
        "n_folds": n,
        "interpretation": "analyse de sensibilité ; plis répétés corrélés",
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
    effect_threshold: float | None = None,
) -> dict:
    """Préselection statistique ; aucune promotion automatique."""
    if effect_threshold is not None and (
        not np.isfinite(effect_threshold) or not 0 <= effect_threshold <= 1
    ):
        raise ValueError("effect_threshold doit être fini et dans [0, 1]")
    order = sorted(MODELS, key=lambda x: (-model_results[x]["mean_pr_auc"], x))
    first = order[0]
    by_pair = {frozenset((x["model_a"], x["model_b"])): x for x in comparisons}

    def superiority_demonstrated(other: str) -> bool:
        if friedman_p >= ALPHA:
            return False
        pair = by_pair[frozenset((first, other))]
        direction = 1 if pair["model_a"] == first else -1
        low, high = pair["difference_ci95"]
        return (
            pair["p_holm"] is not None
            and pair["p_holm"] < ALPHA
            and direction * pair["rank_biserial"] > 0
            and (low > 0 if direction == 1 else high < 0)
        )

    candidates = [first] + [
        name for name in order[1:] if not superiority_demonstrated(name)
    ]
    if len(candidates) == 1:
        if effect_threshold is None:
            return {
                "model": None,
                "status": "effect_threshold_required",
                "reason": "supériorité démontrée, mais seuil d'effet non négligeable non défini",
                "candidates": [first],
            }
        runner = order[1]
        pair = by_pair[frozenset((first, runner))]
        lower_bound = (
            pair["difference_ci95"][0]
            if pair["model_a"] == first
            else -pair["difference_ci95"][1]
        )
        if lower_bound >= effect_threshold:
            return {
                "model": first,
                "status": "provisional",
                "reason": "Holm, direction et borne inférieure de l'IC apparié satisfont le seuil d'effet post hoc",
                "candidates": [first],
                "sensitivity_max_effect_threshold": float(lower_bound),
            }
        return {
            "model": None,
            "status": "effect_threshold_not_met",
            "reason": "borne inférieure de l'IC apparié sous le seuil d'effet post hoc ; sélection en attente",
            "candidates": [first, runner],
            "sensitivity_max_effect_threshold": float(lower_bound),
        }
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
        "supériorité non démontrée pour tous les candidats ; Brier minimal"
        if len(candidates) == 1
        else "supériorité non démontrée ; p95 minimal, puis identifiant stable"
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
    effect_threshold: float | None = None,
) -> dict:
    """Exécute l'analyse et écrit Markdown, JSON et PNG ; aucune donnée brute lue."""
    if effect_threshold is not None and (
        not np.isfinite(effect_threshold) or not 0 <= effect_threshold <= 1
    ):
        raise ValueError("effect_threshold doit être fini et dans [0, 1]")
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
    # Sensibilité distincte : 50 plis appariés ; Friedman/Wilcoxon restent sur n=10.
    fold_matrix = folds.pivot(index=["repeat", "fold"], columns="model", values=METRIC)[
        list(MODELS)
    ]
    fold_sizes = folds.loc[folds["model"] == MODELS[0]].set_index(["repeat", "fold"])
    fold_sizes = fold_sizes.loc[fold_matrix.index]
    test_train_ratios = (
        fold_sizes["outer_validation_rows"] / fold_sizes["outer_fit_rows"]
    ).to_numpy(dtype=float)
    sensitivity = {
        f"{order[0]}_vs_{name}": nadeau_bengio_on_folds(
            (fold_matrix[order[0]] - fold_matrix[name]).to_numpy(),
            test_train_ratios,
        )
        for name in order[1:]
    }
    figure = output_dir / "figures" / "critical_difference.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    diagram = critical_difference_plot(matrix, figure)
    selection = select_model(
        model_results,
        comparisons,
        friedman_p,
        _latencies(latency_path),
        effect_threshold=effect_threshold,
    )
    result = {
        "primary_metric": METRIC,
        "unit": "repeat_mean",
        "n_repeats": 10,
        "n_folds_per_repeat": 5,
        "seed": seed,
        "bootstrap_resamples": N_RESAMPLES,
        "alpha": ALPHA,
        "effect_threshold_pr_auc": effect_threshold,
        "effect_threshold_provenance": "post_hoc"
        if effect_threshold is not None
        else None,
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
    effect_threshold = result.get("effect_threshold_pr_auc")
    if effect_threshold is not None:
        lines += [
            "",
            f"Seuil d'effet non négligeable : {effect_threshold:.6f} point de PR-AUC. Décision **post hoc**, prise après observation du benchmark ; cette réanalyse n'est pas une confirmation indépendante.",
        ]
        bound = selected.get("sensitivity_max_effect_threshold")
        if bound is not None and bound > 0:
            leader = selected["candidates"][0]
            leader_label = "XGBoost" if leader == "xgb" else leader
            verb = (
                "est retenu à titre provisoire"
                if selected["model"] == leader
                else "serait retenu à titre provisoire"
            )
            lines.append(
                f"Sensibilité : {leader_label} {verb} pour tout seuil de 0 à {bound:.17g} inclus (≈ {bound:.4f}, borne inférieure de l'IC bootstrap apparié face au deuxième modèle). Au-delà, la sélection reste en attente."
            )
    lines += [
        "",
        f"Sélection provisoire : {selected['model'] or 'en attente'} ({selected['reason']}). Aucune promotion automatique.",
        "",
        "## Sensibilité Nadeau–Bengio",
        "",
        "Sur les 50 différences de plis appariés (ddl=49) : correction 1/50 + moyenne(n_validation/n_train naturel) calculée sur les effectifs réels. Les répétitions partagent des observations ; ces p-values restent une analyse de sensibilité et ne changent pas la décision Wilcoxon–Holm.",
    ]
    for pair, item in result["nadeau_bengio_sensitivity"].items():
        value = (
            "indéfini (variance nulle)"
            if item["p_value"] is None
            else f"t={item['t']:.4f}, p={item['p_value']:.6g}"
        )
        lines.append(
            f"- {pair}: {value} ; ratio validation/train moyen={item.get('test_train_ratio', float('nan')):.8f}"
        )
    lines += [
        "",
        "![Diagramme de différence critique](figures/critical_difference.png)",
        "",
        "La barre CD est celle de Nemenyi, affichée à titre descriptif ; les conclusions reposent sur Wilcoxon–Holm.",
        "",
        "Limites : 10 blocs seulement, un seul jeu Sparkov, plis stratifiés non temporels, dépendance résiduelle entre répétitions ; aucune conclusion sur la zone de test final. Le seuil d'effet a été décidé post hoc ; aucune promotion automatique. La latence p95 du pipeline complet n'est pas mesurée ici.",
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
        "--effect-threshold",
        type=float,
        default=None,
        help="Effet minimal en PR-AUC, décision post hoc explicitement fournie",
    )
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
        effect_threshold=args.effect_threshold,
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
                if args.effect_threshold is not None:
                    mlflow.log_param("effect_threshold_pr_auc", args.effect_threshold)
                    mlflow.set_tag("effect_threshold_provenance", "post_hoc")
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
