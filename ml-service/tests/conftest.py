"""Test fixtures for ml-service."""

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Test client wrapping the FastAPI application."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_payload():
    """Valid Sparkov transaction payload matching PredictRequest contract."""
    return {
        "transaction_id": "7f3c9a1e-2b4d-4c8e-9f1a-0d5e6b7c8a9f",
        "trans_datetime": "2020-07-14T02:13:45",
        "amount": 150.00,
        "category": "shopping_net",
        "merch_lat": 40.71,
        "merch_long": -74.01,
        "customer": {
            "dob": "1962-05-18",
            "gender": "F",
            "city_pop": 1577385,
            "lat": 40.65,
            "long": -73.95,
            "state": "NY",
        },
    }
