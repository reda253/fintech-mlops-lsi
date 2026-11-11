"""Publication MLflow des agrégats sauvegardés, sans accès aux données sources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ml.tracking_smoke import _private_client_calls, get_tracking_uri

ARTIFACTS = (
    "final_metrics.json",
    "final_report.md",
    "fairness_groups.csv",
    "bootstrap_intervals.json",
    "artifact_manifest.json",
)


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_saved(output: Path) -> dict:
    manifest = json.loads(
        (output / "artifact_manifest.json").read_text(encoding="utf-8")
    )
    for name in ARTIFACTS[:-1]:
        if manifest["artifacts"][name] != _sha(output / name):
            raise ValueError(f"Empreinte différente pour {name}")
    return json.loads((output / "final_metrics.json").read_text(encoding="utf-8"))


def publish_saved(output: Path, tracking_uri: str | None = None) -> dict:
    """Publie ou reprend le run associé à ces fichiers, sans ouvrir la source."""
    import mlflow

    result = verify_saved(output)
    status_path = output / "mlflow_status.json"
    previous = (
        json.loads(status_path.read_text(encoding="utf-8"))
        if status_path.exists()
        else {}
    )
    state = {
        "status": "pending",
        "run_id": previous.get("run_id"),
        "backend_sha256": previous.get("backend_sha256"),
    }
    try:
        uri = get_tracking_uri(tracking_uri)
        uri_hash = hashlib.sha256(uri.encode("utf-8")).hexdigest()
        if state["run_id"] and state["backend_sha256"] != uri_hash:
            raise ValueError("Le run sauvegardé appartient à un autre backend MLflow")
        state["backend_sha256"] = uri_hash
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("final_evaluation")
        run_args = (
            {"run_id": state["run_id"]}
            if state["run_id"]
            else {"run_name": "candidate_final_evaluation"}
        )
        with _private_client_calls(30), mlflow.start_run(**run_args) as run:
            state.update(status="running", run_id=run.info.run_id)
            status_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            mlflow.set_tags(
                {
                    "model_status": "provisional",
                    "model_sha256": result["model_sha256"],
                    "source_sha256": result.get("source_sha256") or "synthetic",
                    "reference_sha256": result["reference_sha256"],
                    "evaluation_script_sha256": result["evaluation_script_sha256"],
                    "metrics_module_sha256": result["metrics_module_sha256"],
                    "tracking_module_sha256": result["tracking_module_sha256"],
                    "publication_module_sha256": _sha(Path(__file__)),
                    "artifact_manifest_sha256": _sha(output / "artifact_manifest.json"),
                    **(
                        {"code_revision": result["code_revision"]}
                        if result.get("code_revision")
                        else {}
                    ),
                    **{
                        f"gate_{key}": value["status"]
                        for key, value in result["quality_gates"].items()
                    },
                }
            )
            mlflow.log_params(
                {
                    "alpha": result["alpha"],
                    "bootstrap_seed": result["bootstrap"]["seed"],
                    "bootstrap_resamples": result["bootstrap"]["resamples"],
                    "scope": result["scope"],
                    **{
                        f"version_{name}": value
                        for name, value in result.get("versions", {}).items()
                    },
                }
            )
            metrics = {
                key: value
                for key, value in result["overall"].items()
                if isinstance(value, (float, int)) and not isinstance(value, bool)
            }
            if result["latency"].get("p95_ms") is not None:
                metrics["latency_p95_ms"] = result["latency"]["p95_ms"]
                metrics["latency_p50_ms"] = result["latency"]["p50_ms"]
            intervals = json.loads(
                (output / "bootstrap_intervals.json").read_text(encoding="utf-8")
            )
            for key, info in intervals["overall"].items():
                if info["ci95"] is not None:
                    metrics[f"{key}_ci95_low"] = info["ci95"][0]
                    metrics[f"{key}_ci95_high"] = info["ci95"][1]
            for index, group in enumerate(result["fairness"]):
                for key in (
                    "n",
                    "frauds",
                    "legitimate",
                    "recall_point_prediction",
                    "false_positive_rate_point_prediction",
                    "review_rate",
                ):
                    value = group.get(key)
                    if value is not None:
                        metrics[f"group_{index}_{key}"] = value
            mlflow.log_metrics(metrics)
            for name in ARTIFACTS:
                mlflow.log_artifact(str(output / name))
        state["status"] = "published"
        state.pop("error_type", None)
    except Exception as exc:  # noqa: BLE001 - preserve saved results for any MLflow failure
        state.update(status="failed", error_type=type(exc).__name__)
        status_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return state
    status_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state
