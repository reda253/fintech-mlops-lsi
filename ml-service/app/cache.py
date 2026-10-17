"""Local node model caching management (§6.10, §5.7).

Stores downloaded MLflow models on node disk (hostPath volume in Kubernetes),
enabling pods that restart on the same worker node to recover instantly without
depending on MLflow network availability.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelCacheManager:
    """Manages model artifacts in local hostPath disk cache."""

    def __init__(self, cache_dir: str | Path = "/tmp/model-cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_model_path(self, model_name: str, version: str) -> Path:
        """Return designated local storage directory for a specific model version."""
        return self.cache_dir / "models" / model_name / str(version)

    def is_cached(self, model_name: str, version: str) -> bool:
        """Check if model artifact exists locally."""
        model_path = self.get_model_path(model_name, version)
        return model_path.is_dir() and any(model_path.iterdir())

    def get_viz_path(self, method: str, view: str) -> Path:
        """Return path to cached visualization JSON file."""
        return self.cache_dir / "viz" / f"{method}_{view}.json"
