"""Tests synthétiques : aucune lecture des artefacts réels du benchmark."""

import json

import numpy as np
import pandas as pd
import pytest

from ml.stats.validate import MODELS, holm_adjust, load_results, main


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
    assert result["selection"]["model"] == "xgb"
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
