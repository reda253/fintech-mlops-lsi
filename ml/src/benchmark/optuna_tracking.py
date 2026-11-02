"""Runs MLflow idempotents pour la recherche Optuna, sans donnees sources."""

import hashlib
import json
from functools import wraps

from mlflow import MlflowClient

from ml.tracking_smoke import _private_client_calls


def _private_request(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _private_client_calls(10):
            return function(*args, **kwargs)

    return wrapped


class SearchTracking:
    """Un parent par etude et un enfant par numero d'essai, reprise comprise."""

    @_private_request
    def __init__(self, uri, *, client=None):
        self.client = client if client is not None else MlflowClient(tracking_uri=uri)
        experiment = self.client.get_experiment_by_name("optuna_search")
        if experiment is not None and experiment.lifecycle_stage != "active":
            raise ValueError("L'experience optuna_search est supprimee.")
        self.experiment_id = (
            experiment.experiment_id
            if experiment
            else self.client.create_experiment("optuna_search")
        )

    def _existing(self, tag, value):
        runs = self.client.search_runs(
            [self.experiment_id],
            filter_string=f"tags.`{tag}` = '{value}'",
            max_results=2,
        )
        if len(runs) > 1:
            raise RuntimeError(
                "Plusieurs runs MLflow correspondent au meme identifiant."
            )
        return runs[0].info.run_id if runs else None

    @_private_request
    def parent(self, study, metadata):
        run_id = study.user_attrs.get("parent_run_id") or self._existing(
            "study_key", metadata["study_key"]
        )
        if run_id is None:
            tags = {
                **metadata,
                "mlflow.runName": f"{metadata['mode']}-{metadata['model']}",
            }
            run_id = self.client.create_run(self.experiment_id, tags=tags).info.run_id
        stored = self.client.get_run(run_id)
        if (
            stored.info.lifecycle_stage != "active"
            or stored.data.tags.get("study_key") != metadata["study_key"]
        ):
            raise RuntimeError("Run parent MLflow incompatible ou supprime.")
        study.set_user_attr("parent_run_id", run_id)
        return run_id

    @_private_request
    def child(self, study, number, parent_id, metadata):
        key = f"{metadata['study_key']}:{number}"
        run_id = study.user_attrs.get(f"child_{number}") or self._existing(
            "trial_key", key
        )
        if run_id is None:
            tags = {
                "git_commit": metadata["git_commit"],
                "config_hash": metadata["config_hash"],
                "mode": metadata["mode"],
                "trial_key": key,
                "mlflow.parentRunId": parent_id,
                "mlflow.runName": f"trial-{number:03d}",
            }
            run_id = self.client.create_run(self.experiment_id, tags=tags).info.run_id
        stored = self.client.get_run(run_id)
        if (
            stored.info.lifecycle_stage != "active"
            or stored.data.tags.get("trial_key") != key
        ):
            raise RuntimeError("Run enfant MLflow incompatible ou supprime.")
        study.set_user_attr(f"child_{number}", run_id)
        return run_id

    @_private_request
    def finish_trial(self, run_id, row):
        signature = hashlib.sha256(
            json.dumps(row, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        if self.client.get_run(run_id).data.tags.get("result_hash") == signature:
            return
        for key, value in row["params"].items():
            self.client.log_param(run_id, key, json.dumps(value))
        self.client.log_metric(run_id, "duration_seconds", row["seconds"])
        self.client.log_metric(run_id, "disk_free_bytes", row["disk_free_bytes"])
        if row["status"] == "COMPLETE":
            result = row["result"]
            for key in (
                "average_precision",
                "beta",
                "preparation_seconds",
                "fit_seconds",
                "predict_seconds",
            ):
                self.client.log_metric(run_id, key, result[key])
            for key, value in result["counts"].items():
                self.client.log_metric(run_id, key, value)
        for key in ("status", "reason", "exception_type", "errno", "winerror"):
            if row.get(key) is not None:
                self.client.set_tag(run_id, key, str(row[key]))
        self.client.set_terminated(
            run_id, status="FINISHED" if row["status"] == "COMPLETE" else "FAILED"
        )
        self.client.set_tag(run_id, "result_hash", signature)

    @_private_request
    def finish_parent(self, run_id, summary, *, status="FINISHED"):
        for key in (
            "attempted",
            "completed",
            "timeout_count",
            "failed_count",
            "elapsed_seconds",
        ):
            self.client.log_metric(run_id, key, summary[key])
        if summary["best_average_precision"] is not None:
            self.client.log_metric(
                run_id, "best_average_precision", summary["best_average_precision"]
            )
        self.client.set_tag(
            run_id, "timeout_alert", str(summary["timeout_alert"]).lower()
        )
        self.client.set_terminated(run_id, status=status)
