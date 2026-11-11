"""T21d: parity checks used when replaying P2's D44 handoff package."""

from __future__ import annotations

import pytest

from ml.scripts.verify_handoff import (
    ParityError,
    _check_case,
    verify_prediction_sets,
)


def _expected() -> dict:
    return {
        "raw_probability": 0.006327430248784685,
        "fraud_probability": 0.0063,
        "prediction_set": [],
        "uncertainty": 0.0553,
        "decision": "REVUE",
    }


def test_fake_thresholds_produce_full_set_and_empty_is_review():
    assert verify_prediction_sets() == {"full_set": [0, 1], "empty_decision": "REVUE"}


def test_check_case_accepts_exact_parity():
    expected = _expected()
    _check_case("review", expected, dict(expected))


def test_check_case_rejects_set_divergence():
    expected = _expected()
    with pytest.raises(ParityError, match="prediction_set"):
        _check_case("review", expected, {**expected, "prediction_set": [1]})
