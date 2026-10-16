"""CI Smoke Pipeline runner executing on 1% / synthetic sample with local MLflow (§5.6).

Usage:
    python -m ml.src.pipeline.smoke
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

from ml.src.pipeline.run import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SMOKE] %(message)s")
logger = logging.getLogger("ml-smoke")


def run_smoke() -> bool:
    """Execute smoke pipeline in an isolated temporary MLflow file store."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "mlflow.db"
        tracking_uri = f"sqlite:///{db_path.as_posix()}"
        logger.info("Running smoke pipeline with isolated tracking store: %s", tracking_uri)

        success = run_pipeline(
            mode="full",
            tracking_uri=tracking_uri,
            experiment="ci-smoke-pipeline",
            test_mode=True,
            champion_pr_auc=0.70,
        )

        if not success:
            logger.error("CI smoke pipeline failed quality gates!")
            return False

        logger.info("CI smoke pipeline completed successfully.")
        return True


def main() -> None:
    success = run_smoke()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
