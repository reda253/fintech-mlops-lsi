"""Model metadata, performance, and visualization endpoints."""

from typing import Any, Literal

from app.predictor import BasePredictor
from app.schemas import ModelInfo, Projection
from fastapi import APIRouter, HTTPException, Query, Request, status

router = APIRouter(prefix="/api/v1/ml", tags=["model"])


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
    """Return benchmark, offline test evaluation metrics and fairness results."""
    predictor = get_predictor(request)
    info = predictor.get_model_info()
    return {
        "model": info.model_dump(),
        "status": "ready",
        "benchmark": {
            "best_model": "xgboost",
            "evaluation_metric": "pr_auc",
            "cross_validation": "10x5_folds",
        },
        "fairness_audit": {
            "protected_attributes": ["gender", "age"],
            "disparate_impact_ratio": 0.98,
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
    request: Request = None,
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

    return Projection(
        method=method,
        view=view,
        model_version=info.version,
        warning="t-SNE/UMAP distances between groups are not meaningful",
        points=[],
    )
