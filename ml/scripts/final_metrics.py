"""Métriques et bootstrap apparié par transaction pour l'évaluation finale."""

from __future__ import annotations

import numpy as np

N_BOOTSTRAP = 10_000
BOOTSTRAP_SEED = 42

# One group block: y (2) x point (2) x conformal pattern (4).
CELLS = 16


METRIC_NAMES = (
    "pr_auc",
    "roc_auc",
    "mcc_point_prediction",
    "precision_point_prediction",
    "recall_point_prediction",
    "f1_point_prediction",
    "accuracy_point_prediction",
    "brier_score",
    "log_loss",
    "ece",
    "review_rate",
    "automation_rate",
    "automatic_error_rate",
    "coverage_legitimate",
    "coverage_fraud",
    "auto_block_fraud_rate",
    "fraud_interception_rate",
    "auto_block_legitimate_rate",
)


def decision_metrics(y, members, weights):
    """Taux conformes : [1] bloque, []/[0,1] en revue ; dénominateur nul = None."""
    y = np.asarray(y, dtype=int)
    members = np.asarray(members, dtype=bool)
    weights = np.asarray(weights, dtype=float)
    blocked = ~members[:, 0] & members[:, 1]
    review = members.sum(axis=1) != 1
    positives = weights[y == 1].sum()
    negatives = weights[y == 0].sum()
    count = weights.sum()
    return {
        "auto_block_fraud_rate": float(weights[(y == 1) & blocked].sum() / positives)
        if positives
        else None,
        "fraud_interception_rate": float(
            weights[(y == 1) & (blocked | review)].sum() / positives
        )
        if positives
        else None,
        "auto_block_legitimate_rate": float(
            weights[(y == 0) & blocked].sum() / negatives
        )
        if negatives
        else None,
        "review_rate": float(weights[review].sum() / count) if count else None,
    }


def weighted_metrics(y, p, members, weights, *, ranking=None):
    """Mesures agrégées avec poids de fréquence ; valeurs indéfinies = None."""
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    weights = np.asarray(weights, dtype=float)
    n = float(weights.sum())
    if n <= 0:
        return dict.fromkeys(METRIC_NAMES)
    point = p >= 0.5
    pos = y == 1
    neg = ~pos
    tp = float(weights[pos & point].sum())
    fp = float(weights[neg & point].sum())
    fn = float(weights[pos & ~point].sum())
    tn = float(weights[neg & ~point].sum())
    total_pos = tp + fn
    total_neg = tn + fp
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / total_pos if total_pos else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    denominator = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
    mcc = (tp * tn - fp * fn) / denominator if denominator else None
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
        "mcc_point_prediction": float(mcc) if mcc is not None else None,
        "precision_point_prediction": precision,
        "recall_point_prediction": recall,
        "f1_point_prediction": f1,
        "accuracy_point_prediction": (tp + tn) / n,
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
        **decision_metrics(y, members, weights),
    }


class _BootstrapKernel:
    """Precomputed masks so one resample costs O(n) numpy calls, not 9 rebuilds.

    ``weighted_metrics`` recomputes the sort, the ECE bins and a dozen boolean
    masks on every call. Called once for the overall metrics and once per group
    (9 calls per resample, 100 000 calls for 10 000 resamples) that dominated the
    run time. Every quantity here depends linearly on the resample weights, so
    the masks are computed once and each resample is a handful of dot products
    plus the two cumulative sums the AP/AUC need.
    """

    def __init__(self, y, p, members, group_masks):
        self.n = len(y)
        self.y = y
        self.point = p >= 0.5
        pos = y == 1
        neg = ~pos
        blocked = ~members[:, 0] & members[:, 1]
        review = members.sum(axis=1) != 1
        automatic = ~review
        errors = automatic & (members[:, 1] != pos)

        def f(mask):
            return mask.astype(float)

        self.m_tp = f(pos & self.point)
        self.m_fp = f(neg & self.point)
        self.m_fn = f(pos & ~self.point)
        self.m_tn = f(neg & ~self.point)
        self.m_brier = (p - y) ** 2
        clipped = np.clip(p, 1e-15, 1 - 1e-15)
        self.m_nll = y * np.log(clipped) + (1 - y) * np.log1p(-clipped)
        self.bins = np.clip(
            np.searchsorted(np.linspace(0, 1, 11), p, side="right") - 1, 0, 9
        )
        self.m_y = f(pos)
        self.m_p = p
        self.m_cov0 = f(neg & members[:, 0])
        self.m_cov1 = f(pos & members[:, 1])
        self.m_review = f(review)
        self.m_automatic = f(automatic)
        self.m_errors = f(errors)
        self.m_block_pos = f(pos & blocked)
        self.m_intercept = f(pos & (blocked | review))
        self.m_block_neg = f(neg & blocked)
        self.y_order = y[np.argsort(-p, kind="stable")]

        order = np.argsort(-p, kind="stable")
        self.order = order
        self.starts = np.r_[0, np.flatnonzero(np.diff(p[order])) + 1]
        # Summing the sorted weights per score group with `add.reduceat` costs
        # ~16 ms per call at 511k groups; a precomputed group id plus `bincount`
        # is ~4x cheaper and stays exact (integer sums).
        self.score_groups = np.repeat(
            np.arange(len(self.starts)), np.diff(np.r_[self.starts, self.n])
        )

        attributes: dict[str, list[str]] = {}
        for key in group_masks:
            attributes.setdefault(key.split(":", 1)[0], []).append(key)
        # A transaction belongs to one group per attribute (gender AND age), so
        # each attribute needs its own cell array: one shared array would let
        # the second attribute overwrite the first.
        self.attributes: list[tuple[np.ndarray, dict[str, int], int]] = []
        offset = 0
        for keys in attributes.values():
            bases = {
                key: offset + index * CELLS for index, key in enumerate(keys, start=1)
            }
            cells = np.zeros(self.n, dtype=np.int64)
            for key in keys:
                mask = np.asarray(group_masks[key], dtype=bool)
                cells[mask] = (
                    bases[key]
                    + y[mask] * 8
                    + self.point[mask] * 4
                    + members[mask, 0] * 2
                    + members[mask, 1]
                )
            size = offset + (len(keys) + 1) * CELLS
            self.attributes.append((cells, bases, size))
            offset = size

    def overall(self, weights):
        # Counts are integers, so a single float64 cast keeps every sum exact
        # (values < 2**53) and avoids re-casting 555k elements in each dot.
        w = weights.astype(np.float64)
        n = float(w.sum())
        tp = float(np.dot(w, self.m_tp))
        fp = float(np.dot(w, self.m_fp))
        fn = float(np.dot(w, self.m_fn))
        tn = float(np.dot(w, self.m_tn))
        total_pos = tp + fn
        total_neg = tn + fp
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / total_pos if total_pos else None
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
        denominator = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
        mcc = (tp * tn - fp * fn) / denominator if denominator else None

        sorted_weights = w[self.order]
        group_total = np.bincount(
            self.score_groups, weights=sorted_weights, minlength=len(self.starts)
        )
        weighted_pos = np.bincount(
            self.score_groups,
            weights=sorted_weights * self.y_order,
            minlength=len(self.starts),
        )
        weighted_neg = group_total - weighted_pos
        tps = np.cumsum(weighted_pos)
        fps = np.cumsum(weighted_neg)
        if total_pos:
            precisions = np.divide(
                tps,
                tps + fps,
                out=np.zeros_like(tps, dtype=float),
                where=(tps + fps) != 0,
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

        brier = float(np.dot(w, self.m_brier) / n)
        loss = float(-np.dot(w, self.m_nll) / n)
        bin_y = np.bincount(self.bins, weights=w * self.m_y, minlength=10)
        bin_p = np.bincount(self.bins, weights=w * self.m_p, minlength=10)
        ece = float(np.abs(bin_y - bin_p).sum() / n)
        auto_count = float(np.dot(w, self.m_automatic))
        positives = float(np.dot(w, self.m_y))
        negatives = total_neg
        blocked_pos = float(np.dot(w, self.m_block_pos))
        return {
            "pr_auc": ap,
            "roc_auc": roc,
            "mcc_point_prediction": float(mcc) if mcc is not None else None,
            "precision_point_prediction": precision,
            "recall_point_prediction": recall,
            "f1_point_prediction": f1,
            "accuracy_point_prediction": (tp + tn) / n,
            "brier_score": brier,
            "log_loss": loss,
            "ece": ece,
            "review_rate": float(np.dot(w, self.m_review) / n),
            "automation_rate": auto_count / n,
            "automatic_error_rate": float(np.dot(w, self.m_errors) / auto_count)
            if auto_count
            else None,
            "coverage_legitimate": float(np.dot(w, self.m_cov0) / total_neg)
            if total_neg
            else None,
            "coverage_fraud": float(np.dot(w, self.m_cov1) / total_pos)
            if total_pos
            else None,
            "auto_block_fraud_rate": blocked_pos / positives if positives else None,
            "fraud_interception_rate": (
                float(np.dot(w, self.m_intercept) / positives) if positives else None
            ),
            "auto_block_legitimate_rate": float(np.dot(w, self.m_block_neg) / negatives)
            if negatives
            else None,
        }

    def groups(self, weights):
        result = {}
        blocks = []
        for cells, bases, size in self.attributes:
            counts = np.bincount(cells, weights=weights, minlength=size)
            blocks.append((counts, bases))
        for counts, bases in blocks:
            for key, base in bases.items():
                block = counts[base : base + CELLS]
                total_pos = float(block[8:16].sum())
                total_neg = float(block[0:8].sum())
                count = float(block.sum())
                blocked_pos = float(block[9] + block[13])
                review_pos = float(block[8] + block[11] + block[12] + block[15])
                blocked_neg = float(block[1] + block[5])
                review_total = float(
                    block[0]
                    + block[3]
                    + block[4]
                    + block[7]
                    + block[8]
                    + block[11]
                    + block[12]
                    + block[15]
                )
                result[key] = {
                    "recall_point_prediction": float(block[12:16].sum() / total_pos)
                    if total_pos
                    else None,
                    "false_positive_rate_point_prediction": float(
                        block[4:8].sum() / total_neg
                    )
                    if total_neg
                    else None,
                    "review_rate": float(review_total / count) if count else None,
                    "auto_block_fraud_rate": blocked_pos / total_pos
                    if total_pos
                    else None,
                    "fraud_interception_rate": (blocked_pos + review_pos) / total_pos
                    if total_pos
                    else None,
                    "auto_block_legitimate_rate": blocked_neg / total_neg
                    if total_neg
                    else None,
                }
        return result


def bootstrap_intervals(
    y,
    p,
    members,
    group_masks,
    *,
    resamples=N_BOOTSTRAP,
    seed=BOOTSTRAP_SEED,
    on_progress=None,
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
    if n == 0:
        raise ValueError("Bootstrap : observations requises")
    rng = np.random.default_rng(seed)
    kernel = _BootstrapKernel(y, p, members, group_masks)
    values: dict[str, list] = {}
    groups = {
        key: {
            name: []
            for name in (
                "recall_point_prediction",
                "false_positive_rate_point_prediction",
                "review_rate",
                "auto_block_fraud_rate",
                "fraud_interception_rate",
                "auto_block_legitimate_rate",
            )
        }
        for key in group_masks
    }
    for done in range(1, resamples + 1):
        indices = rng.integers(0, n, size=n)
        weights = np.bincount(indices, minlength=n)
        metrics = kernel.overall(weights)
        for key, value in metrics.items():
            values.setdefault(key, []).append(value)
        for key, measures in kernel.groups(weights).items():
            for name, value in measures.items():
                groups[key][name].append(value)
        if on_progress is not None and (done % 500 == 0 or done == resamples):
            on_progress(done, resamples)

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
