"""Lectures bornees, prevol et chronometrage sur donnees synthetiques."""

import sys
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from benchmark import models_smoke
from benchmark.config import load_configuration
from preprocessing.pipeline import split_features_target

ROOT = Path(__file__).resolve().parents[2]


def raw_frame(size=300):
    return pd.DataFrame(
        {
            "trans_date_trans_time": pd.date_range(
                "2019-01-01", periods=size, freq="min"
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "dob": ["1980-01-01"] * size,
            "amt": np.arange(size) + 1.0,
            "category": ["grocery_pos", "gas_transport"] * (size // 2),
            "gender": ["F", "M"] * (size // 2),
            "state": ["CA"] * size,
            "city_pop": [1000] * size,
            "lat": [40.0] * size,
            "long": [-73.0] * size,
            "merch_lat": [40.1] * size,
            "merch_long": [-73.1] * size,
            "cc_num": np.arange(size),
            "trans_num": [f"synthetic_{i}" for i in range(size)],
            "is_fraud": (np.arange(size) % 4 == 0).astype(int),
        }
    )


def test_sampling_never_parses_reserved_labels_or_features(tmp_path):
    path = tmp_path / "data/raw/fraudTrain.csv"
    path.parent.mkdir(parents=True)
    frame = raw_frame()
    frame["is_fraud"] = frame["is_fraud"].astype(object)
    frame["amt"] = frame["amt"].astype(object)
    frame.loc[210:, "is_fraud"] = "FORBIDDEN_CALIBRATION_LABEL"
    frame.loc[210:, "amt"] = "FORBIDDEN_CALIBRATION_FEATURE"
    frame.sample(frac=1, random_state=7).to_csv(path, index=False)
    X, y, audit = models_smoke.sample_development(path, limit=20)
    assert len(X) == len(y) == 20
    assert y.isin([0, 1]).all()
    assert pd.to_numeric(X["amt"]).notna().all()
    assert audit["development"]["rows"] == 210
    assert audit["calibration_labels_features_loaded"] == 0
    assert audit["sample_rows"] == 20
    assert X.attrs["zone"] == "development" and y.attrs["zone"] == "development"


@pytest.mark.parametrize("size", [19, 4001, True])
def test_size_cap_rejected_before_any_data_access(monkeypatch, size):
    reader = Mock(side_effect=AssertionError("Lecture interdite"))
    monkeypatch.setattr(models_smoke.pd, "read_csv", reader)
    with pytest.raises(ValueError, match="4000"):
        models_smoke.sample_development("data/raw/fraudTrain.csv", limit=size)
    reader.assert_not_called()


def test_real_entry_point_blocks_incomplete_config_before_data_access(monkeypatch):
    reader = Mock(side_effect=AssertionError("Lecture interdite"))
    monkeypatch.setattr(models_smoke, "sample_development", reader)
    monkeypatch.setattr(
        models_smoke,
        "load_configuration",
        Mock(
            side_effect=ValueError("Configuration incomplete : Lancement reel refuse.")
        ),
    )
    monkeypatch.setattr(sys, "argv", ["models_smoke"])
    with pytest.raises(SystemExit) as raised:
        models_smoke.main()
    assert raised.value.code == 2
    reader.assert_not_called()


def test_unreachable_tracking_does_not_start_docker(monkeypatch):
    monkeypatch.setattr(
        models_smoke, "get_tracking_uri", lambda: "https://tracking.invalid"
    )
    monkeypatch.setattr(models_smoke.mlflow, "get_tracking_uri", lambda: "previous")
    monkeypatch.setattr(models_smoke.mlflow, "set_tracking_uri", Mock())
    monkeypatch.setattr(
        models_smoke.mlflow,
        "set_experiment",
        Mock(side_effect=ConnectionRefusedError()),
    )
    monkeypatch.setattr(
        models_smoke.subprocess, "check_output", Mock(return_value="commit")
    )
    result = models_smoke.log_models_smoke({})
    assert result["status"] == "FAIL" and result["docker_started"] is False
    assert result["error"]["category"] == "connection"


def test_small_diagnostic_uses_real_fold_helper_and_five_models():
    X, y = split_features_target(raw_frame(200))
    for frame in (X, y):
        frame.attrs.update(zone="development", source="data/raw/fraudTrain.csv")
    config = load_configuration(ROOT, allow_incomplete=True)
    for name in ["rf", "xgb"]:
        config["search_spaces"]["models"][name]["smoke_params"]["n_estimators"] = 5
    config["search_spaces"]["models"]["nystroem_svc"]["smoke_params"][
        "n_components"
    ] = 16
    config["search_spaces"]["models"]["mlp"]["smoke_params"].update(
        hidden_layer_sizes=[8], max_iter=50
    )
    audit = {
        "benchmark": {"rows": 1000, "frauds": 10},
        "optuna_train": {"rows": 200, "frauds": 10},
    }
    result = models_smoke.measure_models(X, y, audit, config)
    assert len(result["models"]) == 5
    assert result["counts"]["preproc_fit_rows"] == 160
    assert result["scope"] == "diagnostic_only_not_benchmark"
    for row in result["models"]:
        assert row["fit_seconds"] >= 0
        assert row["estimated_full_fold_total_seconds"] >= 0
        assert 0 <= row["pr_auc_corrected"] <= 1
