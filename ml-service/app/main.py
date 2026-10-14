"""Main FastAPI application for ml-service."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import settings
from app.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    ML_INPUT_VALIDATION_ERRORS_TOTAL,
)
from app.predictor import MockPredictor
from app.routes.health import router as health_router
from app.routes.model import router as model_router
from app.routes.predict import router as predict_router

# Configure root logger
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ml-service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan managing model loading and warm-up."""
    logger.info("Starting ml-service (mode=%s)...", settings.model_mode)

    if settings.model_mode == "mock":
        predictor = MockPredictor(name="fraud-detector", version="mock")
    else:
        # Placeholder for MLflow model loader (Deliverable C / S9-S10)
        logger.warning("Real model mode requested; falling back to mock predictor until registry is connected.")
        predictor = MockPredictor(name="fraud-detector", version="mock")

    predictor.warmup()
    app.state.predictor = predictor
    logger.info("ml-service initialization complete.")

    yield

    logger.info("Shutting down ml-service.")


app = FastAPI(
    title="ml-service",
    version="1.0.0-draft",
    description="FastAPI service serving real-time fraud predictions and conformal uncertainty sets.",
    lifespan=lifespan,
)


@app.middleware("http")
async def metrics_and_logging_middleware(request: Request, call_next) -> Response:
    """Track request latency, HTTP status counters, and trace correlation IDs."""
    start_time = time.perf_counter()

    # Correlation ID propagation
    corr_id = request.headers.get("X-Correlation-Id") or str(uuid4())

    try:
        response = await call_next(request)
    except Exception:
        duration = time.perf_counter() - start_time
        endpoint = request.url.path
        HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint=endpoint, status=500).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, endpoint=endpoint).observe(duration)
        logger.exception("[%s] Unhandled server error", corr_id)
        raise

    duration = time.perf_counter() - start_time
    endpoint = request.url.path
    status_code = response.status_code

    HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint=endpoint, status=status_code).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, endpoint=endpoint).observe(duration)

    response.headers["X-Correlation-Id"] = corr_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle 422 input validation errors and increment Prometheus metric (§5.8)."""
    ML_INPUT_VALIDATION_ERRORS_TOTAL.inc()
    logger.warning("Input validation error on %s: %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": exc.errors()},
    )


@app.get("/metrics", summary="Prometheus scrape endpoint", include_in_schema=False)
def metrics() -> Response:
    """Expose Prometheus metrics directly (not routed through API gateway)."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Register API routers
app.include_router(predict_router)
app.include_router(health_router)
app.include_router(model_router)
