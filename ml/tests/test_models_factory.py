"""Fabriques et probabilites : petits jeux synthetiques uniquement."""

from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from benchmark.config import MODEL_NAMES, load_configuration
from models.factory import build_model
from models.search_spaces import load_search_spaces, model_parameters
from sklearn.datasets import make_classification
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
PARAMS = {
    "logreg": {"max_iter": 200},
    "rf": {"n_estimators": 8, "max_depth": 3},
    "xgb": {"n_estimators": 10, "max_depth": 2},
    "nystroem_svc": {"n_components": 16, "C": 1, "gamma": 0.1, "max_iter": 3000},
    "mlp": {
        "hidden_layer_sizes": [8],
        "max_iter": 300,
        "n_iter_no_change": 5,
        "learning_rate_init": 0.01,
    },
}


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_probabilities_and_determinism(name):
    X, y = make_classification(
        n_samples=180, n_features=8, n_informative=5, random_state=12
    )
    with threadpool_limits(limits=1):
        a = build_model(name, PARAMS[name], 42).fit(X[:140], y[:140])
        b = build_model(name, PARAMS[name], 42).fit(X[:140], y[:140])
        probabilities = a.predict_proba(X[140:])
        repeated = b.predict_proba(X[140:])
    assert probabilities.shape == (40, 2)
    assert np.isfinite(probabilities).all()
    assert ((probabilities >= 0) & (probabilities <= 1)).all()
    np.testing.assert_allclose(probabilities.sum(axis=1), 1, atol=1e-6)
    np.testing.assert_allclose(probabilities, repeated, atol=1e-7, rtol=0)
    seeds = {
        key: value
        for key, value in a.get_params(deep=True).items()
        if key.endswith("random_state")
    }
    assert seeds and all(value == 42 for value in seeds.values())
    if name == "nystroem_svc":
        assert a.method == "sigmoid" and a.cv.random_state == 42


@pytest.mark.parametrize("name", MODEL_NAMES)
@pytest.mark.parametrize(
    "parameter", ["class_weight", "scale_pos_weight", "random_state", "n_jobs"]
)
def test_weights_and_overrides_refused(name, parameter):
    with pytest.raises(ValueError, match="interdits"):
        build_model(name, {parameter: 1}, 42)


def test_unknown_name_and_disabled_early_stopping():
    with pytest.raises(ValueError, match="inconnu"):
        build_model("unknown", {}, 42)
    with pytest.raises(ValueError, match="early_stopping"):
        build_model("mlp", {"early_stopping": False}, 42)


@pytest.mark.parametrize("seed", [-1, None, True])
def test_invalid_seed(seed):
    with pytest.raises(ValueError, match="seed"):
        build_model("rf", {}, seed)


def test_yaml_spaces_are_loaded_not_duplicated_and_not_mutated(monkeypatch):
    spaces = load_search_spaces(ROOT, allow_incomplete=True)
    for name in MODEL_NAMES:
        params = model_parameters(name, spaces, smoke=True)
        assert hasattr(build_model(name, params, 42), "predict_proba")
        params["mutated"] = True
        assert "mutated" not in spaces[name]["fixed_params"]
    assert load_search_spaces(ROOT) == spaces
    config = load_configuration(ROOT)
    config["optuna"]["sampler"]["name"] = "à confirmer"
    monkeypatch.setattr(
        "benchmark.config.yaml.safe_load",
        Mock(
            side_effect=[config["search_spaces"], config["optuna"], config["benchmark"]]
        ),
    )
    with pytest.raises(ValueError, match="Lancement reel refuse"):
        load_search_spaces(ROOT)
