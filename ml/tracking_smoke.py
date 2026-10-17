"""Reusable tracking template for P2 and the ML pipeline (§5.2, §4.12).

The same pattern is used by every pipeline step: set the tracking URI, pick an
experiment, log params/metrics/tags/artifacts, and return the run id.
"""

from __future__ import annotations

import argparse
import os
import subprocess

import mlflow

DEFAULT_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def log_smoke_run(tracking_uri: str, experiment: str = "smoke") -> str:
    """Log one tiny run and return its run_id. Proves the server works end to end."""
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name="tracking-smoke") as run:
        mlflow.log_param("smoke", "true")
        mlflow.log_param("source", "p3-tracking-script")
        mlflow.log_metric("example_metric", 0.42)
        mlflow.set_tag("git_commit", _git_commit())
        mlflow.log_text("hello from the tracking smoke script\n", "note.txt")
        return run.info.run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Log a smoke run to MLflow.")
    parser.add_argument("--tracking-uri", default=DEFAULT_TRACKING_URI)
    parser.add_argument("--experiment", default="smoke")
    args = parser.parse_args()
    run_id = log_smoke_run(args.tracking_uri, args.experiment)
    print(f"Logged run {run_id} to {args.tracking_uri}")


if __name__ == "__main__":
    main()
