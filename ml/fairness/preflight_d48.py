"""Registry-only D48 check, complementary to ml.scripts.d48_preflight.

Never reads the final source or journal, reserves a launch, or predicts.
Loading the pyfunc may populate MLflow's local artifact cache.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from ml.src.evaluation.final_artifacts import APPROVED_D48_MODEL_SHA256
from ml.tracking_smoke import get_tracking_uri


def verify_manifest(manifest: dict) -> None:
    """Only the candidate binding and alpha belong to this Registry check."""
    if manifest.get("model_sha256") != APPROVED_D48_MODEL_SHA256:
        raise ValueError("Le manifeste ne désigne pas le candidat D48 approuvé")
    if not math.isclose(
        float(manifest.get("alpha", -1)), 0.02, abs_tol=1e-12, rel_tol=0
    ):
        raise ValueError("Alpha du manifeste différent de 0.02")


def verify_registry(client, loader, manifest, *, version=None, alias="challenger"):
    """Read the version/tag/signature and load its pyfunc without prediction.

    The Registry protocol_sha256 describes D44 training, not D48 approval.
    Local protocol and authorization checks belong to ml.scripts.d48_preflight.
    """
    verify_manifest(manifest)
    model = (
        client.get_model_version("fraud-detector", str(version))
        if version is not None
        else client.get_model_version_by_alias("fraud-detector", alias)
    )
    if model.tags.get("source_model_sha256") != manifest["model_sha256"]:
        raise ValueError("Tag source_model_sha256 absent ou différent du candidat figé")
    uri = f"models:/fraud-detector/{model.version}"
    loaded = loader(uri)
    signature = loaded.metadata.signature
    if signature is None or signature.inputs is None or signature.outputs is None:
        raise ValueError("Signature pyfunc explicite d'entrée et sortie requise")
    wrapper = loaded.unwrap_python_model()
    if not math.isclose(float(wrapper.alpha), 0.02, rel_tol=0, abs_tol=1e-12):
        raise ValueError("Alpha du modèle différent de 0.02")
    return uri


def run(args) -> None:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    verify_manifest(manifest)
    uri = get_tracking_uri(args.tracking_uri)
    if not uri.startswith(("http://", "https://")):
        raise ValueError("Registry serveur requis ; repli SQLite interdit")
    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(uri)
    selected = verify_registry(
        MlflowClient(),
        mlflow.pyfunc.load_model,
        manifest,
        version=args.version,
        alias=args.alias,
    )
    print(f"[OK] {selected} : tag, signature pyfunc et alpha=0.02")
    print("[OK] Registry seulement : aucune inférence ni réservation effectuée")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Provenance du candidat : model_sha256 et alpha ; pas l'autorisation",
    )
    select = parser.add_mutually_exclusive_group()
    select.add_argument("--version")
    select.add_argument("--alias", default="challenger")
    parser.add_argument("--tracking-uri")
    args = parser.parse_args(argv)
    try:
        run(args)
    except Exception as exc:  # noqa: BLE001 -- mask credentials at the CLI boundary.
        if isinstance(exc, (ValueError, FileNotFoundError)):
            print(f"[FAIL] {exc}")
        else:
            print(
                f"[FAIL] Contrôle Registry impossible ({type(exc).__name__}) ; détail masqué"
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
