"""Smoke : configs strictes, trois tentatives, RNG reproductible, aucun reseau."""

import sys
from unittest.mock import Mock

import pytest
from benchmark import optuna_smoke
from benchmark.config import MODEL_NAMES, load_configuration


def completed(_params, _deadline):
    return {"status": "COMPLETE", "result": {"average_precision": 0.5}}


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_seeded_three_trial_study_is_reproducible_without_selecting_model(name):
    config = load_configuration()
    spaces = config["search_spaces"]["models"]
    first = optuna_smoke.run_smoke_study(name, spaces, config["optuna"], completed)
    second = optuna_smoke.run_smoke_study(name, spaces, config["optuna"], completed)
    assert first["attempted"] == first["completed"] == 3
    assert first["timeout_count"] == 0
    assert first["selected_trial"] is None
    assert [row["params"] for row in first["trials"]] == [
        row["params"] for row in second["trials"]
    ]


def test_timeouts_count_toward_budget_and_alert():
    config = load_configuration()
    evaluate = Mock(
        side_effect=lambda *args: {"status": "FAIL", "reason": "trial_timeout"}
    )
    result = optuna_smoke.run_smoke_study(
        "logreg", config["search_spaces"]["models"], config["optuna"], evaluate
    )
    assert evaluate.call_count == 3
    assert result["attempted"] == result["timeout_count"] == 3
    assert result["completed"] == 0
    assert result["timeout_alert"] is True


def test_without_smoke_flag_no_data_or_network(monkeypatch):
    reader = Mock(side_effect=AssertionError("Lecture interdite"))
    network = Mock(side_effect=AssertionError("Reseau interdit"))
    monkeypatch.setattr(optuna_smoke, "sample_development", reader)
    monkeypatch.setattr(optuna_smoke, "get_tracking_uri", network)
    monkeypatch.setattr(sys, "argv", ["optuna_smoke"])
    with pytest.raises(SystemExit) as raised:
        optuna_smoke.main()
    assert raised.value.code == 2
    reader.assert_not_called()
    network.assert_not_called()


def test_missing_decision_refuses_smoke_before_data_or_network(monkeypatch):
    reader = Mock(side_effect=AssertionError("Lecture interdite"))
    network = Mock(side_effect=AssertionError("Reseau interdit"))
    monkeypatch.setattr(optuna_smoke, "sample_development", reader)
    monkeypatch.setattr(optuna_smoke, "get_tracking_uri", network)
    monkeypatch.setattr(
        optuna_smoke, "load_configuration", Mock(side_effect=ValueError("incomplete"))
    )
    monkeypatch.setattr(sys, "argv", ["optuna_smoke", "--smoke"])
    assert optuna_smoke.main() == 1
    reader.assert_not_called()
    network.assert_not_called()


def test_unavailable_mlflow_stops_before_any_training(monkeypatch):
    reader = Mock(side_effect=AssertionError("Lecture interdite"))
    monkeypatch.setattr(optuna_smoke, "sample_development", reader)
    monkeypatch.setattr(
        optuna_smoke, "get_tracking_uri", lambda: "http://tracking.invalid"
    )
    monkeypatch.setattr(
        optuna_smoke, "check_tracking_connection", lambda *a, **k: {"status": "FAIL"}
    )
    monkeypatch.setattr(sys, "argv", ["optuna_smoke", "--smoke"])
    assert optuna_smoke.main() == 1
    reader.assert_not_called()
