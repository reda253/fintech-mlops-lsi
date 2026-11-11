"""Métriques et bootstrap apparié par transaction pour l'évaluation finale."""

from __future__ import annotations

import numpy as np

N_BOOTSTRAP = 10_000
BOOTSTRAP_SEED = 42


def weighted_metrics(y, p, members, weights, *, ranking=None):
    """Mesures agrégées avec poids de fréquence ; valeurs indéfinies = None."""
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    weights = np.asarray(weights, dtype=float)
    n = float(weights.sum())
    if n <= 0:
        raise ValueError("Bootstrap vide")
    point = p >= 0.5
    pos = y == 1
    neg = ~pos
    tp = float(weights[pos & point].sum())
    fp = float(weights[neg & point].sum())
    fn = float(weights[pos & ~point].sum())
    tn = float(weights[neg & ~point].sum())
    total_pos = tp + fn
    total_neg = tn + fp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / total_pos if total_pos else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
    denominator = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
    mcc = (tp * tn - fp * fn) / denominator if denominator else 0.0
    # Tri unique par appel : les égalités de scores sont regroupées avant AP/AUC.
    if ranking is None:
        order = np.argsort(-p, kind="stable")
        starts = np.r_[0, np.flatnonzero(np.diff(p[order])) + 1]
    else:
        order, starts = ranking
    weighted_pos = np.add.reduceat(weights[order] * y[order], starts)
    weighted_neg = np.add.reduceat(weights[order] * (1 - y[order]), starts)
    tps = np.cumsum(weighted_pos)
    fps = np.cumsum(weighted_neg)
    if total_pos:
        precisions = np.divide(
            tps, tps + fps, out=np.zeros_like(tps), where=(tps + fps) != 0
        )
        ap = float(np.sum(weighted_pos * precisions) / total_pos)
    else:
        ap = None
    if total_pos and total_neg:
        roc = float(
            np.trapezoid(np.r_[0.0, tps / total_pos], np.r_[0.0, fps / total_neg])
        )
    else:
        roc = None
    clipped = np.clip(p, 1e-15, 1 - 1e-15)
    brier = float(np.dot(weights, (p - y) ** 2) / n)
    loss = float(
        -np.dot(weights, y * np.log(clipped) + (1 - y) * np.log1p(-clipped)) / n
    )
    bins = np.clip(np.searchsorted(np.linspace(0, 1, 11), p, side="right") - 1, 0, 9)
    bin_y = np.bincount(bins, weights=weights * y, minlength=10)
    bin_p = np.bincount(bins, weights=weights * p, minlength=10)
    ece = float(np.abs(bin_y - bin_p).sum() / n)
    review = members.sum(axis=1) != 1
    automatic = ~review
    auto_count = float(weights[automatic].sum())
    errors = automatic & (members[:, 1] != pos)
    coverage0 = (
        float(weights[neg & members[:, 0]].sum() / total_neg) if total_neg else None
    )
    coverage1 = (
        float(weights[pos & members[:, 1]].sum() / total_pos) if total_pos else None
    )
    return {
        "pr_auc": ap,
        "roc_auc": roc,
        "mcc": float(mcc),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": (tp + tn) / n,
        "brier_score": brier,
        "log_loss": loss,
        "ece": ece,
        "review_rate": float(weights[review].sum() / n),
        "automation_rate": auto_count / n,
        "automatic_error_rate": float(weights[errors].sum() / auto_count)
        if auto_count
        else None,
        "coverage_legitimate": coverage0,
        "coverage_fraud": coverage1,
    }


def bootstrap_intervals(
    y, p, members, group_masks, *, resamples=N_BOOTSTRAP, seed=BOOTSTRAP_SEED
):
    """Bootstrap percentile iid des transactions, mêmes tirages pour tous les groupes.

    Les réplications sans dénominateur sont exclues de l'IC concerné et comptées.
    Les transactions d'une même carte peuvent être corrélées : limite documentée.
    """
    if resamples <= 0:
        raise ValueError("Nombre de rééchantillonnages strictement positif requis")
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    members = np.asarray(members, dtype=bool)
    n = len(y)
    rng = np.random.default_rng(seed)
    point = p >= 0.5
    review = members.sum(axis=1) != 1
    order = np.argsort(-p, kind="stable")
    ranking = (order, np.r_[0, np.flatnonzero(np.diff(p[order])) + 1])
    values = {}
    groups = {
        key: {"recall": [], "false_positive_rate": [], "review_rate": []}
        for key in group_masks
    }
    for _ in range(resamples):
        indices = rng.integers(0, n, size=n)
        weights = np.bincount(indices, minlength=n)
        metrics = weighted_metrics(y, p, members, weights, ranking=ranking)
        for key, value in metrics.items():
            values.setdefault(key, []).append(value)
        for key, mask in group_masks.items():
            positives = weights[mask & (y == 1)].sum()
            negatives = weights[mask & (y == 0)].sum()
            count = weights[mask].sum()
            groups[key]["recall"].append(
                float(weights[mask & (y == 1) & point].sum() / positives)
                if positives
                else None
            )
            groups[key]["false_positive_rate"].append(
                float(weights[mask & (y == 0) & point].sum() / negatives)
                if negatives
                else None
            )
            groups[key]["review_rate"].append(
                float(weights[mask & review].sum() / count) if count else None
            )

    def interval(samples):
        finite = np.array(
            [v for v in samples if v is not None and np.isfinite(v)], dtype=float
        )
        return {
            "ci95": [float(v) for v in np.quantile(finite, [0.025, 0.975])]
            if len(finite)
            else None,
            "valid_resamples": len(finite),
            "total_resamples": resamples,
        }

    return {
        "overall": {key: interval(v) for key, v in values.items()},
        "groups": {
            key: {metric: interval(v) for metric, v in measures.items()}
            for key, measures in groups.items()
        },
        "parameters": {
            "method": "percentile",
            "unit": "transaction",
            "resamples": resamples,
            "seed": seed,
            "confidence": 0.95,
            "sampling": "iid_with_replacement",
        },
    }
