"""Model metadata, performance, and visualization endpoints."""

import json
import logging
from pathlib import Path
from typing import Any, Literal

from app.cache import ModelCacheManager
from app.predictor import BasePredictor
from app.schemas import ModelInfo, Projection, ProjectionPoint
from fastapi import APIRouter, HTTPException, Query, Request, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ml", tags=["model"])
cache_manager = ModelCacheManager()


def get_predictor(request: Request) -> BasePredictor:
    predictor = getattr(request.app.state, "predictor", None)
    if predictor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Predictor not initialized",
        )
    return predictor


@router.get("/model", response_model=ModelInfo, summary="Model in production (ADMIN, ANALYSTE via gateway)")
def get_model_info(request: Request) -> ModelInfo:
    """Return model version, algorithm, alpha, and runtime information."""
    predictor = get_predictor(request)
    return predictor.get_model_info()


@router.get("/performance", summary="Offline metrics (benchmark, statistical tests, final test with CI, fairness)")
def get_performance(request: Request) -> dict[str, Any]:
    """Return offline evidence for the served version.

    In real mode the final-test block is read from the MLflow run attached to
    the served model version (or its pipeline parent). If that run has no
    evaluation metrics, the endpoint says ``unavailable`` instead of showing
    invented numbers. Mock mode is explicitly labelled ``demo``.
    """

    predictor = get_predictor(request)
    info = predictor.get_model_info()

    if info.mode != "real":
        return {
            "model": info.model_dump(),
            "status": "demo",
            "source": "demo",
            "detail": "Mock mode: values below are illustrative, not measured.",
            **_demo_performance(info),
        }

    measured = _performance_from_registry(info)
    if measured is None:
        return {
            "model": info.model_dump(),
            "status": "unavailable",
            "source": "none",
            "detail": (
                "No evaluation metrics are attached to the served MLflow run. "
                "Run the pipeline evaluation step or query the benchmark report."
            ),
            "benchmark": None,
            "statistical_validation": None,
            "final_test_evaluation": None,
            "fairness_audit": None,
        }

    return {
        "model": info.model_dump(),
        "status": "ready",
        "source": "mlflow_run",
        "detail": "Metrics read from the served MLflow run.",
        "benchmark": None,
        "statistical_validation": None,
        "final_test_evaluation": measured["final_test_evaluation"],
        "fairness_audit": None,
        "run_id": measured["run_id"],
        "run_tags": measured["tags"],
    }


def _demo_performance(info: Any) -> dict[str, Any]:
    """Illustrative benchmark payload used only when ``MODEL_MODE=mock``."""

    return {
        "benchmark": {
            "evaluation_metric": "pr_auc",
            "cross_validation": "10x5_folds",
            "selected_champion": "XGBoost",
            "models": [
                {"name": "LogisticRegression", "pr_auc": 0.724, "roc_auc": 0.912, "brier_score": 0.038, "inference_p95_ms": 1.2, "rank": 5},
                {"name": "MultiLayerPerceptron", "pr_auc": 0.812, "roc_auc": 0.954, "brier_score": 0.024, "inference_p95_ms": 6.8, "rank": 4},
                {"name": "RandomForest", "pr_auc": 0.846, "roc_auc": 0.968, "brier_score": 0.019, "inference_p95_ms": 14.1, "rank": 3},
                {"name": "SVM", "pr_auc": 0.878, "roc_auc": 0.979, "brier_score": 0.014, "inference_p95_ms": 3.9, "rank": 2},
                {"name": "XGBoost", "pr_auc": 0.894, "roc_auc": 0.984, "brier_score": 0.011, "inference_p95_ms": 4.2, "rank": 1},
            ],
        },
        "statistical_validation": {
            "friedman_test": {"statistic": 36.8, "p_value": 1.8e-7, "null_hypothesis_rejected": True},
            "holm_bonferroni_correction": [
                {"comparison": "XGBoost vs LogisticRegression", "p_value": 0.0001, "adjusted_alpha": 0.0125, "significant": True},
                {"comparison": "XGBoost vs MultiLayerPerceptron", "p_value": 0.0012, "adjusted_alpha": 0.0167, "significant": True},
                {"comparison": "XGBoost vs RandomForest", "p_value": 0.0084, "adjusted_alpha": 0.025, "significant": True},
                {"comparison": "XGBoost vs SVM", "p_value": 0.032, "adjusted_alpha": 0.05, "significant": True},
            ],
            "conclusion": "Illustrative mock values: XGBoost ranks first.",
        },
        "final_test_evaluation": {
            "pr_auc": {"value": 0.891, "ci_95": [0.875, 0.906]},
            "roc_auc": {"value": 0.982, "ci_95": [0.976, 0.988]},
            "brier_score": {"value": 0.012, "ci_95": [0.009, 0.015]},
            "conformal_metrics": {
                "alpha": info.alpha,
                "coverage_legit": 0.958,
                "coverage_fraud": 0.952,
                "review_rate": 0.018,
                "automation_rate": 0.982,
            },
        },
        "fairness_audit": {
            "protected_attributes": ["gender", "age"],
            "gender_parity": [
                {"group": "F", "recall": 0.885, "fpr": 0.008, "review_rate": 0.017},
                {"group": "M", "recall": 0.882, "fpr": 0.008, "review_rate": 0.018},
            ],
            "disparate_impact_ratio": 0.992,
            "age_groups": [
                {"band": "18-30", "recall": 0.881, "fpr": 0.007},
                {"band": "31-50", "recall": 0.886, "fpr": 0.008},
                {"band": "51-70", "recall": 0.884, "fpr": 0.008},
                {"band": "70+", "recall": 0.880, "fpr": 0.009},
            ],
        },
    }


_EVALUATION_METRICS = (
    "pr_auc",
    "roc_auc",
    "brier_score",
    "conformal_coverage",
    "conformal_coverage_legit",
    "conformal_coverage_fraud",
    "review_rate",
    "automation_rate",
    "auto_error_rate",
    "latency_p95_sec",
)


def _model_version(info: Any) -> Any:
    """Resolve the served version or alias to an MLflow ModelVersion."""

    from mlflow.tracking import MlflowClient

    client = MlflowClient()
    if str(info.version).isdigit():
        return client.get_model_version(info.name, str(info.version))
    return client.get_model_version_by_alias(info.name, str(info.version))


def _run_evaluation_metrics(client: Any, run_id: str) -> tuple[dict[str, float], dict[str, str], str]:
    """Read metrics from a run, following ``mlflow.parentRunId`` once."""

    run = client.get_run(run_id)
    metrics = dict(run.data.metrics)
    tags = dict(run.data.tags)
    if not any(key in metrics for key in _EVALUATION_METRICS):
        parent_id = tags.get("mlflow.parentRunId")
        if parent_id:
            parent = client.get_run(parent_id)
            metrics = dict(parent.data.metrics)
            tags = {**parent.data.tags, **tags}
            run_id = parent_id
    return metrics, tags, run_id


def _performance_from_registry(info: Any) -> dict[str, Any] | None:
    """Build the final-test block from the served version's MLflow run."""

    try:
        from mlflow.tracking import MlflowClient

        client = MlflowClient()
        version = _model_version(info)
        metrics, tags, run_id = _run_evaluation_metrics(client, version.run_id)
    except Exception as exc:  # noqa: BLE001 - performance is best effort
        logger.warning("Unable to read performance from MLflow: %s", exc)
        return None

    if not any(key in metrics for key in _EVALUATION_METRICS):
        return None

    return {
        "run_id": run_id,
        "tags": {
            key: tags[key]
            for key in ("git_commit", "data_sha256", "calibration_method", "status")
            if key in tags
        },
        "final_test_evaluation": {
            "pr_auc": {"value": metrics.get("pr_auc")},
            "roc_auc": {"value": metrics.get("roc_auc")},
            "brier_score": {"value": metrics.get("brier_score")},
            "conformal_metrics": {
                "alpha": metrics.get("alpha", info.alpha),
                "coverage_legit": metrics.get("conformal_coverage_legit"),
                "coverage_fraud": metrics.get("conformal_coverage_fraud"),
                "coverage_global": metrics.get("conformal_coverage"),
                "review_rate": metrics.get("review_rate"),
                "automation_rate": metrics.get("automation_rate"),
                "auto_error_rate": metrics.get("auto_error_rate"),
            },
            "latency_p95_sec": metrics.get("latency_p95_sec"),
            "n_test": metrics.get("n_test"),
            "n_test_fraud": metrics.get("n_test_fraud"),
        },
    }


def _download_viz_from_registry(
    predictor: BasePredictor,
    method: str,
    view: str,
) -> dict[str, Any] | None:
    """Download ``viz/<method>_<view>.json`` from the deployed model version run."""

    info = predictor.get_model_info()
    if info.mode != "real":
        return None
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        client = MlflowClient()
        if str(info.version).isdigit():
            version = client.get_model_version(info.name, str(info.version))
        else:
            version = client.get_model_version_by_alias(info.name, str(info.version))

        local_path = mlflow.artifacts.download_artifacts(
            run_id=version.run_id,
            artifact_path=f"viz/{method}_{view}.json",
            dst_path=str(cache_manager.cache_dir / "downloads" / str(info.version)),
        )
        with Path(local_path).open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        cache_manager.write_viz(method, view, data, version=info.version)
        return data
    except Exception as exc:  # noqa: BLE001 - visualization is best effort
        logger.debug("Unable to download %s_%s viz from MLflow: %s", method, view, exc)
        return None


@router.get(
    "/viz/{method}",
    response_model=Projection,
    summary="Projection points for the React dashboard",
    responses={
        200: {"description": "Points"},
        404: {"description": "Unknown method or view"},
    },
)
def get_visualizations(
    method: Literal["pca", "tsne", "umap"],
    view: Literal["class", "cluster", "outlier", "error", "uncertainty"] = Query(
        ..., description="Visualization facet view"
    ),
    request: Request = None,  # type: ignore[assignment]
) -> Projection:
    """Return 2D projected dataset points for frontend exploration."""
    allowed_methods = {"pca", "tsne", "umap"}
    allowed_views = {"class", "cluster", "outlier", "error", "uncertainty"}

    if method not in allowed_methods or view not in allowed_views:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown method '{method}' or view '{view}'",
        )

    predictor = get_predictor(request)
    info = predictor.get_model_info()

    # Check the version-scoped disk cache first.
    cached_file = cache_manager.get_viz_path(method, view, info.version)
    if cached_file.is_file():
        try:
            with cached_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return Projection(**data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Failed reading cached projection file %s: %s", cached_file, exc)

    # Alternate check in project data cache
    alt_cached_file = Path("cache") / "viz" / f"{method}_{view}.json"
    if alt_cached_file.is_file():
        try:
            with alt_cached_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return Projection(**data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Failed reading alternate cached projection file %s: %s", alt_cached_file, exc)

    # Cache miss: fetch the artifacts attached to the registered model version.
    registry_data = _download_viz_from_registry(predictor, method, view)
    if registry_data is not None:
        return Projection(**registry_data)

    # Fallback to generated demo points
    demo_points = [
        ProjectionPoint(x=1.2, y=0.5, label="LEGIT", is_fraud=0),
        ProjectionPoint(x=-2.1, y=3.4, label="FRAUD", is_fraud=1),
        ProjectionPoint(x=0.4, y=-1.1, label="LEGIT", is_fraud=0),
        ProjectionPoint(x=-1.8, y=2.9, label="FRAUD", is_fraud=1),
    ]

    return Projection(
        method=method,
        view=view,
        model_version=info.version,
        warning="t-SNE/UMAP distances between groups are not meaningful",
        points=demo_points,
    )
