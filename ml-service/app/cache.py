"""Local node model caching management (§6.10, §5.7).

Stores downloaded MLflow models on node disk (hostPath volume in Kubernetes),
enabling pods that restart on the same worker node to recover instantly without
depending on MLflow network availability.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

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

    def get_viz_path(self, method: str, view: str, version: str | None = None) -> Path:
        """Return path to cached visualization JSON file (version-scoped if given)."""
        suffix = f"_v{version}" if version not in (None, "", "unknown") else ""
        return self.cache_dir / "viz" / f"{method}_{view}{suffix}.json"

    def write_viz(
        self,
        method: str,
        view: str,
        data: dict[str, Any],
        version: str | None = None,
    ) -> Path:
        """Persist a projection JSON so later requests skip the registry download."""
        path = self.get_viz_path(method, view, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            json.dump(data, stream)
        return path
