"""Pipeline modular step definitions (§5.1, §5.4, T21).

Lifecycle:
1. prepare      -> chronological 70/15/15 split + independent fraudTest.csv
2. train        -> preprocessing + XGBoost on an undersampled development block
3. calibrate    -> isotonic vs sigmoid, keep the lowest Brier score
4. conformal    -> Mondrian class-conditional quantiles at alpha
5. evaluate     -> real PR-AUC / coverage / review / error / latency metrics
6. quality_gates-> promotion gates (review rate <= 2 %)
7. visualize    -> PCA / t-SNE / UMAP projections for the dashboard
8. package      -> self-contained FraudDetectorModel wrapper
9. register     -> MLflow model version + champion alias + tags
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tempfile
import time
from itertools import pairwise
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from ml.src.model.calibration import (
    correct_proba,
    fit_calibrator,
    mondrian_thresholds,
)
from ml.src.model.fraud_detector import FraudDetectorModel
from ml.src.model.registry import register_model
from ml.src.preprocessing.pipeline import build_preprocessing_pipeline

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = Path(__file__).resolve().parents[1]
BEST_PARAMS_PATH = ROOT_DIR / "configs" / "best_params.json"

TARGET_COLUMN = "is_fraud"
DATE_COLUMN = "trans_date_trans_time"
DEFAULT_ALPHA = 0.02
ALPHA_GRID = (0.01, 0.02, 0.03, 0.05, 0.10)
REVIEW_RATE_GATE = 0.02
COVERAGE_SLACK = 0.02
LATENCY_GATE_SECONDS = 0.050
LATENCY_SAMPLE_SIZE = 1000
UNDERSAMPLING_RATIO = 10

SPARKOV_COLUMNS = [
    DATE_COLUMN,
    "cc_num",
    "amt",
    "category",
    "gender",
    "state",
    "city_pop",
    "lat",
    "long",
    "dob",
    "merch_lat",
    "merch_long",
    TARGET_COLUMN,
    "trans_num",
]

CATEGORIES = [
    "entertainment",
    "food_dining",
    "gas_transport",
    "grocery_net",
    "grocery_pos",
    "health_fitness",
    "home",
    "kids_pets",
    "misc_net",
    "misc_pos",
    "personal_care",
    "shopping_net",
    "shopping_pos",
    "travel",
]
STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY",
]

DEFAULT_XGB_PARAMS = {
    "tree_method": "hist",
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "n_estimators": 120,
    "max_depth": 6,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
}


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 checksum of a file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frame_sha256(frame: pd.DataFrame) -> str:
    """Deterministic content hash for an in-memory Sparkov frame."""

    hashed = pd.util.hash_pandas_object(frame, index=False).to_numpy(dtype="uint64")
    return hashlib.sha256(hashed.tobytes()).hexdigest()


def generate_synthetic_data(
    n_samples: int = 4000,
    random_state: int = 42,
    fraud_rate: float = 0.10,
) -> pd.DataFrame:
    """Generate a Sparkov-shaped frame for CI and ``--test-mode``.

    The synthetic signal is deliberately strong (fraud amounts and night hours)
    so that the smoke pipeline exercises calibration and conformal quantiles
    without depending on the real Kaggle dataset.
    """

    rng = np.random.default_rng(random_state)
    start = pd.Timestamp("2020-01-01 00:00:00")
    offsets = np.sort(rng.integers(0, 365 * 24 * 60, size=n_samples))
    timestamps = start + pd.to_timedelta(offsets, unit="m")

    is_fraud = (rng.uniform(size=n_samples) < fraud_rate).astype(np.int64)
    min_fraud = min(max(8, int(n_samples * fraud_rate * 0.5)), max(1, n_samples // 20))
    if int(is_fraud.sum()) < min_fraud:
        chosen = rng.choice(n_samples, size=min_fraud, replace=False)
        is_fraud[chosen] = 1

    amounts = rng.lognormal(mean=3.3, sigma=0.8, size=n_samples)
    fraud_mask = is_fraud == 1
    amounts[fraud_mask] *= rng.uniform(6.0, 18.0, size=fraud_mask.sum())

    base_lat = rng.uniform(25.0, 48.0, size=n_samples)
    base_long = rng.uniform(-120.0, -70.0, size=n_samples)
    merch_lat = base_lat + rng.normal(0.0, 0.25, size=n_samples)
    merch_long = base_long + rng.normal(0.0, 0.25, size=n_samples)
    merch_lat[fraud_mask] += rng.uniform(2.0, 6.0, size=fraud_mask.sum())
    merch_long[fraud_mask] -= rng.uniform(2.0, 6.0, size=fraud_mask.sum())

    birth_days = rng.integers(16 * 365, 70 * 365, size=n_samples)
    dob = pd.Timestamp("2020-01-01") - pd.to_timedelta(birth_days, unit="D")

    categories = rng.choice(CATEGORIES, size=n_samples)
    if fraud_mask.any():
        categories[fraud_mask] = rng.choice(
            ["shopping_net", "misc_net", "travel"], size=fraud_mask.sum()
        )

    if fraud_mask.any():
        # Push fraud timestamps into the night window to give XGBoost a
        # learnable signal independent of the amount.
        night_offsets = rng.integers(0, 4 * 60, size=fraud_mask.sum())
        timestamps = pd.Series(timestamps)
        timestamps.loc[fraud_mask] = (
            timestamps.loc[fraud_mask].dt.normalize()
            + pd.to_timedelta(60 + night_offsets, unit="m")
        )
        timestamps = pd.DatetimeIndex(timestamps)

    frame = pd.DataFrame(
        {
            DATE_COLUMN: timestamps.strftime("%Y-%m-%d %H:%M:%S"),
            "cc_num": rng.integers(10**15, 10**16, size=n_samples, dtype=np.int64),
            "amt": np.round(amounts, 2),
            "category": categories,
            "gender": rng.choice(["M", "F"], size=n_samples),
            "state": rng.choice(STATES, size=n_samples),
            "city_pop": rng.integers(500, 1_500_000, size=n_samples),
            "lat": np.round(base_lat, 6),
            "long": np.round(base_long, 6),
            "dob": dob.strftime("%Y-%m-%d"),
            "merch_lat": np.round(merch_lat, 6),
            "merch_long": np.round(merch_long, 6),
            TARGET_COLUMN: is_fraud,
            "trans_num": [f"synth-{random_state}-{index:06d}" for index in range(n_samples)],
        }
    )
    return frame.sort_values(DATE_COLUMN).reset_index(drop=True)


def _read_sparkov_csv(path: Path) -> pd.DataFrame:
    """Read only the modelling columns from a Sparkov CSV, sorted by time."""

    available = set(SPARKOV_COLUMNS)
    frame = pd.read_csv(path, usecols=lambda column: column in available)
    missing = [column for column in SPARKOV_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Colonnes Sparkov manquantes dans {path}: {missing}")

    parsed = pd.to_datetime(frame[DATE_COLUMN], errors="raise")
    order = parsed.sort_values().index
    return frame.loc[order].reset_index(drop=True)


def _chronological_blocks(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n_rows = len(frame)
    if n_rows < 30:
        raise ValueError("Le jeu de donnees doit contenir au moins 30 lignes.")
    development_end = int(n_rows * 0.70)
    calibration_end = int(n_rows * 0.85)

    development = frame.iloc[:development_end].copy()
    prob_calib = frame.iloc[development_end:calibration_end].copy()
    conformal_calib = frame.iloc[calibration_end:].copy()
    for block in (prob_calib, conformal_calib):
        if block[TARGET_COLUMN].nunique() < 2:
            raise ValueError("Chaque bloc de calibration doit contenir les deux classes.")
    return development, prob_calib, conformal_calib


def step_prepare(
    data_path: Path | None = None,
    test_path: Path | None = None,
    test_mode: bool = False,
    parent_run: bool = True,
) -> dict[str, Any]:
    """Phase 1: validate the dataset and split it chronologically (§4.2)."""

    with mlflow.start_run(run_name="1_prepare", nested=parent_run):
        if test_mode or data_path is None:
            logger.info("Generating synthetic Sparkov data (test mode).")
            # D46 splits the conformal block 50/25/25; 12k rows keep enough
            # per-class observations for alpha=0.02 to remain applicable.
            frame = generate_synthetic_data(n_samples=12000, random_state=42)
            test_frame = generate_synthetic_data(n_samples=1000, random_state=1042)
            data_hash = _frame_sha256(frame)
            test_data_hash = _frame_sha256(test_frame)
            source = "synthetic"
        else:
            data_path = Path(data_path)
            if not data_path.is_file():
                raise FileNotFoundError(f"fraudTrain introuvable: {data_path}")
            if test_path is None:
                test_path = data_path.parent / "fraudTest.csv"
            test_path = Path(test_path)
            if not test_path.is_file():
                raise FileNotFoundError(
                    f"fraudTest introuvable: {test_path}. Utilisez --test-mode pour le smoke test."
                )
            frame = _read_sparkov_csv(data_path)
            test_frame = _read_sparkov_csv(test_path)
            data_hash = sha256_file(data_path)
            test_data_hash = sha256_file(test_path)
            source = "sparkov"

        development, prob_calib, conformal_calib = _chronological_blocks(frame)

        mlflow.log_param("data_source", source)
        mlflow.log_param("data_hash", data_hash)
        mlflow.log_param("test_data_hash", test_data_hash)
        mlflow.log_metric("total_samples", len(frame))
        mlflow.log_metric("development_samples", len(development))
        mlflow.log_metric("prob_calib_samples", len(prob_calib))
        mlflow.log_metric("conformal_samples", len(conformal_calib))
        mlflow.log_metric("test_samples", len(test_frame))

        return {
            "development": development,
            "prob_calib": prob_calib,
            "conformal_calib": conformal_calib,
            "test": test_frame,
            "data_hash": data_hash,
            "test_data_hash": test_data_hash,
            "source": source,
        }


def load_best_params(path: Path | None = None) -> tuple[dict[str, Any], str]:
    """Load ``models.xgb.params`` from configs/best_params.json with a fallback."""

    candidate = Path(path) if path is not None else BEST_PARAMS_PATH
    if candidate.is_file():
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            params = payload["models"]["xgb"]["params"]
            if isinstance(params, dict) and params:
                return dict(params), str(candidate)
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("Invalid best_params.json (%s); using defaults.", exc)
    return dict(DEFAULT_XGB_PARAMS), "defaults"


def _undersample_indices(
    y: np.ndarray,
    ratio: int = UNDERSAMPLING_RATIO,
    seed: int = 42,
) -> tuple[np.ndarray, float, dict[str, int]]:
    """Keep every fraud row and ``ratio`` legitimate rows per fraud."""

    fraud_positions = np.flatnonzero(y == 1)
    legit_positions = np.flatnonzero(y == 0)
    n_fraud, n_legit = fraud_positions.size, legit_positions.size
    if n_fraud == 0 or n_legit == 0:
        raise ValueError("Le bloc de developpement doit contenir les deux classes.")

    n_kept = min(n_legit, int(ratio) * n_fraud)
    rng = np.random.default_rng(seed)
    sampled_legit = rng.choice(legit_positions, size=n_kept, replace=False)
    kept = rng.permutation(np.concatenate([fraud_positions, sampled_legit]))
    beta = n_kept / n_legit
    counts = {
        "n_fraud": int(n_fraud),
        "n_legit": int(n_legit),
        "n_kept_legit": int(n_kept),
        "n_train_after": int(kept.size),
    }
    return kept, float(beta), counts


def step_train(
    dev_df: pd.DataFrame,
    params: dict[str, Any] | None = None,
    seed: int = 42,
    parent_run: bool = True,
) -> dict[str, Any]:
    """Phase 2: fit preprocessing on natural data then XGBoost on a balanced sample."""

    with mlflow.start_run(run_name="2_train", nested=parent_run):
        if str(SRC_DIR) not in sys.path:
            sys.path.append(str(SRC_DIR))
        from models.factory import build_model

        model_params, params_source = (
            (dict(params), "explicit") if params is not None else load_best_params()
        )

        y_dev = dev_df[TARGET_COLUMN].to_numpy(dtype=np.int64)
        preprocessor = build_preprocessing_pipeline()
        start_time = time.perf_counter()
        features_all = preprocessor.fit_transform(dev_df, y_dev)
        preprocess_duration = time.perf_counter() - start_time

        kept, beta, counts = _undersample_indices(y_dev, seed=seed)
        x_train = np.asarray(features_all)[kept]
        y_train = y_dev[kept]

        classifier = build_model("xgb", model_params, seed=seed)
        start_time = time.perf_counter()
        classifier.fit(x_train, y_train)
        train_duration = time.perf_counter() - start_time

        mlflow.log_param("params_source", params_source)
        mlflow.log_param("model_type", "XGBClassifier")
        mlflow.log_param("alpha", os.environ.get("ALPHA", str(DEFAULT_ALPHA)))
        mlflow.log_param("beta", beta)
        mlflow.log_param("undersampling_ratio", UNDERSAMPLING_RATIO)
        mlflow.log_params(
            {f"xgb_{key}": value for key, value in model_params.items() if np.isscalar(value)}
        )
        mlflow.log_metric("preprocess_duration_seconds", preprocess_duration)
        mlflow.log_metric("train_duration_seconds", train_duration)
        for key, value in counts.items():
            mlflow.log_metric(key, value)

        return {
            "preprocessor": preprocessor,
            "classifier": classifier,
            "beta": beta,
            "counts": counts,
            "params": model_params,
            "feature_count": int(np.asarray(features_all).shape[1]),
        }


def _raw_probabilities(
    train_result: dict[str, Any],
    frame: pd.DataFrame,
) -> np.ndarray:
    features = train_result["preprocessor"].transform(frame)
    probabilities = train_result["classifier"].predict_proba(features)[:, 1]
    return correct_proba(probabilities, float(train_result["beta"]))


def _apply_calibrator(calibrator: Any, probabilities: np.ndarray) -> np.ndarray:
    calibrated = np.asarray(calibrator.predict(probabilities), dtype=np.float64)
    return np.clip(calibrated, 0.0, 1.0)


def _chronological_parts(
    frame: pd.DataFrame,
    weights: tuple[int, ...],
) -> list[pd.DataFrame]:
    """Split a chronological block without separating equal timestamps (D46).

    Mirrors ``ml/src/final/train_final.py::chronological_parts`` so a retrain
    reproduces the validated method: moving a boundary to the right is safer
    than leaking a same-timestamp transaction across two zones.
    """

    if not weights or any(weight <= 0 for weight in weights):
        raise ValueError("Fractions de decoupage invalides.")
    dates = pd.to_datetime(frame[DATE_COLUMN])
    if dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("Le bloc a decouper doit etre chronologique.")

    cuts = [0]
    nominal = 0
    total = sum(weights)
    for weight in weights[:-1]:
        nominal += len(frame) * weight // total
        cut = max(nominal, cuts[-1] + 1)
        if cut >= len(frame):
            raise ValueError("Sous-bloc chronologique vide.")
        if dates.iloc[cut - 1] == dates.iloc[cut]:
            cut = int(dates.searchsorted(dates.iloc[cut], side="right"))
        if cut >= len(frame):
            raise ValueError("Impossible de separer les dates sans sous-bloc vide.")
        cuts.append(cut)
    cuts.append(len(frame))
    parts = [frame.iloc[start:end].copy() for start, end in pairwise(cuts)]
    if any(part.empty for part in parts):
        raise ValueError("Sous-bloc chronologique vide.")
    return parts


def step_calibrate(
    train_result: dict[str, Any],
    prob_calib_df: pd.DataFrame,
    method: str | None = None,
    parent_run: bool = True,
) -> dict[str, Any]:
    """Phase 3: fit calibrators on 50 % and select on the other 50 % (D46)."""

    with mlflow.start_run(run_name="3_calibrate", nested=parent_run):
        fit_df, choice_df = _chronological_parts(prob_calib_df, (1, 1))
        for block in (fit_df, choice_df):
            if block[TARGET_COLUMN].nunique() < 2:
                raise ValueError("Chaque moitie de calibration doit contenir les deux classes.")

        fit_probabilities = _raw_probabilities(train_result, fit_df)
        fit_target = fit_df[TARGET_COLUMN].to_numpy(dtype=np.int64)
        choice_probabilities = _raw_probabilities(train_result, choice_df)
        choice_target = choice_df[TARGET_COLUMN].to_numpy(dtype=np.int64)

        calibrator, selected, brier_before, brier_after = fit_calibrator(
            fit_probabilities,
            fit_target,
            method=method,
            evaluation_probabilities=choice_probabilities,
            evaluation_target=choice_target,
        )

        mlflow.log_param("calibration_method", selected)
        mlflow.log_metric("brier_before_calibration", brier_before)
        mlflow.log_metric("brier_after_calibration", brier_after)
        mlflow.log_metric("calibration_rows", len(prob_calib_df))
        mlflow.log_metric("calibration_fit_rows", len(fit_df))
        mlflow.log_metric("calibration_choice_rows", len(choice_df))

        return {
            "calibrator": calibrator,
            "method": selected,
            "brier_before": brier_before,
            "brier_after": brier_after,
            "fit_rows": len(fit_df),
            "choice_rows": len(choice_df),
        }


def _review_rate(probabilities: np.ndarray, thresholds: dict[str, float]) -> float:
    _, _, set_size = _prediction_sets(
        probabilities,
        thresholds["threshold_legit"],
        thresholds["threshold_fraud"],
    )
    return float((set_size != 1).mean())


def step_conformal(
    train_result: dict[str, Any],
    calibration_result: dict[str, Any],
    conformal_df: pd.DataFrame,
    alpha: float | None = None,
    alpha_grid: tuple[float, ...] = ALPHA_GRID,
    parent_run: bool = True,
) -> dict[str, Any]:
    """Phase 4: D46 50/25/25 split with alpha selection on the choice block.

    The first half fits the Mondrian quantiles, the second quarter chooses the
    alpha that keeps the review rate under capacity (labels are never used),
    and the last quarter is scored only after alpha is frozen.
    """

    with mlflow.start_run(run_name="4_conformal", nested=parent_run):
        fit_df, choice_df, evaluation_df = _chronological_parts(conformal_df, (2, 1, 1))
        fit_probabilities = _apply_calibrator(
            calibration_result["calibrator"],
            _raw_probabilities(train_result, fit_df),
        )
        fit_target = fit_df[TARGET_COLUMN].to_numpy(dtype=np.int64)
        choice_probabilities = _apply_calibrator(
            calibration_result["calibrator"],
            _raw_probabilities(train_result, choice_df),
        )

        candidates = tuple(sorted({float(value) for value in alpha_grid}))
        if alpha is not None:
            candidates = (float(alpha),)
        if not candidates or any(not 0.0 < value < 1.0 for value in candidates):
            raise ValueError("alpha doit etre dans ]0, 1[.")

        rows: list[dict[str, Any]] = []
        for candidate in candidates:
            try:
                thresholds = mondrian_thresholds(fit_probabilities, fit_target, candidate)
            except ValueError as exc:
                rows.append(
                    {"alpha": candidate, "status": "inapplicable", "reason": str(exc)}
                )
                continue
            rows.append(
                {
                    "alpha": candidate,
                    "status": "eligible",
                    "thresholds": thresholds,
                    "selection_review_rate": _review_rate(
                        choice_probabilities, thresholds
                    ),
                }
            )

        if alpha is not None:
            selected = next(
                (row for row in rows if row["status"] == "eligible"),
                None,
            )
            if selected is None:
                raise ValueError(
                    "alpha fixe inapplicable: le bloc conforme ne contient pas assez "
                    "d'observations par classe."
                )
            selection_status = "forced"
        else:
            eligible = [
                row
                for row in rows
                if row["status"] == "eligible"
                and row["selection_review_rate"] <= REVIEW_RATE_GATE
            ]
            if eligible:
                selected = min(eligible, key=lambda row: row["alpha"])
                selection_status = "selected"
            else:
                selected = min(
                    (row for row in rows if row["status"] == "eligible"),
                    key=lambda row: (row["selection_review_rate"], row["alpha"]),
                    default=None,
                )
                if selected is None:
                    raise ValueError("Aucun alpha applicable sur le bloc conforme.")
                selection_status = "no_eligible_alpha"
                logger.warning(
                    "No alpha keeps the review rate under %.2f%%; best observed is %.2f%%.",
                    REVIEW_RATE_GATE * 100,
                    selected["selection_review_rate"] * 100,
                )

        selected_alpha = float(selected["alpha"])
        thresholds = selected["thresholds"]
        evaluation_probabilities = _apply_calibrator(
            calibration_result["calibrator"],
            _raw_probabilities(train_result, evaluation_df),
        )
        evaluation_target = evaluation_df[TARGET_COLUMN].to_numpy(dtype=np.int64)
        legit_in, fraud_in, set_size = _prediction_sets(
            evaluation_probabilities,
            thresholds["threshold_legit"],
            thresholds["threshold_fraud"],
        )
        evaluation_coverage_legit = (
            float(legit_in[evaluation_target == 0].mean())
            if np.any(evaluation_target == 0)
            else 0.0
        )
        evaluation_coverage_fraud = (
            float(fraud_in[evaluation_target == 1].mean())
            if np.any(evaluation_target == 1)
            else 0.0
        )
        evaluation_review_rate = float((set_size != 1).mean())

        mlflow.log_param("alpha", selected_alpha)
        mlflow.log_param("alpha_selection_status", selection_status)
        mlflow.log_metric("threshold_legit", thresholds["threshold_legit"])
        mlflow.log_metric("threshold_fraud", thresholds["threshold_fraud"])
        mlflow.log_metric("conformal_n_legit", thresholds["n_legit"])
        mlflow.log_metric("conformal_n_fraud", thresholds["n_fraud"])
        mlflow.log_metric("conformal_fit_rows", len(fit_df))
        mlflow.log_metric("conformal_choice_rows", len(choice_df))
        mlflow.log_metric("conformal_evaluation_rows", len(evaluation_df))
        mlflow.log_metric("selection_review_rate", selected["selection_review_rate"])
        mlflow.log_metric("evaluation_review_rate", evaluation_review_rate)
        mlflow.log_metric("evaluation_coverage_legit", evaluation_coverage_legit)
        mlflow.log_metric("evaluation_coverage_fraud", evaluation_coverage_fraud)
        for row in rows:
            if row["status"] == "eligible":
                mlflow.log_metric(
                    f"alpha_{row['alpha']:.2f}_review_rate".replace(".", "_"),
                    row["selection_review_rate"],
                )
        mlflow.log_dict(
            {
                str(row["alpha"]): row.get("selection_review_rate")
                if row["status"] == "eligible"
                else row["status"]
                for row in rows
            },
            "alpha_selection.json",
        )

        return {
            **thresholds,
            "alpha": selected_alpha,
            "alpha_grid": [row["alpha"] for row in rows],
            "alpha_selection": {
                str(row["alpha"]): row.get("selection_review_rate")
                if row["status"] == "eligible"
                else row["status"]
                for row in rows
            },
            "alpha_selection_status": selection_status,
            "selection_review_rate": selected["selection_review_rate"],
            "evaluation_review_rate": evaluation_review_rate,
            "evaluation_coverage_legit": evaluation_coverage_legit,
            "evaluation_coverage_fraud": evaluation_coverage_fraud,
            "fit_rows": len(fit_df),
            "choice_rows": len(choice_df),
            "evaluation_rows": len(evaluation_df),
        }


def _prediction_sets(
    probabilities: np.ndarray,
    threshold_legit: float,
    threshold_fraud: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorised Mondrian sets: return (legit_in, fraud_in, set_size)."""

    legit_in = probabilities <= threshold_legit
    fraud_in = probabilities >= (1.0 - threshold_fraud)
    set_size = legit_in.astype(np.int64) + fraud_in.astype(np.int64)
    return legit_in, fraud_in, set_size


def _measure_latency(pyfunc_model: FraudDetectorModel, sample: pd.DataFrame) -> float:
    durations: list[float] = []
    for _, row in sample.iterrows():
        record = row.to_dict()
        start = time.perf_counter()
        pyfunc_model.predict_one(record)
        durations.append(time.perf_counter() - start)
    if not durations:
        return 0.0
    return float(np.percentile(durations, 95))


def step_evaluate(
    pyfunc_model: FraudDetectorModel,
    test_df: pd.DataFrame,
    latency_sample_size: int = LATENCY_SAMPLE_SIZE,
    parent_run: bool = True,
) -> dict[str, float | None]:
    """Phase 5: real metrics on the independent fraudTest.csv block."""

    with mlflow.start_run(run_name="5_evaluate", nested=parent_run):
        target = test_df[TARGET_COLUMN].to_numpy(dtype=np.int64)
        probabilities = pyfunc_model.batch_probabilities(test_df)

        if np.unique(target).size > 1:
            pr_auc = float(average_precision_score(target, probabilities))
            roc_auc = float(roc_auc_score(target, probabilities))
        else:
            pr_auc = 0.0
            roc_auc = 0.0
        brier = float(brier_score_loss(target, probabilities)) if target.size else 0.0

        legit_in, fraud_in, set_size = _prediction_sets(
            probabilities,
            pyfunc_model.threshold_legit,
            pyfunc_model.threshold_fraud,
        )
        covered = np.where(target == 0, legit_in, fraud_in)
        coverage_legit = float(legit_in[target == 0].mean()) if np.any(target == 0) else 0.0
        coverage_fraud = float(fraud_in[target == 1].mean()) if np.any(target == 1) else 0.0

        review_rate = float((set_size != 1).mean())
        automation_rate = 1.0 - review_rate
        automatic = set_size == 1
        automatic_errors = np.where(
            legit_in & ~fraud_in,
            target == 1,
            np.where(fraud_in & ~legit_in, target == 0, False),
        )
        auto_error_rate: float | None = (
            float(automatic_errors[automatic].mean()) if automatic.any() else None
        )

        sample_size = min(latency_sample_size, len(test_df))
        latency_sample = test_df.sample(n=sample_size, random_state=42)
        latency_p95 = _measure_latency(pyfunc_model, latency_sample)

        metrics: dict[str, float | None] = {
            "alpha": float(pyfunc_model.alpha),
            "pr_auc": pr_auc,
            "roc_auc": roc_auc,
            "brier_score": brier,
            "conformal_coverage": float(covered.mean()) if covered.size else 0.0,
            "conformal_coverage_legit": coverage_legit,
            "conformal_coverage_fraud": coverage_fraud,
            "review_rate": review_rate,
            "automation_rate": automation_rate,
            "auto_error_rate": auto_error_rate,
            "latency_p95_sec": latency_p95,
            "latency_sample_size": float(sample_size),
            "n_test": float(len(test_df)),
            "n_test_fraud": float(target.sum()),
        }
        for key, value in metrics.items():
            if value is not None:
                mlflow.log_metric(key, value)

        return metrics


def load_logreg_params(path: Path | None = None) -> dict[str, Any]:
    """Load ``models.logreg.params`` with a conservative fallback."""

    candidate = Path(path) if path is not None else BEST_PARAMS_PATH
    if candidate.is_file():
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            params = payload["models"]["logreg"]["params"]
            if isinstance(params, dict) and params:
                return dict(params)
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("Invalid logreg params in best_params.json (%s); using defaults.", exc)
    return {"solver": "lbfgs", "max_iter": 1000, "C": 0.01}


def step_logreg_baseline(
    train_result: dict[str, Any],
    dev_df: pd.DataFrame,
    test_df: pd.DataFrame,
    params: dict[str, Any] | None = None,
    seed: int = 42,
    parent_run: bool = True,
) -> dict[str, float]:
    """Phase 5b: score the logistic-regression reference on the test block.

    §5.4 replaces the first-run absolute PR-AUC minimum with "at least the
    logistic regression". The reference is fitted on the development block with
    the same preprocessing and evaluated on the same independent test block.
    """

    with mlflow.start_run(run_name="5b_logreg_baseline", nested=parent_run):
        if str(SRC_DIR) not in sys.path:
            sys.path.append(str(SRC_DIR))
        from models.factory import build_model

        model_params = dict(params) if params is not None else load_logreg_params()
        preprocessor = train_result["preprocessor"]
        x_dev = np.asarray(preprocessor.transform(dev_df))
        x_test = np.asarray(preprocessor.transform(test_df))
        y_dev = dev_df[TARGET_COLUMN].to_numpy(dtype=np.int64)
        y_test = test_df[TARGET_COLUMN].to_numpy(dtype=np.int64)

        classifier = build_model("logreg", model_params, seed=seed)
        classifier.fit(x_dev, y_dev)
        probabilities = np.asarray(classifier.predict_proba(x_test), dtype=np.float64)[:, 1]

        if np.unique(y_test).size > 1:
            pr_auc = float(average_precision_score(y_test, probabilities))
            roc_auc = float(roc_auc_score(y_test, probabilities))
        else:
            pr_auc = 0.0
            roc_auc = 0.0
        brier = float(brier_score_loss(y_test, probabilities)) if y_test.size else 0.0

        mlflow.log_params({f"logreg_{key}": value for key, value in model_params.items()})
        mlflow.log_metric("logreg_pr_auc", pr_auc)
        mlflow.log_metric("logreg_roc_auc", roc_auc)
        mlflow.log_metric("logreg_brier_score", brier)
        return {"pr_auc": pr_auc, "roc_auc": roc_auc, "brier_score": brier}


def step_quality_gates(
    metrics: dict[str, float | None],
    champion_pr_auc: float | None = None,
    baseline_pr_auc: float | None = None,
    alpha: float | None = None,
    parent_run: bool = True,
) -> dict[str, bool]:
    """Phase 6: promotion quality gates (§5.4).

    Gates:
    1. Non-regression: PR-AUC >= champion - 0.01, or >= logistic regression
       on the first run (no champion yet)
    2. Per-class conformal coverage >= (1 - alpha) - 0.02
    3. Review rate <= 2 % of transactions
    4. Inference p95 < 50 ms
    """

    if alpha is None:
        alpha = float(metrics.get("alpha") or DEFAULT_ALPHA)
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha doit etre dans ]0, 1[.")
    if champion_pr_auc is None and baseline_pr_auc is None:
        raise ValueError("champion_pr_auc ou baseline_pr_auc requis pour la non-regression.")

    with mlflow.start_run(run_name="6_quality_gates", nested=parent_run):
        pr_auc = float(metrics.get("pr_auc") if metrics.get("pr_auc") is not None else 0.0)
        if champion_pr_auc is not None:
            reference = float(champion_pr_auc)
            gate_non_regression = pr_auc >= (reference - 0.01)
        else:
            reference = float(baseline_pr_auc or 0.0)
            gate_non_regression = pr_auc >= reference

        target_coverage = (1.0 - alpha) - COVERAGE_SLACK
        coverage_legit = metrics.get("conformal_coverage_legit")
        coverage_fraud = metrics.get("conformal_coverage_fraud")
        gate_coverage_legit = (
            coverage_legit is not None and float(coverage_legit) >= target_coverage
        )
        gate_coverage_fraud = (
            coverage_fraud is not None and float(coverage_fraud) >= target_coverage
        )
        gate_coverage = gate_coverage_legit and gate_coverage_fraud
        review_rate = metrics.get("review_rate")
        latency = metrics.get("latency_p95_sec")
        gate_review_rate = (
            review_rate is not None and float(review_rate) <= REVIEW_RATE_GATE
        )
        gate_latency = latency is not None and float(latency) < LATENCY_GATE_SECONDS

        gates = {
            "gate_non_regression": bool(gate_non_regression),
            "gate_coverage": bool(gate_coverage),
            "gate_coverage_legit": bool(gate_coverage_legit),
            "gate_coverage_fraud": bool(gate_coverage_fraud),
            "gate_review_rate": bool(gate_review_rate),
            "gate_latency": bool(gate_latency),
        }
        all_passed = all(gates.values())

        mlflow.log_param("alpha", alpha)
        mlflow.log_param("non_regression_reference", reference)
        mlflow.log_param("quality_gates_passed", str(all_passed))
        for gate_name, passed in gates.items():
            mlflow.log_metric(gate_name, 1.0 if passed else 0.0)

        gates["all_passed"] = all_passed
        return gates


def step_visualize(
    test_df: pd.DataFrame,
    pyfunc_model: FraudDetectorModel,
    features: list[str] | None = None,
    output_dir: Path | None = None,
    model_version: str = "1",
    max_samples: int = 500,
    parent_run: bool = True,
) -> dict[str, Any]:
    """Phase 7: generate PCA / t-SNE / UMAP projections for all 5 views (§4.11)."""

    from ml.src.visualization.projections import (
        export_projections_to_cache,
        generate_all_projections,
        prepare_visualization_sample,
    )

    with mlflow.start_run(run_name="7_visualize", nested=parent_run):
        if features is None:
            features = ["amt", "city_pop", "lat", "long", "merch_lat", "merch_long"]

        sample = prepare_visualization_sample(test_df, max_samples=max_samples)
        probabilities = pyfunc_model.batch_probabilities(sample)
        y_pred = (probabilities >= 0.5).astype(np.int64)

        projections = generate_all_projections(
            df=sample,
            features=features,
            y_pred=y_pred,
            probabilities=probabilities,
            model_version=model_version,
            max_samples=max_samples,
        )

        output_dir = Path(output_dir) if output_dir is not None else Path(
            tempfile.mkdtemp(prefix="ml-viz-")
        )
        export_projections_to_cache(projections, output_dir)
        mlflow.log_metric("total_projection_files", len(projections))
        mlflow.log_param("projection_sample_size", len(sample))
        return {"projections": projections, "directory": output_dir}


def step_package_model(
    train_result: dict[str, Any],
    calibration_result: dict[str, Any],
    conformal_result: dict[str, float],
    model_name: str = "fraud-detector",
    model_version: str = "1",
    alpha: float = DEFAULT_ALPHA,
    git_commit: str = "unknown",
    data_sha256: str = "unknown",
    parent_run: bool = True,
) -> FraudDetectorModel:
    """Phase 8: build the self-contained pyfunc wrapper (§5.3)."""

    with mlflow.start_run(run_name="8_package", nested=parent_run):
        pyfunc_model = FraudDetectorModel(
            classifier=train_result["classifier"],
            preprocessor=train_result["preprocessor"],
            calibrator=calibration_result["calibrator"],
            calibration_method=calibration_result["method"],
            beta=float(train_result["beta"]),
            threshold_legit=float(conformal_result["threshold_legit"]),
            threshold_fraud=float(conformal_result["threshold_fraud"]),
            alpha=float(alpha),
            model_name=model_name,
            model_version=str(model_version),
            algorithm="xgboost-calibrated",
            trained_at=pd.Timestamp.now(tz="UTC").isoformat(),
            git_commit=git_commit,
            data_sha256=data_sha256,
        )
        mlflow.log_param("pyfunc_model_name", model_name)
        mlflow.log_param("pyfunc_version", model_version)
        mlflow.log_param("calibration_method", calibration_result["method"])
        mlflow.log_param("alpha", alpha)
        mlflow.log_param("beta", float(train_result["beta"]))
        return pyfunc_model


def step_register(
    pyfunc_model: FraudDetectorModel,
    input_example: pd.DataFrame,
    model_name: str = "fraud-detector",
    pipeline_run_id: str = "",
    viz_dir: Path | None = None,
    promote: bool = False,
    parent_run: bool = True,
) -> dict[str, Any]:
    """Phase 9: log the pyfunc artifact and register a version.

    The pipeline registers a ``challenger`` by default; ``champion`` is only
    moved by an explicit promotion once every quality gate has been signed off.
    """

    with mlflow.start_run(run_name="9_register", nested=parent_run):
        result = register_model(
            pyfunc_model,
            input_example,
            model_name=model_name,
            pipeline_run_id=pipeline_run_id,
            viz_dir=viz_dir,
            description=(
                "XGBoost + calibration + Mondrian conformal fraud detector "
                f"(alpha={pyfunc_model.alpha:.3f})"
            ),
            set_champion=promote,
            set_challenger=not promote,
        )
        mlflow.log_param("registered_model_name", result["name"])
        mlflow.log_param("registered_model_version", result["version"])
        mlflow.log_param("registered_model_alias", result["alias"])
        mlflow.set_tag("model_uri", result["model_uri"])
        return result
