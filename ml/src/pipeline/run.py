"""CLI orchestrator for the ML pipeline (§5.1, §5.6).

Usage:
    python -m ml.src.pipeline.run --mode full --tracking-uri http://localhost:5000
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import mlflow

from ml.src.pipeline.promote import promote as open_promotion_pr
from ml.src.pipeline.steps import (
    step_evaluate,
    step_prepare,
    step_quality_gates,
    step_train,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ml-pipeline")


def get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def run_pipeline(
    mode: str = "full",
    tracking_uri: str = "http://localhost:5000",
    experiment: str = "fraud-detector-pipeline",
    data_path: Path | None = None,
    test_mode: bool = False,
    champion_pr_auc: float | None = None,
    model_version: str | None = None,
) -> bool:
    """Execute the end-to-end ML pipeline with parent-child runs and quality gates."""
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)

    logger.info("Starting ML pipeline (mode=%s, tracking_uri=%s)...", mode, tracking_uri)

    with mlflow.start_run(run_name=f"pipeline-{mode}") as parent_run:
        commit = get_git_commit()
        mlflow.set_tag("git_commit", commit)
        mlflow.set_tag("pipeline_mode", mode)
        mlflow.log_param("mode", mode)

        # 1. Prepare
        logger.info("[Step 1/4] Running data preparation...")
        prep_result = step_prepare(data_path=data_path, test_mode=test_mode, parent_run=True)
        mlflow.set_tag("data_hash", prep_result["data_hash"])

        # 2. Train
        logger.info("[Step 2/4] Running model training...")
        train_result = step_train(dev_df=prep_result["development"], parent_run=True)

        # 3. Evaluate
        logger.info("[Step 3/4] Running offline evaluation...")
        eval_metrics = step_evaluate(
            pipeline_artifacts=train_result,
            test_df=prep_result["test"],
            parent_run=True,
        )

        # 4. Quality Gates
        logger.info("[Step 4/4] Evaluating quality gates...")
        gate_results = step_quality_gates(
            metrics=eval_metrics,
            champion_pr_auc=champion_pr_auc,
            parent_run=True,
        )

        all_passed = gate_results["all_passed"]
        if all_passed:
            logger.info("Quality gates passed! Model ready for promotion.")
            mlflow.set_tag("promotion_status", "ELIGIBLE")
            mv = model_version or os.environ.get("MODEL_VERSION", "1")
            github_token = os.environ.get("GITHUB_TOKEN", "")
            auto_merge = os.environ.get("AUTO_MERGE", "true").lower() == "true"
            if not test_mode and github_token:
                try:
                    result = open_promotion_pr(
                        model_version=mv,
                        run_id=parent_run.info.run_id,
                        metrics=eval_metrics,
                        auto_merge=auto_merge,
                        tracking_uri=tracking_uri,
                    )
                    mlflow.set_tag("promotion_pr_url", result.get("pr_url", ""))
                    mlflow.set_tag("promotion_branch", result.get("branch", ""))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Model promotion PR failed (non-fatal): %s", exc)
                    mlflow.set_tag("promotion_status", "PR_FAILED")
            else:
                logger.info(
                    "Skipping GitHub promotion (test_mode=%s, token_set=%s)",
                    test_mode,
                    bool(github_token),
                )
        else:
            logger.warning("Quality gates failed! Halting pipeline without promotion.")
            mlflow.set_tag("promotion_status", "REJECTED")

        logger.info("Pipeline completed. Parent run ID: %s", parent_run.info.run_id)
        return all_passed


def main() -> None:
    parser = argparse.ArgumentParser(description="FinTech MLOps automated training pipeline")
    parser.add_argument("--mode", choices=["full", "retrain"], default="full")
    parser.add_argument(
        "--tracking-uri",
        default=os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"),
    )
    parser.add_argument("--experiment", default="fraud-detector-pipeline")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--champion-pr-auc", type=float, default=None)
    parser.add_argument("--model-version", default=None, help="Registered model version to promote")

    args = parser.parse_args()
    success = run_pipeline(
        mode=args.mode,
        tracking_uri=args.tracking_uri,
        experiment=args.experiment,
        data_path=args.data_path,
        test_mode=args.test_mode,
        champion_pr_auc=args.champion_pr_auc,
        model_version=args.model_version,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
