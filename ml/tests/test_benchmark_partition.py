"""Disjonction Optuna/benchmark : donnees synthetiques uniquement."""

import numpy as np
import pandas as pd
import pytest
from benchmark.partition import assert_disjoint, partition_development
from pandas.testing import assert_frame_equal, assert_series_equal


@pytest.fixture
def development():
    X = pd.DataFrame(
        {
            "trans_date_trans_time": pd.date_range(
                "2019-01-01", periods=10, freq="h"
            ).repeat(2),
            "feature": np.arange(20),
        },
        index=np.arange(100, 120),
    )
    y = pd.Series([0, 1] * 10, index=X.index)
    X.attrs.update(zone="development", source="data/raw/fraudTrain.csv")
    y.attrs.update(X.attrs)
    return X, y


def test_disjoint_indices_dates_and_sizes(development):
    X, y = development
    left, right = partition_development(X, y)
    assert len(left) == 4 and len(right) == 16
    assert set(X.index[left]).isdisjoint(X.index[right])
    assert set(X.iloc[left]["trans_date_trans_time"]).isdisjoint(
        X.iloc[right]["trans_date_trans_time"]
    )
    assert (
        X.iloc[left]["trans_date_trans_time"].max()
        < X.iloc[right]["trans_date_trans_time"].min()
    )


def test_tied_timestamps_stay_on_same_side(development):
    X, y = development
    left, right = partition_development(X, y, 0.25)
    assert len(left) == 6
    assert_disjoint(X, left, right)


def test_source_can_be_unsorted_without_mutation(development):
    X, y = development
    X, y = X.iloc[::-1].copy(), y.iloc[::-1].copy()
    before_X, before_y = X.copy(), y.copy()
    left, right = partition_development(X, y)
    assert X.iloc[left]["trans_date_trans_time"].is_monotonic_increasing
    assert_disjoint(X, left, right)
    assert_frame_equal(X, before_X)
    assert_series_equal(y, before_y)


@pytest.mark.parametrize("fraction", [0, 1, -0.1, np.nan, np.inf, True, "0.2"])
def test_invalid_fraction(development, fraction):
    with pytest.raises(ValueError, match="fraction"):
        partition_development(*development, fraction)


def test_shared_timestamp_and_position_are_rejected(development):
    X, _ = development
    with pytest.raises(ValueError, match="Timestamps"):
        assert_disjoint(X, [0], [1])
    with pytest.raises(ValueError, match="Index"):
        assert_disjoint(X, [0], [0])


@pytest.mark.parametrize(
    "zone", ["probability_calibration", "conformal_calibration", "test"]
)
def test_reserved_zones_rejected(development, zone):
    X, y = development
    X.attrs["zone"] = zone
    with pytest.raises(ValueError, match="development"):
        partition_development(X, y)


def test_forbidden_source_rejected_before_partition(development):
    X, y = development
    X.attrs["source"] = "data/raw/not_training.csv"
    with pytest.raises(ValueError, match="Source interdite"):
        partition_development(X, y)


def test_all_equal_timestamps_reject_empty_output(development):
    X, y = development
    X["trans_date_trans_time"] = pd.Timestamp("2019-01-01")
    with pytest.raises(ValueError, match="vide"):
        partition_development(X, y)
