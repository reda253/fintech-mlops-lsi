"""Transaction data replayer loading Sparkov test set (§9.3)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def load_and_sort_transactions(csv_path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Load Sparkov transactions, sort chronologically, and format as API payloads."""
    logger.info("Reading transactions from %s...", csv_path)
    df = pd.read_csv(csv_path)

    # Required columns check
    required_cols = [
        "trans_num",
        "cc_num",
        "trans_date_trans_time",
        "amt",
        "category",
        "merchant",
        "merch_lat",
        "merch_long",
        "is_fraud",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required Sparkov columns in CSV: {missing}")

    df["trans_date_trans_time"] = pd.to_datetime(df["trans_date_trans_time"])
    df = df.sort_values("trans_date_trans_time").reset_index(drop=True)

    if limit is not None and limit > 0:
        df = df.iloc[:limit]

    records = []
    for row in df.itertuples(index=False):
        trans_dict = {
            "payload": {
                "transNum": str(row.trans_num),
                "cardNumber": str(row.cc_num),
                "transDateTime": row.trans_date_trans_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "amount": float(row.amt),
                "category": str(row.category),
                "merchant": str(row.merchant),
                "merchLat": float(row.merch_lat),
                "merchLong": float(row.merch_long),
            },
            "is_fraud": bool(row.is_fraud == 1),
            "trans_num": str(row.trans_num),
        }
        records.append(trans_dict)

    logger.info("Prepared %d transactions for chronological replay.", len(records))
    return records
