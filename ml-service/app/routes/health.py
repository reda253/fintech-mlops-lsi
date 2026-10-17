"""Health check endpoints (/health/live, /health/ready)."""

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Liveness, the process answers")
def health_live():
    """Liveness probe: returns 200 as long as uvicorn process responds."""
    return {"status": "alive"}


@router.get(
    "/health/ready",
    summary="Readiness, model loaded and warm-up prediction succeeded",
    responses={
        200: {"description": "Ready"},
        503: {"description": "Not ready"},
    },
)
def health_ready(request: Request):
    """Readiness probe: returns 200 only after model is loaded and primed."""
    predictor = getattr(request.app.state, "predictor", None)
    if predictor is None or not predictor.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not ready or warm-up in progress",
        )
    return {"status": "ready"}
