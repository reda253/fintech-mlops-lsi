"""Tests synthétiques : aucune lecture des artefacts réels du benchmark."""

import json

import numpy as np
import pandas as pd
import pytest

from ml.stats.validate import (
    MODELS,
    SCORE_BOUNDS,
    holm_adjust,
    load_results,
    main,
    nadeau_bengio_on_folds,
    select_model,
)


def synthetic_csvs(tmp_path, *, distinct):
    repeats = []
    folds = []
    levels = dict(zip(MODELS, [0.20, 0.55, 0.90, 0.35, 0.70], strict=True))
    for repeat in range(10):
        shared = (repeat - 4.5) / 1000
        for model in MODELS:
            score = (levels[model] if distinct else 0.50) + shared
            brier = (1 - score) / 100
            repeats.append(
                {
                    "model": model,
                    "repeat": repeat,
                    "average_precision": score,
                    "brier_score": brier,
                    **{
                        metric: 1 - score if metric == "log_loss" else score
                        for metric in SCORE_BOUNDS
                        if metric not in {"average_precision", "brier_score"}
                    },
                }
            )
            for fold in range(5):
                folds.append(
                    {
                        "model": model,
                        "repeat": repeat,
                        "fold": fold,
                        "average_precision": score,
                        "brier_score": brier,
                        "outer_fit_rows": 80,
                        "outer_validation_rows": 20,
                        **{
                            metric: 1 - score if metric == "log_loss" else score
                            for metric in SCORE_BOUNDS
                            if metric not in {"average_precision", "brier_score"}
                        },
                    }
                )
    repeat_path = tmp_path / "repeat_means.csv"
    fold_path = tmp_path / "fold_scores.csv"
    pd.DataFrame(repeats).to_csv(repeat_path, index=False)
    pd.DataFrame(folds).to_csv(fold_path, index=False)
    return repeat_path, fold_path


def test_clear_difference_selects_leader(tmp_path):
    repeat_path, fold_path = synthetic_csvs(tmp_path, distinct=True)
    output = tmp_path / "output"
    assert (
        main(
            [
                "--repeat-means",
                str(repeat_path),
                "--fold-scores",
                str(fold_path),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert result["unit"] == "repeat_mean"
    assert result["n_repeats"] == 10
    assert result["fold_rows_checked"] == 250
    assert result["friedman"]["p_value"] < 0.05
    assert result["selection"]["model"] is None
    assert result["selection"]["status"] == "effect_threshold_required"
    assert result["selection"]["candidates"] == ["xgb"]
    assert result["nadeau_bengio_sensitivity"]["xgb_vs_mlp"]["n_folds"] == 50
    assert result["nadeau_bengio_sensitivity"]["xgb_vs_mlp"]["test_train_ratio"] == 0.25
    pair = next(
        x for x in result["pairwise"] if {x["model_a"], x["model_b"]} == {"xgb", "mlp"}
    )
    assert pair["p_holm"] < 0.05
    assert (output / "stats_report.md").is_file()
    assert (output / "figures" / "critical_difference.png").is_file()


def test_no_difference_has_no_posthoc_or_false_significance(tmp_path):
    repeat_path, fold_path = synthetic_csvs(tmp_path, distinct=False)
    output = tmp_path / "output"
    main(
        [
            "--repeat-means",
            str(repeat_path),
            "--fold-scores",
            str(fold_path),
            "--output-dir",
            str(output),
        ]
    )
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert result["friedman"] == {"statistic": 0.0, "p_value": 1.0, "kendall_w": 0.0}
    assert all(item["p_holm"] is None for item in result["pairwise"])
    assert result["selection"]["status"] == "latency_required"


def test_holm_hand_calculation():
    # Tri .01, .02, .04 : facteurs 3, 2, 1, puis maximum cumulatif.
    assert np.allclose(holm_adjust([0.04, 0.01, 0.02]), [0.04, 0.03, 0.04])


def test_rejects_inconsistent_repeat_mean(tmp_path):
    repeat_path, fold_path = synthetic_csvs(tmp_path, distinct=True)
    frame = pd.read_csv(repeat_path)
    frame.loc[0, "average_precision"] += 0.01
    frame.to_csv(repeat_path, index=False)
    with pytest.raises(ValueError, match="ne correspondent"):
        load_results(repeat_path, fold_path)


@pytest.mark.parametrize(
    ("source", "metric", "value", "message"),
    [
        ("fold", "average_precision", -0.1, "average_precision"),
        ("fold", "roc_auc", np.nan, "roc_auc"),
        ("repeat", "roc_auc", 1.1, "roc_auc"),
        ("repeat", "precision", np.inf, "precision"),
        ("fold", "mcc", -1.1, "mcc"),
        ("fold", "recall", -0.1, "recall"),
        ("repeat", "f1", 1.1, "f1"),
        ("fold", "accuracy", np.nan, "accuracy"),
        ("repeat", "brier_score", 1.1, "brier_score"),
        ("repeat", "log_loss", -0.1, "log_loss"),
        ("fold", "ece", 1.1, "ece"),
    ],
)
def test_rejects_invalid_score(tmp_path, source, metric, value, message):
    repeat_path, fold_path = synthetic_csvs(tmp_path, distinct=True)
    path = fold_path if source == "fold" else repeat_path
    frame = pd.read_csv(path)
    frame.loc[0, metric] = value
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match=message):
        load_results(repeat_path, fold_path)


def test_rejects_missing_required_metric(tmp_path):
    repeat_path, fold_path = synthetic_csvs(tmp_path, distinct=True)
    frame = pd.read_csv(fold_path).drop(columns="recall")
    frame.to_csv(fold_path, index=False)
    with pytest.raises(ValueError, match="recall"):
        load_results(repeat_path, fold_path)


def test_rejects_mismatched_fold_sizes(tmp_path):
    repeat_path, fold_path = synthetic_csvs(tmp_path, distinct=True)
    frame = pd.read_csv(fold_path)
    frame.loc[0, "outer_fit_rows"] = 81
    frame.to_csv(fold_path, index=False)
    with pytest.raises(ValueError, match="outer_fit_rows"):
        load_results(repeat_path, fold_path)


def test_rejects_inconsistent_secondary_repeat_mean(tmp_path):
    repeat_path, fold_path = synthetic_csvs(tmp_path, distinct=True)
    frame = pd.read_csv(repeat_path)
    frame.loc[0, "roc_auc"] += 0.01
    frame.to_csv(repeat_path, index=False)
    with pytest.raises(ValueError, match="ne correspondent"):
        load_results(repeat_path, fold_path)


def test_nadeau_bengio_uses_50_paired_folds_and_real_ratio():
    differences = np.linspace(0.01, 0.05, 50)
    ratios = np.linspace(0.24, 0.26, 50)
    result = nadeau_bengio_on_folds(differences, ratios)
    expected = differences.mean() / np.sqrt(
        (1 / 50 + ratios.mean()) * differences.var(ddof=1)
    )
    assert result["n_folds"] == 50
    assert result["df"] == 49
    assert result["unit"] == "paired_fold"
    assert result["test_train_ratio"] == pytest.approx(ratios.mean())
    assert result["t"] == pytest.approx(expected)
    with pytest.raises(ValueError, match="50 différences"):
        nadeau_bengio_on_folds(differences[:10], ratios[:10])


@pytest.mark.parametrize(
    ("rank_effect", "ci", "expected_model"),
    [
        (1.0, [-0.01, 0.02], "rf"),
        (1.0, [0.0, 0.02], "rf"),
        (-0.2, [0.01, 0.03], "rf"),
        (1.0, [0.01, 0.03], None),
    ],
)
def test_selection_checks_effect_direction_and_paired_ci(
    rank_effect, ci, expected_model
):
    models = {
        model: {
            "mean_pr_auc": 0.9 if model == "xgb" else 0.8,
            "mean_brier": 0.03 if model == "rf" else 0.04,
        }
        for model in MODELS
    }
    pairs = []
    for index, a in enumerate(MODELS):
        for b in MODELS[index + 1 :]:
            includes_top_two = {a, b} == {"xgb", "rf"}
            pairs.append(
                {
                    "model_a": a,
                    "model_b": b,
                    "p_holm": 0.01,
                    "rank_biserial": (rank_effect if a == "xgb" else -rank_effect)
                    if includes_top_two
                    else (1.0 if a == "xgb" else -1.0),
                    "difference_ci95": (ci if a == "xgb" else [-ci[1], -ci[0]])
                    if includes_top_two
                    else ([0.01, 0.03] if a == "xgb" else [-0.03, -0.01]),
                }
            )
    result = select_model(models, pairs, 0.001, {})
    assert result["model"] == expected_model
    if expected_model is None:
        assert result["status"] == "effect_threshold_required"
    else:
        assert "supériorité non démontrée" in result["reason"]
