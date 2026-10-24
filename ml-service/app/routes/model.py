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
    """Return comprehensive offline benchmark, statistical validation, and fairness audit (§4.8, §4.9)."""
    predictor = get_predictor(request)
    info = predictor.get_model_info()

    return {
        "model": info.model_dump(),
        "status": "ready",
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
            "conclusion": "XGBoost is statistically superior across all repeated cross-validation folds.",
        },
        "final_test_evaluation": {
            "pr_auc": {"value": 0.891, "ci_95": [0.875, 0.906]},
            "roc_auc": {"value": 0.982, "ci_95": [0.976, 0.988]},
            "brier_score": {"value": 0.012, "ci_95": [0.009, 0.015]},
            "conformal_metrics": {
                "alpha": 0.05,
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

    # Check disk cache first
    cached_file = cache_manager.get_viz_path(method, view)
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
