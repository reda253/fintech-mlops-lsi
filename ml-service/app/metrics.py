"""Prometheus metrics definition for ml-service (§5.8)."""

from prometheus_client import Counter, Gauge, Histogram

# HTTP metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total count of HTTP requests handled by the service.",
    ["method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# ML operational & inference metrics
ML_INFERENCE_DURATION_SECONDS = Histogram(
    "ml_inference_duration_seconds",
    "Time taken strictly by ML prediction pipeline in seconds.",
    ["model_version"],
    buckets=[0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5],
)

ML_PREDICTIONS_TOTAL = Counter(
    "ml_predictions_total",
    "Total ML predictions grouped by model version and conformal prediction set.",
    ["model_version", "prediction_set"],
)

ML_FRAUD_PROBABILITY = Histogram(
    "ml_fraud_probability",
    "Distribution of calibrated fraud scores (drift detection).",
    buckets=[0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.98, 1.0],
)

ML_UNCERTAINTY = Histogram(
    "ml_uncertainty",
    "Distribution of model uncertainty values.",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

ML_INPUT_VALIDATION_ERRORS_TOTAL = Counter(
    "ml_input_validation_errors_total",
    "Total count of invalid inputs rejected with 422.",
)

ML_MODEL_INFO = Gauge(
    "ml_model_info",
    "Information about currently active model in production (always 1).",
    ["name", "version"],
)

ML_MODEL_LOADED_TIMESTAMP_SECONDS = Gauge(
    "ml_model_loaded_timestamp_seconds",
    "Epoch timestamp when model was loaded into service.",
)
