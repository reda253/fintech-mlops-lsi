"""Acces aux espaces YAML, sans copie Python des bornes d'hyperparametres."""

from copy import deepcopy

from benchmark.config import MODEL_NAMES, ROOT, load_configuration


def load_search_spaces(root=ROOT, *, allow_incomplete=False):
    """Le mode reel reutilise le prevol strict de toutes les configurations."""
    return load_configuration(root, allow_incomplete=allow_incomplete)["search_spaces"][
        "models"
    ]


def model_parameters(name, spaces, *, smoke=False):
    """Extrait les parametres fixes et eventuellement ceux du petit diagnostic."""
    if name not in MODEL_NAMES or name not in spaces:
        raise ValueError(f"Modele inconnu : {name}")
    params = deepcopy(spaces[name]["fixed_params"])
    if smoke:
        params.update(deepcopy(spaces[name]["smoke_params"]))
    return params
