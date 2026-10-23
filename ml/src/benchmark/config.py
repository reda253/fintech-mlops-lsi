"""Lecture et validation des configurations P2, sans lancer d'entrainement."""

from __future__ import annotations

import argparse
import math
import unicodedata
from pathlib import Path

import yaml

MODEL_NAMES = ("logreg", "rf", "xgb", "nystroem_svc", "mlp")
CONFIG_NAMES = ("search_spaces", "optuna", "benchmark")
ROOT = Path(__file__).resolve().parents[3]
REQUIRED = {
    "optuna": (
        "models",
        "n_trials",
        "sampler.name",
        "sampler.seed",
        "trial_timeout.mechanism",
        "trial_timeout.seconds",
        "partition.optuna_fraction",
        "partition.internal_train_fraction",
        "partition.timestamp_ties",
        "partition.adequacy_confirmed",
        "objective",
        "direction",
    ),
    "benchmark": (
        "models",
        "zone",
        "splitter",
        "n_splits",
        "repeats",
        "seeds",
        "shared_folds_across_models",
        "legit_per_fraud",
        "primary_metric",
        "secondary_metrics",
        "ece.bins",
        "ece.strategy",
        "threshold.criterion",
        "threshold.scope",
        "threshold.internal_train_fraction",
        "threshold.ties",
        "provisional.criterion",
        "provisional.tag",
        "provisional.automatic_champion",
        "provisional.ties",
    ),
}


def _get(config, path):
    value = config
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _pending(value):
    if value is None:
        return True
    if isinstance(value, str):
        normalized = (
            unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        )
        return normalized.strip().lower() in {"", "a confirmer"}
    return False


def unresolved_fields(configs):
    """Liste les champs obligatoires manquants ou non confirmes."""
    fields = [
        f"{name}.{path}"
        for name, paths in REQUIRED.items()
        for path in paths
        if _pending(_get(configs.get(name, {}), path))
    ]
    if _get(configs.get("optuna", {}), "partition.adequacy_confirmed") is not True:
        name = "optuna.partition.adequacy_confirmed"
        if name not in fields:
            fields.append(name)
    return fields


def validate_search_spaces(config):
    """Valide les bornes YAML sans recopier les espaces dans Python."""
    models = config.get("models", {})
    if not isinstance(models, dict) or set(models) != set(MODEL_NAMES):
        raise ValueError("search_spaces : les cinq modeles exacts sont requis.")
    forbidden = {
        "class_weight",
        "scale_pos_weight",
        "sample_weight",
        "n_trials",
        "random_state",
        "n_jobs",
    }
    for name, model in models.items():
        if not isinstance(model, dict) or set(model) != {
            "fixed_params",
            "smoke_params",
            "parameters",
        }:
            raise ValueError(f"Espace {name} incomplet ou cles inconnues.")
        if any(not isinstance(model[key], dict) for key in model):
            raise ValueError(f"Espace {name} : mappings requis.")
        for key in model:
            if forbidden.intersection(model[key]):
                raise ValueError(
                    f"Espace {name} : ponderation, seed ou budget individuel interdits."
                )
        if not model["parameters"]:
            raise ValueError(f"Espace {name} : aucun hyperparametre.")
        for param, spec in model["parameters"].items():
            if not isinstance(spec, dict):
                raise TypeError(f"Specification invalide : {name}.{param}")
            kind = spec.get("type")
            if kind == "categorical":
                if not isinstance(spec.get("choices"), list) or not spec["choices"]:
                    raise ValueError(f"Choix vides : {name}.{param}")
            elif kind in {"float", "int"}:
                low, high = spec.get("low"), spec.get("high")
                if any(
                    isinstance(v, bool)
                    or not isinstance(v, (float, int))
                    or not math.isfinite(v)
                    for v in (low, high)
                ):
                    raise ValueError(f"Bornes non finies : {name}.{param}")
                if low > high or (spec.get("log", False) and low <= 0):
                    raise ValueError(f"Bornes incoherentes : {name}.{param}")
                if kind == "int" and (
                    not isinstance(low, int) or not isinstance(high, int)
                ):
                    raise ValueError(f"Bornes entieres requises : {name}.{param}")
            else:
                raise ValueError(f"Type inconnu : {name}.{param}")


def validate_configuration(configs, *, allow_incomplete=False):
    """Refuse les lancements reels incomplets ; mode test explicite uniquement."""
    for name in CONFIG_NAMES:
        if (
            not isinstance(configs.get(name), dict)
            or configs[name].get("schema_version") != 1
        ):
            raise ValueError(f"Configuration {name} absente ou schema non supporte.")
    for name, paths in REQUIRED.items():
        allowed = {"schema_version"} | {path.split(".")[0] for path in paths}
        if set(configs[name]) - allowed:
            raise ValueError(f"Budget individuel ou cle inconnue dans {name}.")
    validate_search_spaces(configs["search_spaces"])
    for name in ("optuna", "benchmark"):
        names = configs[name].get("models")
        if names is not None and (
            not isinstance(names, list) or sorted(names) != sorted(MODEL_NAMES)
        ):
            raise ValueError(
                f"{name} : les cinq modeles doivent partager le meme protocole."
            )
    optuna = configs["optuna"]
    if "model_budgets" in optuna or "budgets" in optuna:
        raise ValueError(
            "Budget individuel interdit : un n_trials global unique est requis."
        )
    trials = optuna.get("n_trials")
    if not _pending(trials) and (
        isinstance(trials, bool) or not isinstance(trials, int) or trials <= 0
    ):
        raise ValueError(
            "n_trials doit etre un entier strictement positif partage par les cinq modeles."
        )
    for path in ("partition.optuna_fraction", "partition.internal_train_fraction"):
        value = _get(optuna, path)
        if not _pending(value) and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 < value < 1
        ):
            raise ValueError(f"{path} doit etre dans ]0,1[.")
    bench = configs["benchmark"]
    fixed = {
        "zone": "development",
        "splitter": "StratifiedKFold",
        "n_splits": 5,
        "repeats": 10,
        "seeds": list(range(10)),
        "legit_per_fraud": 10,
        "shared_folds_across_models": True,
        "primary_metric": "average_precision",
        "ece.bins": 10,
        "ece.strategy": "uniform",
        "threshold.criterion": "max_f1",
        "threshold.scope": "inner_training_validation",
        "provisional.tag": "provisional",
        "provisional.automatic_champion": False,
        "threshold.internal_train_fraction": 0.8,
        "provisional.criterion": "mean_repeat_average_precision",
        "secondary_metrics": [
            "roc_auc",
            "f1",
            "precision",
            "recall",
            "mcc",
            "brier_score",
            "log_loss",
            "ece",
        ],
    }
    for path, expected in fixed.items():
        value = _get(bench, path)
        if not _pending(value) and value != expected:
            raise ValueError(f"benchmark.{path} contredit le protocole valide.")
    for path, choices in {
        "sampler.name": {"RandomSampler", "TPESampler"},
        "trial_timeout.mechanism": {"process_wall_clock"},
        "partition.timestamp_ties": {"keep_left"},
        "objective": {"average_precision"},
        "direction": {"maximize"},
    }.items():
        value = _get(optuna, path)
        if not _pending(value) and value not in choices:
            raise ValueError(f"optuna.{path} non supporte.")
    seconds = _get(optuna, "trial_timeout.seconds")
    if not _pending(seconds) and (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not math.isfinite(seconds)
        or seconds <= 0
    ):
        raise ValueError("Delai par essai : nombre fini strictement positif requis.")
    seed = _get(optuna, "sampler.seed")
    if not _pending(seed) and (
        isinstance(seed, bool) or not isinstance(seed, int) or seed < 0
    ):
        raise ValueError("Seed du sampler : entier positif ou nul requis.")
    for path, choices in {
        "threshold.ties": {"higher_threshold", "lower_threshold"},
        "provisional.ties": {"brier_then_latency", "retain_ties"},
    }.items():
        value = _get(bench, path)
        if not _pending(value) and value not in choices:
            raise ValueError(f"benchmark.{path} non supporte.")
    fields = unresolved_fields(configs)
    if fields and not allow_incomplete:
        raise ValueError(
            "Configuration incomplete : "
            + ", ".join(fields)
            + ". Lancement reel refuse."
        )
    return fields


def load_configuration(root=ROOT, *, allow_incomplete=False):
    """Charge les trois YAML ; aucune resolution implicite des choix ouverts."""
    configs = {}
    for name in CONFIG_NAMES:
        path = Path(root) / "configs" / f"{name}.yaml"
        if not path.is_file():
            raise ValueError(f"Configuration manquante : configs/{name}.yaml")
        with path.open(encoding="utf-8") as stream:
            configs[name] = yaml.safe_load(stream)
    validate_configuration(configs, allow_incomplete=allow_incomplete)
    return configs


def main():
    """Prevol strict : ne charge aucune donnee, n'entraine aucun modele."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        load_configuration(args.root)
    except ValueError as exc:
        parser.exit(2, str(exc) + "\n")
    print("Configuration complete ; aucun calcul lance.")


if __name__ == "__main__":
    main()
