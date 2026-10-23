"""Validation des configs sans Optuna, donnees ni reseau."""

import copy
from pathlib import Path

import pytest
from benchmark.config import MODEL_NAMES, load_configuration, validate_configuration

ROOT = Path(__file__).resolve().parents[2]


def test_incomplete_configuration_refuses_real_launch():
    with pytest.raises(ValueError, match="Lancement reel refuse"):
        load_configuration(ROOT)


def test_explicit_test_mode_loads_all_five_spaces_and_shared_budget():
    config = load_configuration(ROOT, allow_incomplete=True)
    assert set(config["search_spaces"]["models"]) == set(MODEL_NAMES)
    assert config["optuna"]["n_trials"] == 30
    assert config["benchmark"]["seeds"] == list(range(10))


@pytest.mark.parametrize("path", ["n_trials", "models", "sampler"])
def test_missing_required_field_blocks_real_launch_but_not_test_mode(path):
    config = load_configuration(ROOT, allow_incomplete=True)
    del config["optuna"][path]
    assert validate_configuration(config, allow_incomplete=True)
    with pytest.raises(ValueError, match="incomplete"):
        validate_configuration(config)


def test_individual_budget_refused_even_in_test_mode():
    config = load_configuration(ROOT, allow_incomplete=True)
    config["optuna"]["model_budgets"] = {"logreg": 30, "rf": 50}
    with pytest.raises(ValueError, match="Budget individuel"):
        validate_configuration(config, allow_incomplete=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("zone", "probability_calibration"),
        ("n_splits", 3),
        ("seeds", [42]),
        ("legit_per_fraud", 1),
    ],
)
def test_validated_protocol_cannot_be_silently_changed(field, value):
    config = load_configuration(ROOT, allow_incomplete=True)
    config["benchmark"][field] = value
    with pytest.raises(ValueError, match="protocole"):
        validate_configuration(config, allow_incomplete=True)


@pytest.mark.parametrize("change", ["weights", "bounds", "model"])
def test_invalid_spaces_are_rejected(change):
    config = copy.deepcopy(load_configuration(ROOT, allow_incomplete=True))
    models = config["search_spaces"]["models"]
    if change == "weights":
        models["rf"]["fixed_params"]["class_weight"] = "balanced"
    elif change == "bounds":
        models["logreg"]["parameters"]["C"]["low"] = -1
    else:
        del models["mlp"]
    with pytest.raises(ValueError):
        validate_configuration(config, allow_incomplete=True)
