"""Bind the MLflow-served model to the frozen D48 candidate (D44 joblib).

The D48 artifacts only carry the SHA-256 of the frozen joblib. Comparing that
hash with a CLI argument is not enough: the model actually served by MLflow
must also be bound to the same frozen object. This module verifies the joblib
hash and then checks that the served model produces the same calibrated
probabilities on a fixed probe, so a different model with identical alpha and
conformal thresholds is still refused.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from ml.src.evaluation.final_artifacts import APPROVED_D48_MODEL_SHA256
from ml.src.evaluation.probe import identity_probe

PROBABILITY_ATOL = 1e-9
BOUND_ATTRIBUTES = ("alpha", "threshold_legit", "threshold_fraud")


class ModelBindingError(ValueError):
    """The served model is not the approved frozen candidate."""


@dataclass(frozen=True)
class FrozenCandidate:
    """A frozen joblib whose bytes match the approved D44 candidate."""

    path: Path
    sha256: str
    model: Any


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelBindingError(message)


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_frozen_candidate(
    path: str | Path,
    expected_sha256: str = APPROVED_D48_MODEL_SHA256,
) -> FrozenCandidate:
    """Load the frozen candidate and refuse any other joblib."""

    source = Path(path)
    _require(source.is_file(), f"candidat fige absent: {source}")
    digest = sha256_file(source)
    _require(
        digest == str(expected_sha256).lower(),
        "empreinte du candidat fige differente de D44",
    )
    try:
        model = joblib.load(source)
    except Exception as exc:
        raise ModelBindingError(f"candidat fige illisible: {source}") from exc

    missing = [
        name
        for name in (*BOUND_ATTRIBUTES, "batch_probabilities")
        if getattr(model, name, None) is None
    ]
    _require(not missing, f"candidat fige incomplet: {missing}")
    return FrozenCandidate(path=source, sha256=digest, model=model)


def _probabilities(model: Any, label: str) -> np.ndarray:
    probe = identity_probe()
    try:
        raw = model.batch_probabilities(probe)
    except Exception as exc:
        raise ModelBindingError(f"{label}: probabilites impossibles: {exc}") from exc

    probabilities = np.asarray(raw, dtype=np.float64)
    _require(
        probabilities.shape == (len(probe),),
        f"{label}: sortie de probabilites invalide",
    )
    _require(
        np.isfinite(probabilities).all()
        and ((probabilities >= 0.0) & (probabilities <= 1.0)).all(),
        f"{label}: probabilites hors [0, 1]",
    )
    return probabilities


def assert_model_binding(frozen: FrozenCandidate, served: Any) -> None:
    """Require the MLflow-served model to be behaviourally the frozen candidate."""

    for attribute in BOUND_ATTRIBUTES:
        expected = float(getattr(frozen.model, attribute))
        observed = getattr(served, attribute, None)
        _require(
            observed is not None,
            f"modele servi: attribut {attribute} absent",
        )
        _require(
            math.isclose(float(observed), expected, rel_tol=0, abs_tol=1e-12),
            f"modele servi: {attribute} different du candidat fige",
        )

    frozen_probabilities = _probabilities(frozen.model, "candidat fige")
    served_probabilities = _probabilities(served, "modele servi")
    _require(
        np.allclose(
            frozen_probabilities,
            served_probabilities,
            rtol=0.0,
            atol=PROBABILITY_ATOL,
        ),
        "modele servi different du candidat fige malgre des seuils identiques",
    )
