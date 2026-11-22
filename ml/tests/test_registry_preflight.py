"""Registry-only checks: synthetic metadata and mocked MLflow, no network."""

import importlib
import json
from types import SimpleNamespace

import pytest
from mlflow.types.schema import ColSpec, Object, Property, Schema

from ml.scripts import registry_preflight as preflight


def manifest():
    return {"model_sha256": preflight.APPROVED_D48_MODEL_SHA256, "alpha": 0.02}


def registry_objects():
    version = SimpleNamespace(
        version="1",
        aliases=["challenger"],
        tags={
            "source_model_sha256": preflight.APPROVED_D48_MODEL_SHA256,
            "status": "PROVISIONAL",
            "protocol_sha256": "cf7bcf0a" + "0" * 56,
        },
    )
    loaded = SimpleNamespace(
        metadata=SimpleNamespace(
            signature=SimpleNamespace(
                inputs=Schema(
                    [ColSpec(Object([Property("dob", "string")]), "customer")]
                ),
                outputs=Schema([ColSpec("double", "score")]),
            )
        ),
        unwrap_python_model=lambda: SimpleNamespace(alpha=0.02),
    )
    return version, loaded


def test_manifest_frozen_values():
    preflight.verify_model_metadata(manifest())
    for key, value in (("alpha", 0.05), ("model_sha256", "b" * 64)):
        with pytest.raises(ValueError):
            preflight.verify_model_metadata({**manifest(), key: value})


@pytest.mark.parametrize("bad", ["tag", "signature", "alpha"])
def test_registry_rejects_inconsistent_model(bad):
    version, loaded = registry_objects()
    if bad == "tag":
        version.tags = {}
    elif bad == "signature":
        loaded.metadata.signature = None
    else:
        loaded.unwrap_python_model = lambda: SimpleNamespace(alpha=0.05)
    client = SimpleNamespace(get_model_version_by_alias=lambda *a: version)
    with pytest.raises(ValueError):
        preflight.verify_registry(client, lambda _: loaded, manifest())


def test_registry_loads_signature_without_predict_or_d48_protocol_tag():
    version, loaded = registry_objects()
    calls = []
    client = SimpleNamespace(get_model_version=lambda *a: version)

    def load(uri):
        calls.append(uri)
        return loaded

    assert (
        preflight.verify_registry(client, load, manifest(), version="1")
        == "models:/fraud-detector/1"
    )
    assert calls == ["models:/fraud-detector/1"]


def test_registry_validates_binding_before_loading():
    with pytest.raises(ValueError, match="candidat"):
        preflight.verify_registry(
            None,
            lambda _: pytest.fail("must not load"),
            {**manifest(), "model_sha256": "b" * 64},
        )


def test_registry_cli_does_not_read_source_journal_or_authorization(
    tmp_path, monkeypatch, capsys
):
    import mlflow
    import mlflow.tracking

    from ml.scripts import d48_preflight

    metadata = tmp_path / "candidate-provenance.json"
    metadata.write_text(json.dumps(manifest()), encoding="utf-8")
    version, loaded = registry_objects()
    monkeypatch.setattr(
        preflight, "get_tracking_uri", lambda _: "http://synthetic.invalid"
    )
    monkeypatch.setattr(mlflow, "set_tracking_uri", lambda _: None)
    monkeypatch.setattr(
        importlib.import_module("mlflow.tracking"),
        "MlflowClient",
        lambda: SimpleNamespace(get_model_version=lambda *a: version),
    )
    monkeypatch.setattr(
        importlib.import_module("mlflow.pyfunc"), "load_model", lambda _: loaded
    )
    monkeypatch.setattr(
        d48_preflight,
        "preflight",
        lambda *a: pytest.fail("local phase must stay separate"),
    )
    assert (
        preflight.main(
            [
                "--tracking-uri",
                "http://synthetic.invalid",
                "--model-metadata",
                str(metadata),
                "--version",
                "1",
            ]
        )
        == 0
    )
    assert "Registry seulement" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == [metadata]


@pytest.mark.parametrize("uri", ["sqlite:///synthetic.db", "file:///synthetic"])
def test_registry_refuses_local_store(tmp_path, monkeypatch, uri):
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(manifest()), encoding="utf-8")
    monkeypatch.setattr(preflight, "get_tracking_uri", lambda _: uri)
    assert (
        preflight.main(
            [
                "--tracking-uri",
                "http://synthetic.invalid",
                "--model-metadata",
                str(metadata),
            ]
        )
        == 1
    )


def test_registry_error_is_masked(tmp_path, monkeypatch, capsys):
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(manifest()), encoding="utf-8")

    def failure(_):
        raise RuntimeError("private credential must not be printed")

    monkeypatch.setattr(preflight, "get_tracking_uri", failure)
    assert (
        preflight.main(
            [
                "--tracking-uri",
                "http://synthetic.invalid",
                "--model-metadata",
                str(metadata),
            ]
        )
        == 1
    )
    assert "private credential" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "case", ["missing_customer", "flat_customer", "status", "champion"]
)
def test_registry_refuses_invalid_contract(case):
    version, loaded = registry_objects()
    if case == "missing_customer":
        loaded.metadata.signature.inputs = Schema([ColSpec("string", "other")])
    elif case == "flat_customer":
        loaded.metadata.signature.inputs = Schema([ColSpec("string", "customer")])
    elif case == "status":
        version.tags["status"] = "CHAMPION"
    else:
        version.aliases.append("champion")
    client = SimpleNamespace(get_model_version_by_alias=lambda *a: version)
    with pytest.raises(ValueError):
        preflight.verify_registry(client, lambda _: loaded, manifest())


def test_cli_help_and_sqlite_message(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit):
        preflight.main(["--help"])
    help_text = capsys.readouterr().out
    assert "--model-metadata" in help_text and "model_sha256" in help_text
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(manifest()), encoding="utf-8")
    monkeypatch.setattr(preflight, "get_tracking_uri", lambda _: "sqlite:///local.db")
    assert (
        preflight.main(
            [
                "--tracking-uri",
                "http://synthetic.invalid",
                "--model-metadata",
                str(metadata),
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "SQLite" in output and "--allow-local-sqlite" not in output
