"""Model predictor implementation (Mock and MLflow abstractions)."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import HTTPException, status

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


class RealPredictor(BasePredictor):
    """Production predictor loading packaged MLflow pyfunc model (§5.3, §5.7)."""

    def __init__(
        self,
        model_uri: str = "",
        cache_dir: str = "/tmp/model-cache",
        name: str = "fraud-detector",
        version: str = "1",
        model_instance: Any = None,
    ):
        self.model_uri = model_uri
        self.cache_dir = cache_dir
        self.name = name
        self.version = version
        self.model = model_instance
        self.alpha = 0.05
        self.loaded_at: datetime | None = None
        self._ready = False

    def warmup(self) -> None:
        """Load model weights and run warm-up inference."""
        logger.info("Initializing RealPredictor (uri=%s)...", self.model_uri)
        if self.model is None and self.model_uri:
            try:
                import mlflow.pyfunc

                self.model = mlflow.pyfunc.load_model(self.model_uri)
                logger.info("Loaded pyfunc model from %s", self.model_uri)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load model from %s (%s); real predictor disabled.", self.model_uri, exc)

        # Fail-safe invariant: do NOT mark ready if model is not loaded
        if self.model is None:
            logger.error("RealPredictor warmup failed: no model loaded. Predictor is NOT ready.")
            self._ready = False
            return

        # Run warm-up inference
        sample_record = {
            "trans_datetime": "2026-10-24 12:00:00",
            "amount": 100.0,
            "category": "shopping_net",
            "merch_lat": 40.71,
            "merch_long": -74.01,
            "customer": {
                "dob": "1980-01-01",
                "gender": "F",
                "city_pop": 50000,
                "lat": 40.70,
                "long": -74.00,
                "state": "NY",
            },
        }
        try:
            if hasattr(self.model, "predict_one"):
                self.model.predict_one(sample_record)
            elif hasattr(self.model, "predict"):
                self.model.predict([sample_record])
            logger.info("Warm-up prediction completed successfully.")
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
            logger.error("Warm-up inference failed: %s; real predictor is NOT ready.", exc)
            self._ready = False
            return

        self.loaded_at = datetime.now(UTC)
        self._ready = True
        ML_MODEL_INFO.labels(name=self.name, version=self.version).set(1.0)
        ML_MODEL_LOADED_TIMESTAMP_SECONDS.set(self.loaded_at.timestamp())

    def is_ready(self) -> bool:
        """Return True only if initialized AND a valid model is loaded."""
        return bool(self._ready and self.model is not None)

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(
            name=self.name,
            version=self.version,
            algorithm="xgboost-calibrated",
            alpha=self.alpha,
            trained_at=self.loaded_at,
            git_commit="prod",
            mode="real",
        )

    def predict(self, request: PredictRequest) -> PredictResponse:
        # Fail-safe invariant: return 503 if no model is loaded
        if self.model is None:
            logger.error("Predict called on RealPredictor without an active model. Raising 503.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Model not loaded or unavailable",
            )

        start_time = time.perf_counter()

        trans_dt = request.trans_datetime
        trans_dt_str = (
            trans_dt.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(trans_dt, "strftime")
            else str(trans_dt)
        )

        record = {
            "transaction_id": str(request.transaction_id),
            "trans_datetime": trans_dt_str,
            "amount": request.amount,
            "category": request.category,
            "merch_lat": request.merch_lat,
            "merch_long": request.merch_long,
            "customer": request.customer.model_dump(),
        }

        try:
            if hasattr(self.model, "predict_one"):
                out = self.model.predict_one(record)
            else:
                out = self.model.predict([record])[0]

            prediction = int(out.get("prediction", 0))
            fraud_proba = float(out.get("fraud_probability", 0.5))

            raw_set = out.get("prediction_set")
            # Fail-safe invariant: NEVER default to [0] on missing or malformed prediction sets!
            if raw_set is None or not raw_set:
                logger.warning("Missing or empty prediction_set in model output; defaulting to [0, 1] (REVUE).")
                pred_set = [0, 1]
                uncertainty = 1.0
                uncertainty_level = "ELEVEE"
            else:
                pred_set = [int(v) for v in raw_set]
                uncertainty = float(out.get("uncertainty", 1.0))
                uncertainty_level = str(out.get("uncertainty_level", "ELEVEE"))
        except (KeyError, ValueError, TypeError, AttributeError, IndexError) as exc:
            logger.error("Model prediction failed: %s; falling back to safe REVUE evaluation.", exc)
            prediction = 0
            fraud_proba = 0.5
            pred_set = [0, 1]
            uncertainty = 1.0
            uncertainty_level = "ELEVEE"

        elapsed_seconds = time.perf_counter() - start_time
        inference_ms = round(elapsed_seconds * 1000.0, 2)

        set_label = map_prediction_set_label(pred_set)
        ML_INFERENCE_DURATION_SECONDS.labels(model_version=self.version).observe(elapsed_seconds)
        ML_PREDICTIONS_TOTAL.labels(model_version=self.version, prediction_set=set_label).inc()
        ML_FRAUD_PROBABILITY.observe(fraud_proba)
        ML_UNCERTAINTY.observe(uncertainty)

        return PredictResponse(
            transaction_id=request.transaction_id,
            prediction=prediction,  # type: ignore[arg-type]
            fraud_probability=fraud_proba,
            prediction_set=pred_set,  # type: ignore[arg-type]
            uncertainty=uncertainty,
            uncertainty_level=uncertainty_level,  # type: ignore[arg-type]
            alpha=self.alpha,
            model=ModelVersionInfo(name=self.name, version=self.version),
            inference_ms=inference_ms,
        )
