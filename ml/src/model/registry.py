"""Packaging and MLflow registry helpers (§5.3, T21c).

The pyfunc artifact must stay self-contained: the serving image does not contain
this repository, so ``log_model`` ships a minimal copy of the runtime modules:

* ``ml/src/model/{fraud_detector,calibration}.py``
* ``ml/src/preprocessing/pipeline.py``

Two top-level aliases (``preprocessing`` and ``model``) are also shipped so that
artifacts produced by P2's notebooks, which import ``preprocessing.pipeline``
instead of ``ml.src.preprocessing.pipeline``, still unpickle correctly.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mlflow
import mlflow.pyfunc
import pandas as pd
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient

SRC_DIR = Path(__file__).resolve().parents[1]  # ml/src

_RUNTIME_FILES = (
    "__init__.py",
    "model/__init__.py",
    "model/calibration.py",
    "model/fraud_detector.py",
    "preprocessing/__init__.py",
    "preprocessing/pipeline.py",
)

PIP_REQUIREMENTS = [
    "mlflow-skinny==3.17.2",
    "numpy==2.4.6",
    "pandas==3.0.6",
    "scikit-learn==1.9.1",
    "xgboost-cpu==3.2.0",
]

MODEL_MODULE = "ml.src.model.fraud_detector"


def stage_model_code(destination: Path | None = None) -> Path:
    """Copy the minimal runtime modules into an importable code directory.

    Returns the staging root. Pass its children (``ml``, ``preprocessing``,
    ``model``) to ``mlflow.pyfunc.log_model(code_paths=[...])``.
    """

    root = destination or Path(tempfile.mkdtemp(prefix="fraud-model-code-"))
    root = Path(root)
    canonical = root / "ml" / "src"
    for relative in _RUNTIME_FILES:
        source = SRC_DIR / relative
        target = canonical / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    # ``ml`` is a namespace package in the repository; make it explicit so that
    # ``import ml.src.model.fraud_detector`` always resolves in the artifact.
    (root / "ml" / "__init__.py").write_text("", encoding="utf-8")

    # Compatibility aliases for P2-era artifacts pickled as top-level modules.
    for package, filename in (("preprocessing", "pipeline.py"), ("model", "calibration.py")):
        target_dir = root / package
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "__init__.py").write_text("", encoding="utf-8")
        shutil.copy2(SRC_DIR / package / filename, target_dir / filename)

    return root


def code_paths_for(staging_root: Path) -> list[str]:
    """Return the three code paths MLflow should copy into the artifact."""

    return [
        str(staging_root / "ml"),
        str(staging_root / "preprocessing"),
        str(staging_root / "model"),
    ]


def sparkov_row_to_api_record(row: pd.Series) -> dict[str, Any]:
    """Convert one Sparkov row into the nested request contract used by the API."""

    timestamp = pd.to_datetime(row["trans_date_trans_time"])
    return {
        "transaction_id": str(uuid.uuid4()),
        "trans_datetime": timestamp.isoformat(),
        "amount": float(row["amt"]),
        "category": str(row["category"]),
        "merch_lat": float(row["merch_lat"]),
        "merch_long": float(row["merch_long"]),
        "customer": {
            "dob": str(pd.to_datetime(row["dob"]).date()),
            "gender": str(row["gender"]),
            "city_pop": int(row["city_pop"]),
            "lat": float(row["lat"]),
            "long": float(row["long"]),
            "state": str(row["state"]),
        },
    }


def build_input_example(sample_df: pd.DataFrame, n_rows: int = 2) -> pd.DataFrame:
    """Build a nested input example (customer struct) from Sparkov rows."""

    if sample_df.empty:
        raise ValueError("Un exemple d'entree non vide est requis.")
    rows = sample_df.head(n_rows)
    return pd.DataFrame(
        [sparkov_row_to_api_record(row) for _, row in rows.iterrows()]
    )


def _registered_version(client: MlflowClient, model_name: str, model_info: Any) -> str:
    version = getattr(model_info, "registered_model_version", None)
    if version not in (None, ""):
        return str(version)
    versions = client.search_model_versions(f"name='{model_name}'")
    if not versions:
        raise RuntimeError(f"Aucune version enregistree pour {model_name}.")
    return str(max(int(item.version) for item in versions))


def register_model(
    pyfunc_model: Any,
    input_example: pd.DataFrame,
    *,
    model_name: str = "fraud-detector",
    pipeline_run_id: str = "",
    viz_dir: Path | None = None,
    description: str | None = None,
    set_champion: bool = True,
    extra_tags: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Log, register and optionally alias the packaged fraud detector.

    Must be called inside an active MLflow run: the run becomes the model
    version source, which is where visualization artifacts are attached.

    ``set_champion=False`` registers a provisional version without moving the
    ``champion`` alias, so a candidate can be validated before promotion.
    """

    active_run = mlflow.active_run()
    if active_run is None:
        raise RuntimeError("register_model() doit etre appele dans un run MLflow actif.")

    output_example = pyfunc_model.predict(None, input_example)
    signature = infer_signature(input_example, output_example)

    if viz_dir is not None and Path(viz_dir).is_dir():
        mlflow.log_artifacts(str(viz_dir), artifact_path="viz")

    staging_root = stage_model_code()
    try:
        model_info = mlflow.pyfunc.log_model(
            name="model",
            python_model=pyfunc_model,
            signature=signature,
            input_example=input_example,
            code_paths=code_paths_for(staging_root),
            registered_model_name=model_name,
            metadata=pyfunc_model.to_metadata(),
            pip_requirements=PIP_REQUIREMENTS,
        )
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    client = MlflowClient()
    version = _registered_version(client, model_name, model_info)
    metadata = pyfunc_model.to_metadata()

    tags = {
        "git_commit": str(metadata.get("git_commit", "unknown")),
        "data_sha256": str(metadata.get("data_sha256", "unknown")),
        "alpha": str(metadata.get("alpha")),
        "beta": str(metadata.get("beta")),
        "algorithm": str(metadata.get("algorithm", "xgboost-calibrated")),
        "calibration": str(metadata.get("calibration", "none")),
        "pipeline_run_id": pipeline_run_id or active_run.info.run_id,
        "trained_at": str(metadata.get("trained_at", "unknown")),
    }
    if extra_tags:
        tags.update({key: str(value) for key, value in extra_tags.items()})
    for key, value in tags.items():
        client.set_model_version_tag(model_name, version, key, value)
    if description:
        client.update_model_version(model_name, version, description=description)
    if set_champion:
        client.set_registered_model_alias(model_name, "champion", version)

    return {
        "name": model_name,
        "version": version,
        "alias": "champion" if set_champion else None,
        "model_uri": f"models:/{model_name}/{version}",
        "run_id": active_run.info.run_id,
        "registered_at": datetime.now(UTC).isoformat(),
        "tags": tags,
        "signature": signature.to_dict(),
    }


def load_tracking_uri(tracking_uri: str | None) -> None:
    """Set the tracking URI only when explicitly provided."""

    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
