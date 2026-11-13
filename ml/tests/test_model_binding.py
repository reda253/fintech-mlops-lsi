"""D48: the served model must be bound to the approved frozen joblib."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pytest

from ml.src.evaluation.model_binding import (
    ModelBindingError,
    assert_model_binding,
    load_frozen_candidate,
    sha256_file,
)


class StubModel:
    """Minimal picklable model exposing the D48 binding surface."""

    def __init__(
        self,
        probability: float,
        *,
        alpha: float = 0.02,
        threshold_legit: float = 0.5,
        threshold_fraud: float = 0.6,
    ):
        self.probability = float(probability)
        self.alpha = alpha
        self.threshold_legit = threshold_legit
        self.threshold_fraud = threshold_fraud

    def batch_probabilities(self, frame) -> np.ndarray:
        return np.full(len(frame), self.probability, dtype=np.float64)


def _dump(tmp_path: Path, model, name: str = "candidate.joblib") -> Path:
    path = tmp_path / name
    joblib.dump(model, path)
    return path


def test_frozen_candidate_requires_the_approved_hash(tmp_path: Path):
    path = _dump(tmp_path, StubModel(0.2))

    with pytest.raises(ModelBindingError, match="differente de D44"):
        load_frozen_candidate(path)


def test_frozen_candidate_loads_with_a_matching_hash(tmp_path: Path):
    path = _dump(tmp_path, StubModel(0.2))
    digest = sha256_file(path)

    candidate = load_frozen_candidate(path, expected_sha256=digest)

    assert candidate.sha256 == digest
    assert candidate.model.probability == pytest.approx(0.2)


def test_frozen_candidate_must_expose_probabilities(tmp_path: Path):
    path = _dump(tmp_path, {"not": "a model"})
    digest = sha256_file(path)

    with pytest.raises(ModelBindingError, match="incomplet"):
        load_frozen_candidate(path, expected_sha256=digest)


def test_different_model_with_same_alpha_and_thresholds_is_refused(tmp_path: Path):
    path = _dump(tmp_path, StubModel(0.2))
    digest = sha256_file(path)
    frozen = load_frozen_candidate(path, expected_sha256=digest)

    served = StubModel(0.9)

    with pytest.raises(ModelBindingError, match="seuils identiques"):
        assert_model_binding(frozen, served)


def test_served_model_with_a_different_threshold_is_refused(tmp_path: Path):
    path = _dump(tmp_path, StubModel(0.2))
    digest = sha256_file(path)
    frozen = load_frozen_candidate(path, expected_sha256=digest)

    served = StubModel(0.2, threshold_fraud=0.7)

    with pytest.raises(ModelBindingError, match="threshold_fraud"):
        assert_model_binding(frozen, served)


def test_matching_served_model_is_accepted(tmp_path: Path):
    path = _dump(tmp_path, StubModel(0.2))
    digest = sha256_file(path)
    frozen = load_frozen_candidate(path, expected_sha256=digest)

    assert_model_binding(frozen, StubModel(0.2))
