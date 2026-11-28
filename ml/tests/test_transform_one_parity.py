"""Exact preprocessing parity and a portable synthetic smoke reference."""

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.src.model.fraud_detector import adapt_to_sparkov_record
from ml.src.preprocessing.pipeline import build_preprocessing_pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "reference_100_synthetic.json"


def reference():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("scale_numeric", [False, True])
@pytest.mark.parametrize("hour_onehot", [False, True])
def test_transform_one_is_exactly_the_batch_transform(scale_numeric, hour_onehot):
    rows = [adapt_to_sparkov_record(c["input"]) for c in reference()["cases"]]
    # Include unknown categories and both sides of a birthday boundary.
    rows += [
        {**rows[0], "dob": "1980-06-01", "trans_date_trans_time": date}
        for date in ("2020-05-31 23:59:59", "2020-06-01 00:00:00")
    ]
    rows.append({**rows[0], "category": "unknown-category", "state": "unknown-state"})
    pipeline = build_preprocessing_pipeline(scale_numeric, hour_onehot).fit(
        pd.DataFrame(rows[:50])
    )
    expected_batch = pipeline.transform(pd.DataFrame(rows))
    for index, record in enumerate(rows):
        actual = pipeline.transform_one(record)
        expected = pipeline.transform(pd.DataFrame([record]))[0]
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(actual, expected_batch[index])
        assert actual.dtype == expected.dtype


def test_reference_structure_and_counts():
    payload = reference()
    assert payload["synthetic_only"] is True
    assert payload["qualificatif"] == "synthétique, stratifié, non représentatif"
    assert payload["seed"] == 42 and payload["alpha"] == 0.02
    assert len(payload["cases"]) == 100
    counts = Counter()
    for case in payload["cases"]:
        assert set(case["input"]) == {
            "transaction_id",
            "trans_datetime",
            "amount",
            "category",
            "merch_lat",
            "merch_long",
            "customer",
        }
        assert set(case["input"]["customer"]) == {
            "dob",
            "gender",
            "state",
            "city_pop",
            "lat",
            "long",
        }
        expected = case["expected"]
        served = case["expected_serving"]
        assert served["fraud_probability"] == round(expected["raw_probability"], 4)
        assert expected["fraud_probability"] == round(expected["raw_probability"], 6)
        assert served["prediction_set"] == expected["prediction_set"]
        assert served["alpha"] == 0.02
        counts[str(served["prediction_set"])] += 1
    assert counts == {"[0]": 34, "[1]": 35, "[]": 31}
    assert dict(counts) == payload["reference_prediction_set_counts"]


@pytest.mark.parametrize("with_mean", [False, True])
@pytest.mark.parametrize("with_std", [False, True])
def test_fast_path_is_exact_with_scaler_and_without_dataframe(
    monkeypatch, with_mean, with_std
):
    rows = [adapt_to_sparkov_record(c["input"]) for c in reference()["cases"]]
    pipeline = build_preprocessing_pipeline(scale_numeric=True)
    pipeline.set_params(
        columns__numeric__with_mean=with_mean,
        columns__numeric__with_std=with_std,
    )
    pipeline.fit(pd.DataFrame(rows[:50]))
    scaler = pipeline.named_steps["columns"].named_transformers_["numeric"]
    assert scaler.with_mean == with_mean
    assert scaler.with_std == with_std
    expected = pipeline.transform(pd.DataFrame(rows))

    def forbidden(*args, **kwargs):
        pytest.fail("transform_one must keep its fast path")

    monkeypatch.setattr(pd, "DataFrame", forbidden)
    monkeypatch.setattr(pipeline, "transform", forbidden)
    monkeypatch.setattr(pipeline.named_steps["columns"], "transform", forbidden)
    for record, batch_row in zip(rows, expected, strict=True):
        actual = pipeline.transform_one(record)
        np.testing.assert_array_equal(actual, batch_row)
        assert actual.dtype == batch_row.dtype
        assert actual.tobytes() == batch_row.tobytes()
