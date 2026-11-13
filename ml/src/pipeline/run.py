"""CLI orchestrator for the ML pipeline (§5.1, §5.6, T21).

Usage:
    # Training (never reads fraudTest.csv)
    python -m ml.src.pipeline.run --mode full \
        --data-path data/raw/fraudTrain.csv \
        --tracking-uri http://localhost:5000 --no-register

    # Official D48 evaluation (consumes verified artifacts)
    python -m ml.src.pipeline.run --mode evaluate \
        --evaluation-dir /outside/repo/d48-results \
        --candidate-model /outside/repo/d44/candidate.joblib \
        --model-uri models:/fraud-detector/1 \
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

from ml.src.evaluation.model_binding import (
    assert_model_binding,
    load_frozen_candidate,
)
from ml.src.model.registry import build_input_example
from ml.src.pipeline.promote import promote as open_promotion_pr
from ml.src.pipeline.steps import (
    step_calibrate,
    step_conformal,
    step_evaluate,
    step_evaluate_synthetic,
    step_logreg_baseline,
    step_package_model,
    step_prepare,
    step_quality_gates,
    step_register,
    step_train,
    step_visualize,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("ml-pipeline")


def get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def _load_python_model(model_uri: str):
    """Load the registered model and unwrap the custom pyfunc implementation."""
    loaded = mlflow.pyfunc.load_model(model_uri)
    unwrap = getattr(loaded, "unwrap_python_model", None)
    return unwrap() if callable(unwrap) else loaded


def _run_evaluation(
    *,
    tracking_uri: str,
    experiment: str,
    evaluation_dir: Path,
    candidate_model: Path,
    model_uri: str | None,
    model_name: str,
    model_version: str | None,
    champion_pr_auc: float | None,
    baseline_pr_auc: float | None,
) -> bool:
    """Log a verified D48 artifact for the frozen candidate; never trains."""

    uri = model_uri or f"models:/{model_name}/{model_version or '1'}"
    frozen = load_frozen_candidate(candidate_model)
    model = _load_python_model(uri)
    assert_model_binding(frozen, model)

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name="pipeline-evaluate"):
        mlflow.set_tag("git_commit", get_git_commit())
        mlflow.set_tag("pipeline_mode", "evaluate")
        mlflow.set_tag("decision_id", "D48")
        mlflow.set_tag("evaluation_source", "final_evaluation_artifacts")
        mlflow.set_tag("model_uri", uri)
        mlflow.set_tag("candidate_sha256", frozen.sha256)
        mlflow.set_tag("model_binding", "frozen_joblib_verified")
        mlflow.log_param("evaluation_dir", str(Path(evaluation_dir)))
        mlflow.log_param("candidate_model", str(frozen.path))

        metrics = step_evaluate(
            pyfunc_model=model,
            evaluation_dir=Path(evaluation_dir),
            expected_model_sha256=frozen.sha256,
            parent_run=True,
        )
        gates = step_quality_gates(
            metrics=metrics,
            champion_pr_auc=champion_pr_auc,
            baseline_pr_auc=baseline_pr_auc,
            alpha=float(metrics["alpha"]),
            parent_run=True,
        )
        mlflow.set_tag("promotion_status", "NOT_APPLICABLE")
        logger.info(
            "D48 evaluation logged for %s (gates_passed=%s). No promotion performed.",
            uri,
            gates["all_passed"],
        )
        return bool(gates["all_passed"])


def run_pipeline(
    mode: str = "full",
    tracking_uri: str = "http://localhost:5000",
    experiment: str = "fraud-detector-pipeline",
    data_path: Path | None = None,
    test_mode: bool = False,
    champion_pr_auc: float | None = None,
    baseline_pr_auc: float | None = None,
    evaluation_dir: Path | None = None,
    candidate_model: Path | None = None,
    model_uri: str | None = None,
    model_version: str | None = None,
    alpha: float | None = None,
    register: bool = True,
    model_name: str = "fraud-detector",
) -> bool:
    """Execute training or the official D48 evaluation.

    Training never reads ``fraudTest.csv``. ``mode="evaluate"`` consumes the
    verified D48 artifact directory produced once by
    ``ml/scripts/evaluate_final_candidate.py``.
    """

    if mode not in {"full", "retrain", "evaluate"}:
        raise ValueError("mode doit etre 'full', 'retrain' ou 'evaluate'.")
    real_mode = data_path is not None and not test_mode
    if mode == "evaluate":
        if evaluation_dir is None:
            raise ValueError("--evaluation-dir est requis avec --mode evaluate.")
        if candidate_model is None:
            raise ValueError("--candidate-model est requis avec --mode evaluate.")
        if data_path is not None:
            raise ValueError("--data-path n'est pas utilise avec --mode evaluate.")
        if test_mode:
            raise ValueError("--test-mode n'est pas utilise avec --mode evaluate.")
        register = False
    else:
        if evaluation_dir is not None:
            raise ValueError("--evaluation-dir est reserve a --mode evaluate.")
        if candidate_model is not None:
            raise ValueError("--candidate-model est reserve a --mode evaluate.")
        if real_mode and register:
            raise ValueError(
                "Un run reel ne peut pas s'enregistrer sans l'evaluation D48 verifiee; "
                "utilisez --mode evaluate ou --no-register."
            )

    requested_alpha = alpha
    if requested_alpha is None and os.environ.get("ALPHA"):
        requested_alpha = float(os.environ["ALPHA"])
    if requested_alpha is not None and not 0.0 < requested_alpha < 1.0:
        raise ValueError("alpha doit etre dans ]0, 1[.")

    if mode == "evaluate":
        return _run_evaluation(
            tracking_uri=tracking_uri,
            experiment=experiment,
            evaluation_dir=Path(evaluation_dir),
            candidate_model=Path(candidate_model),
            model_uri=model_uri,
            model_name=model_name,
            model_version=model_version,
            champion_pr_auc=champion_pr_auc,
            baseline_pr_auc=baseline_pr_auc,
        )

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
            test_mode=test_mode,
            parent_run=True,
        )
        mlflow.set_tag("data_hash", prep_result["data_hash"])
        mlflow.set_tag("test_data_hash", prep_result["test_data_hash"] or "unread")

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

        eval_metrics: dict[str, float | None] | None = None
        gate_results: dict[str, bool] | None = None
        sample_df = prep_result["test"]

        if sample_df is not None:
            # 6. Synthetic-only evaluation for --test-mode / CI smoke
            logger.info("[Step 6/9] Evaluating on the synthetic holdout...")
            eval_metrics = step_evaluate_synthetic(
                pyfunc_model=pyfunc_model,
                test_df=sample_df,
                latency_sample_size=1000,
                parent_run=True,
            )

            # 6b. First-run non-regression reference: logistic regression (§5.4)
            logger.info("[Step 6b/9] Scoring the logistic-regression baseline...")
            baseline_metrics = step_logreg_baseline(
                train_result=train_result,
                dev_df=prep_result["development"],
                test_df=sample_df,
                parent_run=True,
            )
            reference_pr_auc = (
                baseline_pr_auc
                if baseline_pr_auc is not None
                else baseline_metrics["pr_auc"]
            )

            # 7. Quality gates
            logger.info("[Step 7/9] Evaluating quality gates...")
            gate_results = step_quality_gates(
                metrics=eval_metrics,
                champion_pr_auc=champion_pr_auc,
                baseline_pr_auc=reference_pr_auc,
                alpha=resolved_alpha,
                parent_run=True,
            )
        else:
            mlflow.set_tag("evaluation_status", "absent")
            mlflow.set_tag("promotion_status", "NOT_EVALUATED")
            logger.info(
                "Real training run completed without final evaluation; "
                "registration disabled."
            )
            return True

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
                    sample_df=sample_df,
                    pyfunc_model=pyfunc_model,
                    model_version=packaged_version,
                    parent_run=True,
                )
                viz_directory = Path(viz_result["directory"])

                # 9. Registry
                if register:
                    logger.info("[Step 9/9] Registering %s in MLflow...", model_name)
                    input_example = build_input_example(sample_df)
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
                registration["version"]
                if registration
                else (model_version or packaged_version)
            )
            if real_mode and github_token:
                try:
                    result = open_promotion_pr(
                        model_version=promote_version,
                        run_id=parent_run.info.run_id,
                        metrics=eval_metrics or {},
                        auto_merge=os.environ.get("AUTO_MERGE", "true").lower()
                        == "true",
                        tracking_uri=tracking_uri,
                    )
                    mlflow.set_tag("promotion_pr_url", result.get("pr_url", ""))
                    mlflow.set_tag("promotion_branch", result.get("branch", ""))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Model promotion PR failed (non-fatal): %s", exc)
                    mlflow.set_tag("promotion_status", "PR_FAILED")
            else:
                logger.info(
                    "Skipping GitHub promotion (real_mode=%s, token_set=%s)",
                    real_mode,
                    bool(github_token),
                )
        else:
            logger.warning("Quality gates failed! Halting pipeline without promotion.")
            mlflow.set_tag("promotion_status", "REJECTED")

        logger.info("Pipeline completed. Parent run ID: %s", parent_run.info.run_id)
        return all_passed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FinTech MLOps automated training pipeline"
    )
    parser.add_argument(
        "--mode", choices=["full", "retrain", "evaluate"], default="full"
    )
    parser.add_argument(
        "--tracking-uri",
        default=os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"),
    )
    parser.add_argument("--experiment", default="fraud-detector-pipeline")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument(
        "--evaluation-dir",
        type=Path,
        default=None,
        help="Verified D48 output directory; only valid with --mode evaluate.",
    )
    parser.add_argument(
        "--candidate-model",
        type=Path,
        default=None,
        help="Frozen D44 joblib; required with --mode evaluate to bind the served model.",
    )
    parser.add_argument("--model-uri", default=None)
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--champion-pr-auc", type=float, default=None)
    parser.add_argument("--baseline-pr-auc", type=float, default=None)
    parser.add_argument(
        "--model-version", default=None, help="Version label baked into the wrapper"
    )
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
        test_mode=args.test_mode,
        champion_pr_auc=args.champion_pr_auc,
        baseline_pr_auc=args.baseline_pr_auc,
        evaluation_dir=args.evaluation_dir,
        candidate_model=args.candidate_model,
        model_uri=args.model_uri,
        model_version=args.model_version,
        alpha=args.alpha,
        register=not args.no_register,
        model_name=args.model_name,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
