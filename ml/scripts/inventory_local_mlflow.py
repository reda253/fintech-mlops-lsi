"""Inventorie les metadonnees SQLite et fichiers d'artefacts, en lecture seule."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def inventory(project_root: Path) -> dict:
    """Ne lit ni Sparkov ni le contenu des artefacts ; n'ecrit pas dans SQLite."""
    path = project_root / ".mlflow" / "fold_smoke" / "mlflow.db"
    result = {"source": ".mlflow/fold_smoke/mlflow.db", "read_only": True}
    if not path.is_file():
        return {**result, "status": "ABSENT"}
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        experiments = connection.execute(
            "SELECT experiment_id, name, lifecycle_stage FROM experiments ORDER BY experiment_id"
        ).fetchall()
        runs = connection.execute(
            "SELECT run_uuid, experiment_id, lifecycle_stage, artifact_uri FROM runs ORDER BY run_uuid"
        ).fetchall()
    counts = Counter(row[1] for row in runs)
    files, size, locations_missing, locations_remote = 0, 0, 0, 0
    run_metadata = []
    for run_id, experiment_id, stage, artifact_uri in runs:
        parsed = urlsplit(artifact_uri or "")
        n_files = 0
        if parsed.scheme == "file" and not parsed.netloc:
            artifact_path = Path(url2pathname(parsed.path))
            if artifact_path.is_dir():
                for item in artifact_path.rglob("*"):
                    if item.is_file():
                        n_files += 1
                        size += item.stat().st_size
            else:
                locations_missing += 1
        else:
            locations_remote += 1
        files += n_files
        run_metadata.append(
            {
                "run_id": run_id,
                "experiment_id": experiment_id,
                "lifecycle_stage": stage,
                "local_artifact_files": n_files,
            }
        )
    result.update(
        status="INVENTORIED",
        experiments=[
            {
                "experiment_id": ident,
                "name": name,
                "lifecycle_stage": stage,
                "runs": counts[ident],
            }
            for ident, name, stage in experiments
        ],
        experiment_count=len(experiments),
        run_count=len(runs),
        runs=run_metadata,
        local_artifact_files=files,
        local_artifact_bytes=size,
        missing_local_artifact_directories=locations_missing,
        remote_or_unknown_artifact_locations=locations_remote,
        migration_executed=False,
    )
    return result


def main() -> None:
    """Affiche l'inventaire et ecrit un rapport seulement si demande."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = inventory(args.project_root)
    payload = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
