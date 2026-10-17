"""Configuration MLflow P2, sans adresse supposee ni secret affiche."""

from __future__ import annotations

import argparse
import io
import logging
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.parse import urlsplit

import mlflow
from dotenv import dotenv_values
from mlflow import MlflowClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_KEYS = (
    "MLFLOW_TRACKING_URI",
    "MLFLOW_TRACKING_USERNAME",
    "MLFLOW_TRACKING_PASSWORD",
    "MLFLOW_TRACKING_TOKEN",
)


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def log_smoke_run(
    tracking_uri: str,
    experiment: str = "smoke",
    *,
    on_run_created=None,
) -> str:
    """Conserve le template P3 ; le callback permet le nettoyage du diagnostic."""
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name="tracking-smoke") as run:
        if on_run_created is not None:
            on_run_created(run.info.run_id)
        mlflow.log_param("smoke", "true")
        mlflow.log_param("source", "p3-tracking-script")
        mlflow.log_metric("example_metric", 0.42)
        mlflow.set_tag("git_commit", _git_commit())
        mlflow.log_text("hello from the tracking smoke script\n", "note.txt")
        return run.info.run_id


def get_tracking_uri(
    tracking_uri: str | None = None,
    *,
    allow_local_sqlite: bool = False,
    project_root: Path = PROJECT_ROOT,
) -> str:
    """Resout CLI > environnement > .env racine > ml/.env.

    Ne choisit jamais une adresse de serveur par defaut. SQLite exige toujours
    une autorisation explicite. Les identifiants restent dans l'environnement
    et sont lus directement par MLflow ; ils ne sont ni retournes ni affiches.
    """
    for relative in (".env", "ml/.env"):
        path = project_root / relative
        if path.is_file():
            values = dotenv_values(path, interpolate=False)
            for key in CONFIG_KEYS:
                if key not in os.environ and values.get(key):
                    os.environ[key] = values[key]

    uri = (tracking_uri or os.environ.get("MLFLOW_TRACKING_URI", "")).strip()
    if not uri:
        if not allow_local_sqlite:
            raise ValueError(
                "MLFLOW_TRACKING_URI absente : demander l'URL exacte a Omar. "
                "Le repli SQLite exige --allow-local-sqlite."
            )
        local_dir = project_root / ".mlflow" / "fold_smoke"
        local_dir.mkdir(parents=True, exist_ok=True)
        uri = "sqlite:///" + (local_dir / "mlflow.db").as_posix()

    try:
        parsed = urlsplit(uri)
        embedded_credentials = (
            parsed.username is not None or parsed.password is not None
        )
        invalid_http = parsed.scheme in {"http", "https"} and (
            not parsed.hostname or parsed.port == 0
        )
    except ValueError:
        raise ValueError("URI MLflow invalide ; valeur masquee.") from None
    if embedded_credentials or parsed.query or parsed.fragment:
        raise ValueError(
            "URI MLflow refusee : utiliser les variables d'authentification, "
            "sans identifiants, parametres ni fragment dans l'URI."
        )
    if parsed.scheme == "sqlite":
        if not allow_local_sqlite:
            raise ValueError("SQLite refuse sans --allow-local-sqlite explicite.")
        if not uri.startswith("sqlite:///") or parsed.netloc or not parsed.path:
            raise ValueError("URI SQLite invalide ; valeur masquee.")
        print(
            "MLflow : backend SQLite local, explicitement autorise (pas le serveur P3)."
        )
    elif parsed.scheme in {"http", "https"} and not invalid_http:
        username = os.environ.get("MLFLOW_TRACKING_USERNAME", "")
        password = os.environ.get("MLFLOW_TRACKING_PASSWORD", "")
        token = os.environ.get("MLFLOW_TRACKING_TOKEN", "")
        if token and (username or password):
            raise ValueError(
                "Choisir Basic OU token, pas les deux modes simultanement."
            )
        if not token and bool(username) != bool(password):
            raise ValueError(
                "Authentification Basic incomplete : username ET password requis."
            )
        auth = "token" if token else "Basic" if username else "non configuree"
        print(
            f"MLflow : backend serveur configure ; authentification {auth}. URI masquee."
        )
    else:
        raise ValueError(
            "URI MLflow refusee : serveur HTTP(S) ou SQLite explicite attendu."
        )
    return uri


@contextmanager
def _private_client_calls(timeout_seconds: int):
    """Borne les appels et masque les traces tierces susceptibles de contenir un secret.

    Reserve au diagnostic CLI mono-thread : les reglages et sorties sont
    restaures, meme en cas d'erreur. La verification TLS n'est jamais desactivee.
    """
    settings = {
        "MLFLOW_HTTP_REQUEST_TIMEOUT": str(timeout_seconds),
        "MLFLOW_ARTIFACT_UPLOAD_DOWNLOAD_TIMEOUT": str(timeout_seconds),
        "MLFLOW_HTTP_REQUEST_MAX_RETRIES": "0",
    }
    previous = {key: os.environ.get(key) for key in settings}
    disabled = logging.root.manager.disable
    try:
        os.environ.update(settings)
        logging.disable(logging.CRITICAL)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            yield
    finally:
        logging.disable(disabled)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _safe_error(exc: Exception) -> dict:
    """Classe une erreur sans publier le message brut, l'URL ou les headers."""
    causes = []
    current = exc
    while current is not None and id(current) not in {id(item) for item in causes}:
        causes.append(current)
        current = current.__cause__ or current.__context__
    text = " ".join(f"{type(item).__name__}: {item}" for item in causes).lower()
    code = getattr(exc, "error_code", "")
    status = next(
        (
            getattr(getattr(item, "response", None), "status_code", None)
            for item in causes
            if getattr(getattr(item, "response", None), "status_code", None)
        ),
        None,
    )
    if status is None:
        match = re.search(
            r"(?:status(?:[_ ]code)?|response code)\D{0,8}([45]\d\d)", text
        )
        status = int(match[1]) if match else None
    if code in {"UNAUTHENTICATED", "PERMISSION_DENIED"}:
        status = status or {"UNAUTHENTICATED": 401, "PERMISSION_DENIED": 403}[code]
    if status:
        category, detail = "http", f"HTTP {status}"
    elif "ssl" in text or "certificate" in text or "certificat" in text:
        category, detail = "tls", "Erreur TLS/certificat"
    elif "timeout" in text or "timed out" in text:
        category, detail = "timeout", "Delai de connexion ou de lecture depasse"
    elif any(
        word in text for word in ("getaddrinfo", "nameresolution", "name resolution")
    ):
        category, detail = "dns", "Resolution DNS impossible"
    elif "connection" in text or "connexion" in text:
        category, detail = "connection", "Connexion impossible ou refusee"
    else:
        category, detail = "client", "Erreur du client MLflow ; detail brut masque"
    return {
        "category": category,
        "exception_type": type(exc).__name__,
        "message": detail,
    }


def check_tracking_connection(tracking_uri: str, *, timeout_seconds: int = 10) -> dict:
    """Cree, relit puis supprime logiquement un run de connectivity_check.

    Aucun jeu de donnees ni modele n'est utilise. Seul le run cree par cet
    appel peut etre supprime. Un echec de nettoyage est rapporte explicitement.
    """
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds doit etre un entier strictement positif.")
    result = {"status": "FAIL", "experiment": "connectivity_check", "stage": "connect"}
    client, run_id = None, None
    previous_uri = mlflow.get_tracking_uri()

    def capture_run(created_id):
        nonlocal run_id
        run_id = created_id
        result["run_id"] = run_id

    with _private_client_calls(timeout_seconds):
        try:
            client = MlflowClient(tracking_uri=tracking_uri)
            result["stage"] = "write"
            log_smoke_run(
                tracking_uri,
                experiment="connectivity_check",
                on_run_created=capture_run,
            )
            result["stage"] = "read"
            stored = client.get_run(run_id)
            if (
                stored.data.params.get("smoke") != "true"
                or stored.data.metrics.get("example_metric") != 0.42
                or not stored.data.tags.get("git_commit")
                or stored.info.status != "FINISHED"
            ):
                raise ValueError("Le run relu ne correspond pas aux valeurs envoyees.")
            result["read_verified"] = True
            result["stage"] = "download_artifact_from_host"
            if "note.txt" not in {item.path for item in client.list_artifacts(run_id)}:
                raise ValueError("Artefact note.txt absent du run.")
            with tempfile.TemporaryDirectory() as directory:
                local_path = client.download_artifacts(run_id, "note.txt", directory)
                if (
                    Path(local_path).read_text(encoding="utf-8")
                    != "hello from the tracking smoke script\n"
                ):
                    raise ValueError("L'artefact telecharge differe du contenu envoye.")
            result["artifact_download_verified"] = True
        except Exception as exc:  # noqa: BLE001 -- ne jamais exposer une exception tierce brute
            result["error"] = _safe_error(exc)
        finally:
            if run_id is not None:
                try:
                    client.delete_run(run_id)
                    deleted = client.get_run(run_id).info.lifecycle_stage == "deleted"
                    if not deleted:
                        raise ValueError(
                            "La suppression logique du run n'est pas confirmee."
                        )
                    result["run_deleted"] = True
                except Exception as exc:  # noqa: BLE001 -- rapport de nettoyage sans secret
                    result["run_deleted"] = False
                    result["cleanup_error"] = _safe_error(exc)
            mlflow.set_tracking_uri(previous_uri)
    if (
        result.get("read_verified")
        and result.get("artifact_download_verified")
        and result.get("run_deleted")
        and "error" not in result
    ):
        result.update(status="PASS", stage="complete")
    return result


def main() -> None:
    """Execute le template P3 avec la meme resolution d'URI que le smoke P2."""
    parser = argparse.ArgumentParser(description="Log a smoke run to MLflow.")
    parser.add_argument("--tracking-uri")
    parser.add_argument("--allow-local-sqlite", action="store_true")
    parser.add_argument("--experiment", default="smoke")
    args = parser.parse_args()
    uri = get_tracking_uri(
        args.tracking_uri, allow_local_sqlite=args.allow_local_sqlite
    )
    run_id = log_smoke_run(uri, args.experiment)
    print(f"Logged run {run_id}; backend annonce ci-dessus, URI masquee.")


if __name__ == "__main__":
    main()
