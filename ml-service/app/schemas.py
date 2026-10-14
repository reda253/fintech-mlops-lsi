"""Pydantic schemas matching contracts/ml-service.yaml."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

CategoryType = Literal[
    "entertainment",
    "food_dining",
    "gas_transport",
    "grocery_net",
    "grocery_pos",
    "health_fitness",
    "home",
    "kids_pets",
    "misc_net",
    "misc_pos",
    "personal_care",
    "shopping_net",
    "shopping_pos",
    "travel",
]


class CustomerInput(BaseModel):
    """Customer information nested in PredictRequest."""

    dob: date = Field(..., description="Customer date of birth")
    gender: Literal["M", "F"] = Field(..., description="Customer gender")
    city_pop: Annotated[int, Field(ge=0, description="City population")]
    lat: Annotated[float, Field(ge=-90.0, le=90.0, description="Customer latitude")]
    long: Annotated[float, Field(ge=-180.0, le=180.0, description="Customer longitude")]
    state: str = Field(..., description="US State or region code")


class PredictRequest(BaseModel):
    """Transaction inference request from risk-service."""

    transaction_id: UUID = Field(..., description="Unique transaction UUID")
    trans_datetime: datetime = Field(..., description="Transaction ISO-8601 local timestamp")
    amount: Annotated[float, Field(gt=0, description="Transaction amount in currency units")]
    category: CategoryType = Field(..., description="Merchant category")
    merch_lat: Annotated[float, Field(ge=-90.0, le=90.0, description="Merchant latitude")]
    merch_long: Annotated[float, Field(ge=-180.0, le=180.0, description="Merchant longitude")]
    customer: CustomerInput = Field(..., description="Customer profile")


class ModelVersionInfo(BaseModel):
    """Model identification metadata."""

    name: str = Field(default="fraud-detector", examples=["fraud-detector"])
    version: str = Field(default="mock", examples=["8"])


class PredictResponse(BaseModel):
    """Inference response returned to risk-service."""

    transaction_id: UUID
    prediction: Literal[0, 1]
    fraud_probability: Annotated[float, Field(ge=0.0, le=1.0)]
    prediction_set: list[Literal[0, 1]] = Field(..., max_length=2)
    uncertainty: Annotated[float, Field(ge=0.0, le=1.0)]
    uncertainty_level: Literal["FAIBLE", "ELEVEE"]
    alpha: float = Field(default=0.05, examples=[0.05])
    model: ModelVersionInfo
    inference_ms: float


class ModelInfo(BaseModel):
    """Metadata regarding currently deployed model."""

    name: str = "fraud-detector"
    version: str = "mock"
    algorithm: str = "heuristic-mock"
    alpha: float = 0.05
    trained_at: datetime | None = None
    git_commit: str = "unknown"
    mode: Literal["real", "mock"] = "mock"


class ProjectionPoint(BaseModel):
    """Single point for visualization."""

    x: float
    y: float
    label: str | None = None
    is_fraud: int | None = None


class Projection(BaseModel):
    """Dimensionality reduction projection response."""

    method: str
    view: str
    model_version: str
    warning: str = "t-SNE/UMAP distances between groups are not meaningful"
    points: list[ProjectionPoint] = Field(default_factory=list)
