"""Tests for simulator replayer and feedback scheduler."""

from pathlib import Path

import pandas as pd
import pytest
from app.feedback import FeedbackScheduler
from app.replayer import load_and_sort_transactions


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Create a temporary CSV file with Sparkov format."""
    file_path = tmp_path / "test_transactions.csv"
    data = {
        "trans_num": ["t3", "t1", "t2"],
        "cc_num": ["1234567812345678", "8765432187654321", "1111222233334444"],
        "trans_date_trans_time": [
            "2020-07-14 05:00:00",
            "2020-07-14 01:00:00",
            "2020-07-14 03:00:00",
        ],
        "amt": [520.0, 45.0, 250.0],
        "category": ["shopping_net", "grocery_pos", "entertainment"],
        "merchant": ["fraud_Kirlin and Sons", "fraud_Rippin-Considine", "fraud_Bauch-Wuckert"],
        "merch_lat": [40.71, 34.05, 41.87],
        "merch_long": [-74.01, -118.24, -87.62],
        "is_fraud": [1, 0, 0],
    }
    df = pd.DataFrame(data)
    df.to_csv(file_path, index=False)
    return file_path


def test_load_and_sort_transactions_chronological(sample_csv):
    records = load_and_sort_transactions(sample_csv)
    assert len(records) == 3

    # Check chronological ordering: t1 (01:00), t2 (03:00), t3 (05:00)
    assert records[0]["trans_num"] == "t1"
    assert records[1]["trans_num"] == "t2"
    assert records[2]["trans_num"] == "t3"

    # Check payload keys matching CreateTransactionRequest
    payload = records[0]["payload"]
    assert payload["transNum"] == "t1"
    assert payload["cardNumber"] == "8765432187654321"
    assert payload["amount"] == 45.0
    assert payload["category"] == "grocery_pos"
    assert payload["merchant"] == "fraud_Rippin-Considine"
    assert payload["transDateTime"] == "2020-07-14T01:00:00"


def test_replayer_missing_columns(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    pd.DataFrame({"trans_num": ["t1"]}).to_csv(bad_csv, index=False)

    with pytest.raises(ValueError, match="Missing required Sparkov columns"):
        load_and_sort_transactions(bad_csv)


def test_feedback_scheduler():
    scheduler = FeedbackScheduler(default_delay_seconds=10.0)
    due_t1 = scheduler.schedule("t1", is_fraud=False, delay_seconds=10.0)
    due_t2 = scheduler.schedule("t2", is_fraud=True, delay_seconds=20.0)

    assert scheduler.pending_count == 2

    # Nothing due at t = due_t1 - 1
    assert scheduler.get_due_feedbacks(now=due_t1 - 1.0) == []

    # t1 due at due_t1
    due_items = scheduler.get_due_feedbacks(now=due_t1)
    assert len(due_items) == 1
    assert due_items[0]["transNum"] == "t1"
    assert due_items[0]["isFraud"] is False
    assert scheduler.pending_count == 1

    # t2 due at due_t2
    due_items2 = scheduler.get_due_feedbacks(now=due_t2)
    assert len(due_items2) == 1
    assert due_items2[0]["transNum"] == "t2"
    assert due_items2[0]["isFraud"] is True
    assert scheduler.pending_count == 0
