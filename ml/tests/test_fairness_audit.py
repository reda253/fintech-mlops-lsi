"""Synthetic fairness checks, without model or final-test access."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.fairness import audit


@pytest.fixture
def synthetic_launch(tmp_path, monkeypatch):
    from ml.tests import test_evaluation_safety

    return test_evaluation_safety.synthetic_launch.__wrapped__(tmp_path, monkeypatch)


def sample():
    return pd.DataFrame(
        {
            "gender": ["F", "F", "M", "M"],
            "age_band": ["0-25", "0-25", "66-120", "66-120"],
            "is_fraud": [1, 1, 0, 0],
            "fraud_probability": [0.9, 0.5, 0.1, 0.9],
            "include_0": [0, 0, 1, 0],
            "include_1": [1, 0, 0, 1],
        }
    )


def test_exact_age_boundaries():
    assert audit.age_bands(
        pd.Series([0, 25, 26, 35, 36, 45, 46, 55, 56, 65, 66, 120])
    ).tolist() == [name for name in audit.AGE_LABELS for _ in range(2)]
    with pytest.raises(ValueError):
        audit.age_bands(pd.Series([121]))


def test_exact_decisions_and_rates():
    assert [audit.decision(s) for s in ([0], [1], [], [0, 1])] == [
        "APPROUVER",
        "BLOQUER",
        "REVUE HUMAINE",
        "REVUE HUMAINE",
    ]
    result = audit.analyze(sample(), n_boot=200)
    overall = result["groups"][0]
    assert overall["N"] == 4 and overall["N_pos"] == 2 and overall["N_neg"] == 2
    assert [overall["metrics"][m]["value"] for m in audit.METRICS] == [
        0.5,
        1,
        0.5,
        0.25,
    ]


def test_deterministic_shared_bootstrap_and_undefined():
    a = audit.analyze(sample(), n_boot=1000)
    assert a == audit.analyze(sample(), n_boot=1000)
    female = next(
        g for g in a["groups"] if g["attribute"] == "gender" and g["group"] == "F"
    )
    assert female["metrics"]["auto_block_legitimate_rate"]["value"] is None
    male = next(
        g for g in a["groups"] if g["attribute"] == "gender" and g["group"] == "M"
    )
    assert male["metrics"]["auto_block_fraud_rate"]["ci95"] is None
    for gap in a["absolute_gaps"]:
        if gap["ci95"]:
            assert 0 <= gap["ci95"][0] <= gap["ci95"][1] <= 1


def test_equivalent_gender_and_age_masks_share_bootstrap_draws():
    result = audit.analyze(sample(), n_boot=100)
    female = next(
        g for g in result["groups"] if g["attribute"] == "gender" and g["group"] == "F"
    )
    youngest = next(
        g
        for g in result["groups"]
        if g["attribute"] == "age_band" and g["group"] == "0-25"
    )
    assert female["metrics"] == youngest["metrics"]
    for metric in audit.METRICS:
        gender_gap = next(
            g
            for g in result["absolute_gaps"]
            if g["attribute"] == "gender" and g["metric"] == metric
        )
        age_gap = next(
            g
            for g in result["absolute_gaps"]
            if g["attribute"] == "age_band"
            and g["group_a"] == "0-25"
            and g["group_b"] == "66-120"
            and g["metric"] == metric
        )
        assert gender_gap["ci95"] == age_gap["ci95"]


@pytest.mark.parametrize(
    "column,value",
    [("gender", "X"), ("is_fraud", 2), ("fraud_probability", np.nan), ("include_0", 2)],
)
def test_reject_invalid_predictions(column, value):
    frame = sample()
    frame.loc[0, column] = value
    with pytest.raises(ValueError):
        audit.analyze(frame, n_boot=10)


def test_saved_predictions_cli_synthetic_end_to_end(
    synthetic_launch, tmp_path, monkeypatch
):
    import importlib
    from types import SimpleNamespace

    import mlflow
    import mlflow.tracking

    from ml.fairness import preflight_d48 as preflight
    from ml.scripts import d48_preflight as local_preflight
    from ml.scripts import evaluate_final_candidate as evaluation
    from ml.scripts import final_journal
    from ml.tests.test_evaluation_safety import approved, write_previous_evaluation

    args, raw, journal, evaluated = synthetic_launch
    model = Path(args[args.index("--model") + 1])
    protocol = Path(args[args.index("--protocol-file") + 1])
    auth = Path(args[args.index("--authorization") + 1])
    source_hash, model_hash = evaluation.sha256(raw), evaluation.sha256(model)
    monkeypatch.setattr(audit, "APPROVED_D48_SOURCE_SHA256", source_hash)
    for module in (preflight, audit):
        monkeypatch.setattr(module, "APPROVED_D48_MODEL_SHA256", model_hash)
    monkeypatch.setattr(final_journal, "LEGACY_SOURCE", source_hash)
    monkeypatch.setattr(final_journal, "LEGACY_MODEL", model_hash)
    monkeypatch.setattr(evaluation, "FINAL_DECISION_ID", "D48")
    journal.write_text(
        json.dumps(
            {
                "status": "started",
                "utc": "2026-11-10T00:00:00Z",
                "model_sha256": model_hash,
            }
        )
        + "\n"
        + json.dumps({"status": "completed", "source_sha256": source_hash})
        + "\n"
    )
    auth.write_text(
        json.dumps(
            approved(
                journal, "D48", source_hash, model_hash, evaluation.sha256(protocol)
            )
        )
    )
    args[args.index("--decision-id") + 1] = "D48"
    history = tmp_path / "historical"
    write_previous_evaluation(args, history)
    args += ["--previous-evaluation", str(history), "--code-revision", "a" * 40]
    provenance = tmp_path / "provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "source_sha256": source_hash,
                "model_sha256": model_hash,
                "alpha": 0.02,
                "model_uri": "models:/fraud-detector/1",
                "model_version": "1",
            }
        )
    )
    monkeypatch.setattr(
        preflight, "get_tracking_uri", lambda _: "http://synthetic.invalid"
    )
    monkeypatch.setattr(mlflow, "set_tracking_uri", lambda _: None)
    version = SimpleNamespace(version="1", tags={"source_model_sha256": model_hash})
    loaded = SimpleNamespace(
        metadata=SimpleNamespace(
            signature=SimpleNamespace(inputs=["x"], outputs=["y"])
        ),
        unwrap_python_model=lambda: SimpleNamespace(alpha=0.02),
    )
    monkeypatch.setattr(
        importlib.import_module("mlflow.tracking"),
        "MlflowClient",
        lambda: SimpleNamespace(get_model_version_by_alias=lambda *a: version),
    )
    monkeypatch.setattr(
        importlib.import_module("mlflow.pyfunc"), "load_model", lambda _: loaded
    )
    # Local #120 preconditions, then Registry check, then synthetic evaluation.
    import argparse

    monkeypatch.setattr(
        local_preflight, "load_latency_sample", evaluation.load_latency_sample
    )
    local_checks = local_preflight.preflight(
        argparse.Namespace(
            model=model,
            source=raw,
            reference=Path(args[args.index("--reference") + 1]),
            previous_evaluation=history,
            latency_source=Path(args[args.index("--latency-source") + 1]),
            journal=journal,
            authorization=auth,
            protocol_file=protocol,
            output_dir=evaluated,
            decision_id="D48",
            reason="synthetic integration",
            expected_model_sha256=model_hash,
            expected_source_sha256=source_hash,
        )
    )
    assert local_checks and not evaluated.exists()
    assert preflight.main(["--manifest", str(provenance)]) == 0
    assert evaluation.main(args) == 0
    (evaluated / "mlflow_status.json").write_text(
        json.dumps({"status": "published", "run_id": "synthetic-evaluation"})
    )
    # Analysis can only open saved artifacts: no further inference or raw access.
    original_open = Path.open

    def saved_only(path, *a, **kw):
        if path.resolve() == raw.resolve():
            pytest.fail("audit must not open even the synthetic final source")
        return original_open(path, *a, **kw)

    monkeypatch.setattr(Path, "open", saved_only)
    monkeypatch.setattr(
        mlflow.pyfunc, "load_model", lambda *a, **k: pytest.fail("no model load")
    )
    output = tmp_path / "analysis"
    command = [
        "--from-predictions",
        str(evaluated / "predictions.csv"),
        "--output-dir",
        str(output),
        "--code-revision",
        "a" * 40,
        "--model-metadata",
        str(provenance),
        "--journal",
        str(journal),
    ]
    original_manifest = (evaluated / "artifact_manifest.json").read_bytes()
    before_journal = journal.read_bytes()
    assert audit.main(command) == 0
    data = json.loads((output / "fairness_metrics.json").read_text(encoding="utf-8"))
    assert data["bootstrap"]["n_boot"] == 10000 and data["bootstrap"]["seed"] == 42
    text = (output / "fairness_report.md").read_text(encoding="utf-8")
    assert "N/A (undefined)" in text and "non indépendante" in text
    assert len(list((output / "figures").glob("*.png"))) == 8
    manifest = json.loads((output / "manifest_d48.json").read_text())
    assert manifest["status"] == "complete" and manifest["model_sha256"] == model_hash
    assert manifest["input_predictions_sha256"] == evaluation.sha256(
        evaluated / "predictions.csv"
    )
    assert (
        manifest["scope"] == "saved_d48_predictions"
        and manifest["git_commit"] == "a" * 40
    )
    assert (
        manifest["run_id"] == "synthetic-evaluation"
        and manifest["source_sha256"] == source_hash
    )
    for name, digest in manifest["artifacts"].items():
        assert evaluation.sha256(output / name) == digest
    assert (evaluated / "artifact_manifest.json").read_bytes() == original_manifest
    assert journal.read_bytes() == before_journal
    with pytest.raises(ValueError):
        audit.main(command)
    with (evaluated / "predictions.csv").open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(ValueError, match="predictions.csv"):
        audit.main(command)


def test_reference_is_explicit():
    result = audit.analyze(sample(), age_reference="0-25", n_boot=20)
    assert all(
        g["group_b"] == "0-25"
        for g in result["absolute_gaps"]
        if g["attribute"] == "age_band"
    )


@pytest.mark.parametrize(
    "status", ["started", "reserved", "predictions_saved", "completed", "failed"]
)
def test_audit_rejects_all_d47_entries_before_artifact_read(
    tmp_path, monkeypatch, status
):
    from ml.scripts import final_journal

    journal = tmp_path / "journal.jsonl"
    journal.write_text('{"status":"completed","source_sha256":"' + "a" * 64 + '"}\n')
    raw, _ = final_journal.read_journal(journal)
    final_journal._append(
        journal,
        raw,
        {
            "status": status,
            "decision_id": "D47",
            "launch_id": "synthetic",
            "utc": "2026-11-20T00:00:00Z",
            "model_sha256": "b" * 64,
            "source_sha256": "a" * 64,
            "protocol_sha256": "c" * 64,
        },
    )
    before = journal.read_bytes()
    monkeypatch.setattr(
        audit,
        "load_verified_final_evaluation",
        lambda *a, **k: pytest.fail("journal must fail first"),
    )
    with pytest.raises(ValueError, match="Entrée D47"):
        audit.main(
            [
                "--from-predictions",
                str(tmp_path / "predictions.csv"),
                "--output-dir",
                str(tmp_path / "audit"),
                "--journal",
                str(journal),
                "--code-revision",
                "a" * 40,
            ]
        )
    assert journal.read_bytes() == before


@pytest.mark.parametrize(
    "change,match",
    [("bounds", "pr_auc"), ("counts", "fraud_count"), ("history", "historique")],
)
def test_audit_uses_strict_reader_despite_valid_hashes(tmp_path, change, match):
    from ml.scripts.evaluate_final_candidate import sha256 as digest
    from ml.tests.test_final_artifacts import build_artifact

    directory = build_artifact(tmp_path)
    path = directory / "final_metrics.json"
    payload = json.loads(path.read_text())
    if change == "bounds":
        payload["overall"]["pr_auc"] = 1.1
    elif change == "counts":
        payload["overall"]["fraud_count"] = 11
    else:
        payload["previous_evaluation"]["artifacts"].clear()
    path.write_text(json.dumps(payload))
    manifest_path = directory / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"]["final_metrics.json"] = digest(path)
    manifest_path.write_text(json.dumps(manifest))
    journal = tmp_path / "journal.jsonl"
    journal.write_text('{"status":"completed","source_sha256":"' + "a" * 64 + '"}\n')
    with pytest.raises(ValueError, match=match):
        audit.main(
            [
                "--from-predictions",
                str(directory / "predictions.csv"),
                "--output-dir",
                str(tmp_path / "audit"),
                "--journal",
                str(journal),
                "--code-revision",
                "a" * 40,
            ]
        )
    assert not (tmp_path / "audit").exists()
