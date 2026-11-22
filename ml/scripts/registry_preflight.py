"""Registry-only D48 check, complementary to ml.scripts.d48_preflight.

Never reads the final source or journal, reserves a launch, or predicts.
Loading the pyfunc may populate MLflow's local artifact cache.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from ml.src.evaluation.final_artifacts import APPROVED_D48_MODEL_SHA256
from ml.tracking_smoke import get_tracking_uri


def verify_model_metadata(metadata: dict) -> None:
    """Only the candidate binding and alpha belong to this Registry check."""
    if metadata.get("model_sha256") != APPROVED_D48_MODEL_SHA256:
        raise ValueError("Les métadonnées ne désignent pas le candidat D48 approuvé")
    if not math.isclose(
        float(metadata.get("alpha", -1)), 0.02, abs_tol=1e-12, rel_tol=0
    ):
        raise ValueError("Alpha des métadonnées différent de 0.02")


def verify_registry(client, loader, metadata, *, version=None, alias="challenger"):
    """Read the version/tag/signature and load its pyfunc without prediction.

    The Registry protocol_sha256 describes D44 training, not D48 approval.
    Local protocol and authorization checks belong to ml.scripts.d48_preflight.
    """
    verify_model_metadata(metadata)
    model = (
        client.get_model_version("fraud-detector", str(version))
        if version is not None
        else client.get_model_version_by_alias("fraud-detector", alias)
    )
    if model.tags.get("source_model_sha256") != metadata["model_sha256"]:
        raise ValueError("Tag source_model_sha256 absent ou différent du candidat figé")
    if model.tags.get("status") != "PROVISIONAL":
        raise ValueError("Le modèle doit avoir le statut PROVISIONAL")
    if "champion" in (model.aliases or []):
        raise ValueError("Le modèle porte déjà l'alias champion")
    uri = f"models:/fraud-detector/{model.version}"
    loaded = loader(uri)
    signature = loaded.metadata.signature
    if signature is None or signature.inputs is None or signature.outputs is None:
        raise ValueError("Signature pyfunc explicite d'entrée et sortie requise")
    from mlflow.types.schema import Object

    customer = next(
        (item for item in signature.inputs if item.name == "customer"), None
    )
    if customer is None or not isinstance(customer.type, Object):
        raise ValueError("Signature d'entrée : champ customer imbriqué requis")
    wrapper = loaded.unwrap_python_model()
    if not math.isclose(float(wrapper.alpha), 0.02, rel_tol=0, abs_tol=1e-12):
        raise ValueError("Alpha du modèle différent de 0.02")
    return uri


def run(args) -> None:
    metadata = json.loads(args.model_metadata.read_text(encoding="utf-8"))
    verify_model_metadata(metadata)
    configured = (
        args.tracking_uri or os.environ.get("MLFLOW_TRACKING_URI", "")
    ).strip()
    if not configured or configured.lower().startswith("sqlite:"):
        raise ValueError(
            "Registry MLflow distant http:// ou https:// requis ; SQLite local interdit"
        )
    uri = get_tracking_uri(configured)
    if not uri.startswith(("http://", "https://")):
        raise ValueError(
            "Registry MLflow distant http:// ou https:// requis ; SQLite local interdit"
        )
    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(uri)
    selected = verify_registry(
        MlflowClient(),
        mlflow.pyfunc.load_model,
        metadata,
        version=args.version,
        alias=args.alias,
    )
    print(f"[OK] {selected} : tag, signature pyfunc et alpha=0.02")
    print("[OK] Registry seulement : aucune inférence ni réservation effectuée")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-metadata",
        type=Path,
        required=True,
        help="JSON metadata du candidat : clés model_sha256 et alpha (pas artifact_manifest.json)",
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
