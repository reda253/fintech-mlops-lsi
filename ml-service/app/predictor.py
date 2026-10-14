"""Model predictor implementation (Mock and MLflow abstractions)."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Literal

from app.metrics import (
    ML_FRAUD_PROBABILITY,
    ML_INFERENCE_DURATION_SECONDS,
    ML_MODEL_INFO,
    ML_MODEL_LOADED_TIMESTAMP_SECONDS,
    ML_PREDICTIONS_TOTAL,
    ML_UNCERTAINTY,
)
from app.schemas import (
    ModelInfo,
    ModelVersionInfo,
    PredictRequest,
    PredictResponse,
)

logger = logging.getLogger(__name__)


def map_prediction_set_label(prediction_set: list[int]) -> str:
    """Format prediction_set list into metric label: '0', '1', '01', or 'vide'."""
    if not prediction_set:
        return "vide"
    if prediction_set == [0]:
        return "0"
    if prediction_set == [1]:
        return "1"
    if sorted(prediction_set) == [0, 1]:
        return "01"
    return "autre"


class BasePredictor(ABC):
    """Abstract predictor interface."""

    @abstractmethod
    def warmup(self) -> None:
        """Run warm-up inference to prime caches and verify model readiness."""

    @abstractmethod
    def predict(self, request: PredictRequest) -> PredictResponse:
        """Execute inference on a transaction request."""

    @abstractmethod
    def get_model_info(self) -> ModelInfo:
        """Return metadata of currently active model."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Check whether predictor is initialized and ready to serve."""


class MockPredictor(BasePredictor):
    """Deterministic mock predictor for development and testing (§5.7).

    Rules:
    - amount > 500            -> [1] (BLOQUER), proba=0.92, uncertainty=FAIBLE
    - 200 <= amount <= 500    -> [0, 1] (REVUE), proba=0.45, uncertainty=ELEVEE
    - amount < 200            -> [0] (APPROUVER), proba=0.03, uncertainty=FAIBLE
    """

    def __init__(self, name: str = "fraud-detector", version: str = "mock"):
        self.name = name
        self.version = version
        self.algorithm = "heuristic-mock"
        self.alpha = 0.05
        self.loaded_at: datetime | None = None
        self._ready = False

    def warmup(self) -> None:
        logger.info("Executing mock predictor warmup...")
        self.loaded_at = datetime.now(UTC)
        self._ready = True
        ML_MODEL_INFO.labels(name=self.name, version=self.version).set(1.0)
        ML_MODEL_LOADED_TIMESTAMP_SECONDS.set(self.loaded_at.timestamp())
        logger.info("Mock predictor is ready.")

    def is_ready(self) -> bool:
        return self._ready

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(
            name=self.name,
            version=self.version,
            algorithm=self.algorithm,
            alpha=self.alpha,
            trained_at=self.loaded_at,
            git_commit="mock-dev",
            mode="mock",
        )

    def predict(self, request: PredictRequest) -> PredictResponse:
        start_time = time.perf_counter()

        amount = request.amount
        prediction: Literal[0, 1]
        prediction_set: list[Literal[0, 1]]
        uncertainty_level: Literal["FAIBLE", "ELEVEE"]
        fraud_probability: float
        uncertainty: float

        if amount > 500.0:
            prediction = 1
            prediction_set = [1]
            fraud_probability = 0.92
            uncertainty = 0.15
            uncertainty_level = "FAIBLE"
        elif amount >= 200.0:
            prediction = 0
            prediction_set = [0, 1]
            fraud_probability = 0.45
            uncertainty = 0.85
            uncertainty_level = "ELEVEE"
        else:
            prediction = 0
            prediction_set = [0]
            fraud_probability = 0.03
            uncertainty = 0.08
            uncertainty_level = "FAIBLE"

        elapsed_seconds = time.perf_counter() - start_time
        inference_ms = round(elapsed_seconds * 1000.0, 2)

        # Update metrics
        set_label = map_prediction_set_label(prediction_set)
        ML_INFERENCE_DURATION_SECONDS.labels(model_version=self.version).observe(elapsed_seconds)
        ML_PREDICTIONS_TOTAL.labels(model_version=self.version, prediction_set=set_label).inc()
        ML_FRAUD_PROBABILITY.observe(fraud_probability)
        ML_UNCERTAINTY.observe(uncertainty)

        return PredictResponse(
            transaction_id=request.transaction_id,
            prediction=prediction,
            fraud_probability=fraud_probability,
            prediction_set=prediction_set,
            uncertainty=uncertainty,
            uncertainty_level=uncertainty_level,
            alpha=self.alpha,
            model=ModelVersionInfo(name=self.name, version=self.version),
            inference_ms=inference_ms,
        )
