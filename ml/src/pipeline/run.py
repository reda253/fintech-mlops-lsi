"""CLI orchestrator for the ML pipeline (§5.1, §5.6, T21).

Usage:
    python -m ml.src.pipeline.run --mode full \
        --data-path data/raw/fraudTrain.csv \
        --test-path data/raw/fraudTest.csv \
        --tracking-uri http://localhost:5000
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import mlflow

from ml.src.model.registry import build_input_example
from ml.src.pipeline.promote import promote as open_promotion_pr
from ml.src.pipeline.steps import (
    step_calibrate,
    step_conformal,
    step_evaluate,
    step_logreg_baseline,
    step_package_model,
    step_prepare,
    step_quality_gates,
    step_register,
    step_train,
    step_visualize,
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
    test_path: Path | None = None,
    test_mode: bool = False,
    champion_pr_auc: float | None = None,
    model_version: str | None = None,
    alpha: float | None = None,
    register: bool = True,
    model_name: str = "fraud-detector",
) -> bool:
    """Execute the end-to-end ML pipeline with parent-child runs and quality gates."""

    requested_alpha = alpha
    if requested_alpha is None and os.environ.get("ALPHA"):
        requested_alpha = float(os.environ["ALPHA"])
    if requested_alpha is not None and not 0.0 < requested_alpha < 1.0:
        raise ValueError("alpha doit etre dans ]0, 1[.")

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)

    logger.info(
        "Starting ML pipeline (mode=%s, alpha=%s, tracking_uri=%s)...",
        mode,
        f"{requested_alpha:.3f}" if requested_alpha is not None else "D46 selection",
        tracking_uri,
    )

    with mlflow.start_run(run_name=f"pipeline-{mode}") as parent_run:
        commit = get_git_commit()
        mlflow.set_tag("git_commit", commit)
        mlflow.set_tag("pipeline_mode", mode)
        mlflow.log_param("mode", mode)
        mlflow.log_param(
            "alpha_mode", "fixed" if requested_alpha is not None else "selected"
        )

        # 1. Prepare
        logger.info("[Step 1/9] Running data preparation...")
        prep_result = step_prepare(
            data_path=data_path,
            test_path=test_path,
            test_mode=test_mode,
            parent_run=True,
        )
        mlflow.set_tag("data_hash", prep_result["data_hash"])
        mlflow.set_tag("test_data_hash", prep_result["test_data_hash"])

        # 2. Train
        logger.info("[Step 2/9] Training XGBoost on the development block...")
        train_result = step_train(dev_df=prep_result["development"], parent_run=True)
        mlflow.set_tag("beta", str(train_result["beta"]))

        # 3. Probability calibration
        logger.info("[Step 3/9] Calibrating probabilities (isotonic vs sigmoid)...")
        calibration_result = step_calibrate(
            train_result=train_result,
            prob_calib_df=prep_result["prob_calib"],
            parent_run=True,
        )
        mlflow.set_tag("calibration_method", calibration_result["method"])

        # 4. Conformal quantiles (D46: 50/25/25, alpha chosen on the middle block)
        logger.info("[Step 4/9] Computing Mondrian conformal thresholds...")
        conformal_result = step_conformal(
            train_result=train_result,
            calibration_result=calibration_result,
            conformal_df=prep_result["conformal_calib"],
            alpha=requested_alpha,
            parent_run=True,
        )
        resolved_alpha = float(conformal_result["alpha"])
        mlflow.log_param("alpha", resolved_alpha)
        mlflow.log_param(
            "alpha_selection_status", conformal_result["alpha_selection_status"]
        )
        logger.info(
            "Selected alpha=%.3f (%s).",
            resolved_alpha,
            conformal_result["alpha_selection_status"],
        )

        # 5. Package the pyfunc wrapper before evaluation
        logger.info("[Step 5/9] Packaging the fraud detector wrapper...")
        packaged_version = model_version or "1"
        pyfunc_model = step_package_model(
            train_result=train_result,
            calibration_result=calibration_result,
            conformal_result=conformal_result,
            model_name=model_name,
            model_version=packaged_version,
            alpha=resolved_alpha,
            git_commit=commit,
            data_sha256=prep_result["data_hash"],
            parent_run=True,
        )

        # 6. Offline evaluation
        logger.info("[Step 6/9] Evaluating on the independent test block...")
        eval_metrics = step_evaluate(
            pyfunc_model=pyfunc_model,
            test_df=prep_result["test"],
            latency_sample_size=1000,
            parent_run=True,
        )

        # 6b. First-run non-regression reference: logistic regression (§5.4)
        logger.info("[Step 6b/9] Scoring the logistic-regression baseline...")
        baseline_metrics = step_logreg_baseline(
            train_result=train_result,
            dev_df=prep_result["development"],
            test_df=prep_result["test"],
            parent_run=True,
        )

        # 7. Quality gates
        logger.info("[Step 7/9] Evaluating quality gates...")
        gate_results = step_quality_gates(
            metrics=eval_metrics,
            champion_pr_auc=champion_pr_auc,
            baseline_pr_auc=baseline_metrics["pr_auc"],
            alpha=resolved_alpha,
            parent_run=True,
        )

        all_passed = gate_results["all_passed"]
        registration: dict | None = None
        viz_directory: Path | None = None

        if all_passed:
            logger.info("Quality gates passed! Model ready for promotion.")
            mlflow.set_tag("promotion_status", "ELIGIBLE")
            try:
                # 8. Visualisations
                logger.info("[Step 8/9] Generating PCA / t-SNE / UMAP projections...")
                viz_result = step_visualize(
                    test_df=prep_result["test"],
                    pyfunc_model=pyfunc_model,
                    model_version=packaged_version,
                    parent_run=True,
                )
                viz_directory = Path(viz_result["directory"])

                # 9. Registry
                if register:
                    logger.info("[Step 9/9] Registering %s in MLflow...", model_name)
                    input_example = build_input_example(prep_result["test"])
                    registration = step_register(
                        pyfunc_model=pyfunc_model,
                        input_example=input_example,
                        model_name=model_name,
                        pipeline_run_id=parent_run.info.run_id,
                        viz_dir=viz_directory,
                        parent_run=True,
                    )
                    mlflow.set_tag("model_version", registration["version"])
                    mlflow.set_tag("model_uri", registration["model_uri"])
                    mlflow.set_tag("model_alias", registration["alias"])
                else:
                    logger.info("Registration disabled (register=False).")
                    mlflow.set_tag("registration", "skipped")
            finally:
                if viz_directory is not None:
                    shutil.rmtree(viz_directory, ignore_errors=True)

            github_token = os.environ.get("GITHUB_TOKEN", "")
            promote_version = (
                registration["version"] if registration else (model_version or packaged_version)
            )
            if not test_mode and github_token:
                try:
                    result = open_promotion_pr(
                        model_version=promote_version,
                        run_id=parent_run.info.run_id,
                        metrics=eval_metrics,
                        auto_merge=os.environ.get("AUTO_MERGE", "true").lower() == "true",
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
    parser.add_argument("--test-path", type=Path, default=None)
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--champion-pr-auc", type=float, default=None)
    parser.add_argument("--model-version", default=None, help="Version label baked into the wrapper")
    parser.add_argument("--model-name", default="fraud-detector")
    parser.add_argument(
        "--alpha",
        type=float,
        default=None,
        help="Alpha fixe. Omis, D46 choisit le plus petit alpha sous 2 %% de revue.",
    )
    parser.add_argument("--no-register", action="store_true")

    args = parser.parse_args()
    success = run_pipeline(
        mode=args.mode,
        tracking_uri=args.tracking_uri,
        experiment=args.experiment,
        data_path=args.data_path,
        test_path=args.test_path,
        test_mode=args.test_mode,
        champion_pr_auc=args.champion_pr_auc,
        model_version=args.model_version,
        alpha=args.alpha,
        register=not args.no_register,
        model_name=args.model_name,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
