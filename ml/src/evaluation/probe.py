"""Fixed identity probe used to bind the served model to the frozen candidate.

The probe is deliberately tiny and deterministic: it only needs to separate two
different classifiers, not to estimate performance. Both the frozen D44 joblib
and the model served by MLflow are scored on exactly these rows.
"""

from __future__ import annotations

import pandas as pd

PROBE_ROWS = (
    {
        "trans_date_trans_time": "2020-06-01 12:00:00",
        "dob": "2000-06-01",
        "amt": 5.0,
        "category": "shopping_net",
        "gender": "F",
        "state": "NY",
        "city_pop": 50000,
        "lat": 40.0,
        "long": -73.0,
        "merch_lat": 40.1,
        "merch_long": -73.1,
    },
    {
        "trans_date_trans_time": "2020-06-02 03:15:00",
        "dob": "1980-01-01",
        "amt": 25.0,
        "category": "grocery_pos",
        "gender": "M",
        "state": "CA",
        "city_pop": 120000,
        "lat": 34.05,
        "long": -118.24,
        "merch_lat": 34.15,
        "merch_long": -118.34,
    },
    {
        "trans_date_trans_time": "2020-06-03 22:45:00",
        "dob": "1960-01-01",
        "amt": 500.0,
        "category": "misc_net",
        "gender": "F",
        "state": "TX",
        "city_pop": 8000,
        "lat": 29.76,
        "long": -95.37,
        "merch_lat": 29.86,
        "merch_long": -95.47,
    },
    {
        "trans_date_trans_time": "2020-06-04 07:30:00",
        "dob": "1950-01-01",
        "amt": 900.0,
        "category": "travel",
        "gender": "M",
        "state": "FL",
        "city_pop": 250000,
        "lat": 25.76,
        "long": -80.19,
        "merch_lat": 25.86,
        "merch_long": -80.29,
    },
    {
        "trans_date_trans_time": "2020-06-05 18:05:00",
        "dob": "1995-09-12",
        "amt": 120.0,
        "category": "shopping_pos",
        "gender": "F",
        "state": "WA",
        "city_pop": 60000,
        "lat": 47.61,
        "long": -122.33,
        "merch_lat": 47.71,
        "merch_long": -122.43,
    },
    {
        "trans_date_trans_time": "2020-06-06 11:20:00",
        "dob": "1975-04-20",
        "amt": 42.5,
        "category": "entertainment",
        "gender": "M",
        "state": "IL",
        "city_pop": 15000,
        "lat": 41.88,
        "long": -87.63,
        "merch_lat": 41.98,
        "merch_long": -87.73,
    },
    {
        "trans_date_trans_time": "2020-06-07 02:10:00",
        "dob": "2001-11-30",
        "amt": 310.0,
        "category": "gas_transport",
        "gender": "F",
        "state": "MA",
        "city_pop": 3000,
        "lat": 42.36,
        "long": -71.06,
        "merch_lat": 42.46,
        "merch_long": -71.16,
    },
    {
        "trans_date_trans_time": "2020-06-08 16:40:00",
        "dob": "1970-07-07",
        "amt": 75.0,
        "category": "food_dining",
        "gender": "M",
        "state": "GA",
        "city_pop": 95000,
        "lat": 33.75,
        "long": -84.39,
        "merch_lat": 33.85,
        "merch_long": -84.49,
    },
)


def identity_probe() -> pd.DataFrame:
    """Return a fresh copy of the fixed probe frame."""

    return pd.DataFrame([dict(row) for row in PROBE_ROWS])
