"""Tests MLflow P2 sans reseau ni identifiants reels."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from ml import tracking_smoke as tracking
from ml.scripts.inventory_local_mlflow import inventory


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch, tmp_path):
    """Isole la configuration et interdit tout acces HTTP dans ces tests."""
    previous = {key: os.environ.get(key) for key in tracking.CONFIG_KEYS}
    for key in tracking.CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key in [
        "MLFLOW_HTTP_REQUEST_TIMEOUT",
        "MLFLOW_HTTP_REQUEST_MAX_RETRIES",
        "MLFLOW_ARTIFACT_UPLOAD_DOWNLOAD_TIMEOUT",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        requests.sessions.Session,
        "request",
        Mock(side_effect=AssertionError("Reseau interdit")),
    )
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_missing_uri_refuses_implicit_fallback(tmp_path):
    with pytest.raises(ValueError, match="URL exacte"):
        tracking.get_tracking_uri(project_root=tmp_path)
    assert not (tmp_path / ".mlflow").exists()


def test_local_fallback_requires_explicit_flag(tmp_path, capsys):
    uri = tracking.get_tracking_uri(project_root=tmp_path, allow_local_sqlite=True)
    assert uri == "sqlite:///" + (tmp_path / ".mlflow/fold_smoke/mlflow.db").as_posix()
    assert (tmp_path / ".mlflow/fold_smoke").is_dir()
    assert "SQLite local" in capsys.readouterr().out


def test_even_configured_sqlite_requires_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "sqlite:///:memory:")
    with pytest.raises(ValueError, match="SQLite refuse"):
        tracking.get_tracking_uri(project_root=tmp_path)


def test_cli_then_environment_then_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "MLFLOW_TRACKING_URI=https://dotenv.invalid\n", encoding="utf-8"
    )
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://environment.invalid")
    assert (
        tracking.get_tracking_uri("https://cli.invalid", project_root=tmp_path)
        == "https://cli.invalid"
    )
    assert (
        tracking.get_tracking_uri(project_root=tmp_path)
        == "https://environment.invalid"
    )
    monkeypatch.delenv("MLFLOW_TRACKING_URI")
    assert tracking.get_tracking_uri(project_root=tmp_path) == "https://dotenv.invalid"


def test_project_dotenv_has_priority_over_ml_dotenv(tmp_path):
    (tmp_path / "ml").mkdir()
    (tmp_path / ".env").write_text(
        "MLFLOW_TRACKING_URI=https://root.invalid\n", encoding="utf-8"
    )
    (tmp_path / "ml/.env").write_text(
        "MLFLOW_TRACKING_URI=https://ml.invalid\n", encoding="utf-8"
    )
    assert tracking.get_tracking_uri(project_root=tmp_path) == "https://root.invalid"


def test_dotenv_secrets_never_printed(tmp_path, capsys, caplog, monkeypatch):
    # Valeurs de test ephemeres : aucun vrai secret dans les sources.
    username, password = secrets.token_urlsafe(20), secrets.token_urlsafe(32)
    (tmp_path / ".env").write_text(
        "MLFLOW_TRACKING_URI=https://tracking.invalid\n"
        f"MLFLOW_TRACKING_USERNAME={username}\nMLFLOW_TRACKING_PASSWORD={password}\n"
        "UNRELATED_VARIABLE=not_loaded\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("UNRELATED_VARIABLE", raising=False)
    assert (
        tracking.get_tracking_uri(project_root=tmp_path) == "https://tracking.invalid"
    )
    assert os.environ["MLFLOW_TRACKING_PASSWORD"] == password
    assert "UNRELATED_VARIABLE" not in os.environ
    output = str(capsys.readouterr()) + caplog.text
    assert username not in output and password not in output
    assert "Basic" in output and "https://tracking.invalid" not in output


@pytest.mark.parametrize("mode", ["username_only", "password_only", "both_modes"])
def test_invalid_auth_configuration(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://tracking.invalid")
    if mode != "password_only":
        monkeypatch.setenv("MLFLOW_TRACKING_USERNAME", secrets.token_urlsafe(20))
    if mode != "username_only":
        monkeypatch.setenv("MLFLOW_TRACKING_PASSWORD", secrets.token_urlsafe(32))
    if mode == "both_modes":
        monkeypatch.setenv("MLFLOW_TRACKING_TOKEN", secrets.token_urlsafe(32))
    with pytest.raises(ValueError):
        tracking.get_tracking_uri(project_root=tmp_path)


def test_token_not_printed_and_server_not_replaced_by_sqlite(
    tmp_path, monkeypatch, capsys
):
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://tracking.invalid")
    monkeypatch.setenv("MLFLOW_TRACKING_TOKEN", token)
    assert (
        tracking.get_tracking_uri(project_root=tmp_path, allow_local_sqlite=True)
        == "https://tracking.invalid"
    )
    assert token not in str(capsys.readouterr())
    assert not (tmp_path / ".mlflow").exists()


@pytest.mark.parametrize(
    "form", ["credentials", "query", "fragment", "invalid_port", "unsupported"]
)
def test_rejects_unsafe_or_invalid_uri_without_echo(tmp_path, capsys, form):
    sentinel = secrets.token_urlsafe(24)
    uri = {
        "credentials": f"https://{sentinel}@tracking.invalid",
        "query": f"https://tracking.invalid?token={sentinel}",
        "fragment": f"https://tracking.invalid#{sentinel}",
        "invalid_port": f"https://tracking.invalid:{sentinel}",
        "unsupported": f"file:///{sentinel}",
    }[form]
    with pytest.raises(ValueError) as raised:
        tracking.get_tracking_uri(uri, project_root=tmp_path)
    assert sentinel not in str(raised.value) + str(capsys.readouterr())


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    monkeypatch.setattr(tracking, "MlflowClient", Mock(return_value=client))

    def smoke(uri, experiment, *, on_run_created):
        on_run_created("created_run_only")
        return "created_run_only"

    monkeypatch.setattr(tracking, "log_smoke_run", Mock(side_effect=smoke))
    stored = SimpleNamespace(
        data=SimpleNamespace(
            params={"smoke": "true"},
            metrics={"example_metric": 0.42},
            tags={"git_commit": "recorded-commit"},
        ),
        info=SimpleNamespace(status="FINISHED"),
    )
    deleted = SimpleNamespace(info=SimpleNamespace(lifecycle_stage="deleted"))
    client.get_run.side_effect = [stored, deleted]
    client.list_artifacts.return_value = [SimpleNamespace(path="note.txt")]

    def download(run_id, artifact, directory):
        path = Path(directory) / artifact
        path.write_text("hello from the tracking smoke script\n", encoding="utf-8")
        return str(path)

    client.download_artifacts.side_effect = download
    return client


def test_connectivity_creates_logs_reads_and_deletes_own_run(client):
    result = tracking.check_tracking_connection("https://tracking.invalid")
    assert (
        result["status"] == "PASS" and result["read_verified"] and result["run_deleted"]
    )
    tracking.log_smoke_run.assert_called_once()
    assert tracking.log_smoke_run.call_args.kwargs["experiment"] == "connectivity_check"
    assert result["artifact_download_verified"]
    client.download_artifacts.assert_called_once()
    client.delete_run.assert_called_once_with("created_run_only")
    assert client.get_run.call_count == 2


def test_original_template_keeps_params_metric_artifact_git_commit(monkeypatch):
    for name in [
        "set_tracking_uri",
        "set_experiment",
        "log_param",
        "log_metric",
        "set_tag",
        "log_text",
    ]:
        monkeypatch.setattr(tracking.mlflow, name, Mock())
    run = SimpleNamespace(info=SimpleNamespace(run_id="template_run"))
    monkeypatch.setattr(
        tracking.mlflow, "start_run", Mock(return_value=nullcontext(run))
    )
    monkeypatch.setattr(tracking, "_git_commit", lambda: "recorded-commit")
    callback = Mock()
    assert (
        tracking.log_smoke_run(
            "https://tracking.invalid", "connectivity_check", on_run_created=callback
        )
        == "template_run"
    )
    callback.assert_called_once_with("template_run")
    tracking.mlflow.set_experiment.assert_called_once_with("connectivity_check")
    tracking.mlflow.log_param.assert_any_call("smoke", "true")
    tracking.mlflow.log_metric.assert_called_once_with("example_metric", 0.42)
    tracking.mlflow.set_tag.assert_called_once_with("git_commit", "recorded-commit")
    tracking.mlflow.log_text.assert_called_once_with(
        "hello from the tracking smoke script\n", "note.txt"
    )


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_safe_and_do_not_delete_other_runs(client, status, capsys, caplog):
    sentinel = secrets.token_urlsafe(24)
    response = requests.Response()
    response.status_code = status

    def fail(*args, **kwargs):
        print(sentinel)
        logging.getLogger("mlflow").error(sentinel)
        raise requests.HTTPError(sentinel, response=response)

    tracking.log_smoke_run.side_effect = fail
    result = tracking.check_tracking_connection("https://tracking.invalid")
    assert result["status"] == "FAIL" and result["error"]["message"] == f"HTTP {status}"
    assert sentinel not in json.dumps(result) + str(capsys.readouterr()) + caplog.text
    client.delete_run.assert_not_called()


@pytest.mark.parametrize(
    "exc,category",
    [
        (TimeoutError(), "timeout"),
        (requests.exceptions.SSLError(), "tls"),
        (ConnectionError("getaddrinfo failed"), "dns"),
        (ConnectionRefusedError(), "connection"),
    ],
)
def test_transport_error_classification(client, exc, category):
    tracking.log_smoke_run.side_effect = exc
    result = tracking.check_tracking_connection("https://tracking.invalid")
    assert result["status"] == "FAIL" and result["error"]["category"] == category


def test_read_mismatch_still_deletes_created_run(client):
    client.get_run.side_effect = [
        SimpleNamespace(data=SimpleNamespace(params={}, metrics={})),
        SimpleNamespace(info=SimpleNamespace(lifecycle_stage="deleted")),
    ]
    result = tracking.check_tracking_connection("https://tracking.invalid")
    assert result["status"] == "FAIL" and result["run_deleted"]
    client.delete_run.assert_called_once_with("created_run_only")


def test_failed_cleanup_is_not_pass(client):
    client.delete_run.side_effect = requests.HTTPError(
        response=SimpleNamespace(status_code=403)
    )
    result = tracking.check_tracking_connection("https://tracking.invalid")
    assert result["status"] == "FAIL" and result["run_deleted"] is False
    assert result["cleanup_error"]["message"] == "HTTP 403"


def test_timeout_settings_and_logging_restored(client, monkeypatch):
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "77")
    previous = logging.root.manager.disable

    previous_smoke = tracking.log_smoke_run.side_effect

    def inspect_settings(*args, **kwargs):
        assert os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "3"
        assert os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] == "0"
        assert os.environ["MLFLOW_ARTIFACT_UPLOAD_DOWNLOAD_TIMEOUT"] == "3"
        return previous_smoke(*args, **kwargs)

    tracking.log_smoke_run.side_effect = inspect_settings
    assert (
        tracking.check_tracking_connection(
            "https://tracking.invalid", timeout_seconds=3
        )["status"]
        == "PASS"
    )
    assert os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "77"
    assert "MLFLOW_HTTP_REQUEST_MAX_RETRIES" not in os.environ
    assert "MLFLOW_ARTIFACT_UPLOAD_DOWNLOAD_TIMEOUT" not in os.environ
    assert logging.root.manager.disable == previous


def test_failed_artifact_download_still_deletes_own_run(client):
    client.download_artifacts.side_effect = requests.ConnectionError(
        "Connection refused"
    )
    result = tracking.check_tracking_connection("https://tracking.invalid")
    assert result["status"] == "FAIL" and result["run_deleted"]
    assert result["stage"] == "download_artifact_from_host"
    client.delete_run.assert_called_once_with("created_run_only")


def test_failed_write_after_creation_still_deletes_own_run(client):
    def fail(uri, experiment, *, on_run_created):
        on_run_created("created_run_only")
        raise requests.ConnectionError("Connection refused")

    tracking.log_smoke_run.side_effect = fail
    client.get_run.side_effect = [
        SimpleNamespace(info=SimpleNamespace(lifecycle_stage="deleted"))
    ]
    result = tracking.check_tracking_connection("https://tracking.invalid")
    assert result["status"] == "FAIL" and result["run_deleted"]
    client.delete_run.assert_called_once_with("created_run_only")


def test_inventory_missing_database_does_not_create_it(tmp_path):
    result = inventory(tmp_path)
    assert result["status"] == "ABSENT"
    assert not (tmp_path / ".mlflow").exists()


def test_inventory_counts_artifacts_without_changing_database(tmp_path):
    path = tmp_path / ".mlflow/fold_smoke/mlflow.db"
    path.parent.mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "note.txt").write_text("fixture", encoding="utf-8")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE experiments(experiment_id INTEGER, name TEXT, lifecycle_stage TEXT)"
        )
        connection.execute(
            "CREATE TABLE runs(run_uuid TEXT, experiment_id INTEGER, lifecycle_stage TEXT, artifact_uri TEXT)"
        )
        connection.execute("INSERT INTO experiments VALUES (1, 'fixture', 'active')")
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?)",
            ("fixture_run", 1, "active", artifacts.as_uri()),
        )
    before = path.read_bytes()
    result = inventory(tmp_path)
    assert path.read_bytes() == before
    assert result["experiment_count"] == 1 and result["run_count"] == 1
    assert result["local_artifact_files"] == 1
    assert result["local_artifact_bytes"] == len(b"fixture")
    assert result["migration_executed"] is False
