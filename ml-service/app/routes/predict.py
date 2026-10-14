"""Prediction endpoint (POST /predict)."""

from typing import Annotated
from uuid import UUID

from app.predictor import BasePredictor
from app.schemas import PredictRequest, PredictResponse
from fastapi import APIRouter, Header, HTTPException, Request, status

router = APIRouter(tags=["inference"])


def get_predictor(request: Request) -> BasePredictor:
    """Retrieve active predictor from application state."""
    predictor = getattr(request.app.state, "predictor", None)
    if predictor is None or not predictor.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded or predictor not ready",
        )
    return predictor


@router.post(
    "/predict",
    response_model=PredictResponse,
    summary="Predict one transaction (internal, risk-service only, never routed)",
    responses={
        200: {"description": "Prediction result"},
        422: {"description": "Invalid input"},
        503: {"description": "Model not loaded"},
    },
)
def predict(
    payload: PredictRequest,
    request: Request,
    x_correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-Id")] = None,
) -> PredictResponse:
    """Synchronous CPU prediction endpoint (§5.7).

    FastAPI automatically offloads synchronous def endpoints to its threadpool,
    ensuring CPU-intensive inferences don't block the async event loop.
    """
    predictor = get_predictor(request)
    return predictor.predict(payload)
