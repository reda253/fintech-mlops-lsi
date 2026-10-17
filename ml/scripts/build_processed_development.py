"""Regenere l'artefact de consultation development, sans classifieur."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "ml" / "src"))

from data.load_data import load_training_dataset, split_chronologically
from preprocessing.pipeline import (
    build_preprocessing_pipeline,
    split_features_target,
)


def sha256_file(path: Path) -> str:
    """Calcule le hash d'un fichier par blocs."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact(
    project_root: Path = PROJECT_ROOT, batch_size: int = 10_000
) -> dict[str, int | str]:
    """Ajuste sur development et ecrit le CSV par blocs sans toucher la source."""

    if batch_size <= 0:
        raise ValueError("batch_size doit etre strictement positif.")
    source = project_root / "data" / "raw" / "fraudTrain.csv"
    if not source.is_file():
        raise FileNotFoundError("Place fraudTrain.csv dans data/raw/.")
    started = perf_counter()
    print("[1/5] Calcul de l'empreinte de fraudTrain.csv...", flush=True)
    source_hash = sha256_file(source)
    print("[2/5] Chargement des champs autorises et tri chronologique...", flush=True)
    data, _ = load_training_dataset(source)
    development = split_chronologically(data)["development"]
    X, y = split_features_target(development)
    del data, development

    print(
        f"[3/5] Ajustement du preprocessing sur {len(X):,} lignes development...",
        flush=True,
    )
    pipeline = build_preprocessing_pipeline()
    pipeline.fit(X)
    names = pipeline.get_feature_names_out().tolist()
    feature_list_path = project_root / "docs" / "feature_list_p2.csv"
    feature_list = pd.read_csv(feature_list_path)
    expected = feature_list.loc[
        feature_list["section"].eq("pipeline_output"), "output_name"
    ].tolist()
    if names != expected:
        raise ValueError("Noms ou ordre differents de docs/feature_list_p2.csv.")

    print(f"[4/5] Export CSV : {len(names)} features + cible...", flush=True)
    output_dir = project_root / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "sparkov_development_preprocessed_strict.csv"
    with tempfile.NamedTemporaryFile(
        dir=output_dir, prefix=".development_", suffix=".tmp", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        for start in range(0, len(X), batch_size):
            stop = min(start + batch_size, len(X))
            values = pipeline.transform(X.iloc[start:stop])
            if not np.isfinite(values).all():
                raise ValueError("Valeurs non finies dans le preprocessing.")
            frame = pd.DataFrame(values, columns=names)
            frame["is_fraud"] = y.iloc[start:stop].to_numpy()
            frame.to_csv(
                temporary_path, mode="w" if start == 0 else "a",
                header=start == 0, index=False, float_format="%.9g",
                lineterminator="\n",
            )
            if (start // batch_size + 1) % 10 == 0 or stop == len(X):
                print(
                    f"  Lignes exportees : {stop:,}/{len(X):,} "
                    f"({100 * stop / len(X):.1f} %)",
                    flush=True,
                )
        print("[5/5] Verification de la source et actualisation des rapports...", flush=True)
        if sha256_file(source) != source_hash:
            raise RuntimeError("La source a change pendant la generation.")
        temporary_path.replace(output)
    except PermissionError as exc:
        raise PermissionError(
            "CSV verrouille : ferme son affichage dans Excel/Jupyter et relance."
        ) from exc
    finally:
        temporary_path.unlink(missing_ok=True)

    reports = project_root / "reports"
    reports.mkdir(exist_ok=True)
    versions = {"python": platform.python_version()}
    for package in [
        "pandas", "numpy", "scikit-learn", "xgboost", "statsmodels", "nbstripout"
    ]:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            continue
    versions_path = reports / "dependency_versions_p2.json"
    versions_path.write_text(json.dumps(versions, indent=2) + "\n", encoding="utf-8")

    hash_path = reports / "sha256_p2.csv"
    hashes = {}
    if hash_path.is_file():
        previous = pd.read_csv(hash_path)
        hashes.update({
            str(row.file).replace("\\", "/"): row.sha256
            for row in previous.itertuples(index=False)
        })
    for path in [source, output, feature_list_path, versions_path]:
        hashes[path.relative_to(project_root).as_posix()] = sha256_file(path)
    schema = project_root / "docs" / "transaction_schema_p2.md"
    if schema.is_file():
        hashes[schema.relative_to(project_root).as_posix()] = sha256_file(schema)
    pd.DataFrame([
        {"file": name, "sha256": digest}
        for name, digest in sorted(hashes.items())
    ]).to_csv(hash_path, index=False, lineterminator="\n")

    result = {
        "source": source.relative_to(project_root).as_posix(),
        "zone": "development", "rows": len(X), "features": len(names),
        "columns_with_target": len(names) + 1,
        "output": output.relative_to(project_root).as_posix(),
        "sha256": hashes[output.relative_to(project_root).as_posix()],
        "usage": "Consultation only; refit preprocessing within each benchmark fold.",
    }
    print(json.dumps(result, indent=2), flush=True)
    print(f"Termine en {perf_counter() - started:.1f} secondes.", flush=True)
    return result


def main() -> None:
    """Lance la regeneration depuis le dossier du projet."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=10_000)
    args = parser.parse_args()
    build_artifact(batch_size=args.batch_size)


if __name__ == "__main__":
    main()
