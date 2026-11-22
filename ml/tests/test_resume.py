"""Recovery path: finish a run that stopped after predictions_saved."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.scripts import evaluate_final_candidate as evaluation
from ml.scripts import final_journal
from ml.scripts.final_journal import find_open_launch
from ml.src.evaluation.final_artifacts import (
    APPROVED_D48_MODEL_SHA256,
    APPROVED_D48_SOURCE_SHA256,
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _journal(tmp_path: Path) -> Path:
    journal = tmp_path / "journal.jsonl"
    journal.write_text(
        json.dumps(
            {
                "status": "started",
                "utc": "2026-11-10T18:41:37.453667+00:00",
                "model_sha256": APPROVED_D48_MODEL_SHA256,
            }
        )
        + "\n"
        + json.dumps(
            {
                "status": "completed",
                "source_sha256": APPROVED_D48_SOURCE_SHA256,
                "output": "/previous",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return journal


def _binding(launch_id: str, utc: str) -> dict:
    return {
        "launch_id": launch_id,
        "decision_id": "D48",
        "model_sha256": APPROVED_D48_MODEL_SHA256,
        "source_sha256": APPROVED_D48_SOURCE_SHA256,
        "protocol_sha256": "b" * 64,
        "utc": utc,
    }


def _reserve(journal: Path, launch_id: str, predictions_sha256: str) -> None:
    raw, _entries = final_journal.read_journal(journal)
    final_journal._append(
        journal,
        raw,
        {
            "status": "reserved",
            "protocol_revision": "D48-2026-11-20",
            **_binding(launch_id, "2026-11-22T14:43:28+00:00"),
        },
    )
    raw, _entries = final_journal.read_journal(journal)
    final_journal._append(
        journal,
        raw,
        {
            "status": "predictions_saved",
            "predictions_sha256": predictions_sha256,
            **_binding(launch_id, "2026-11-22T14:43:36+00:00"),
        },
    )


def test_finds_the_single_open_launch(tmp_path):
    journal = _journal(tmp_path)
    _reserve(journal, "launch-1", "c" * 64)

    launch = find_open_launch(
        journal,
        source_sha256=APPROVED_D48_SOURCE_SHA256,
        model_sha256=APPROVED_D48_MODEL_SHA256,
        predictions_sha256="c" * 64,
    )

    assert launch["launch_id"] == "launch-1"
    assert launch["decision_id"] == "D48"


def test_refuses_a_predictions_hash_that_does_not_match(tmp_path):
    journal = _journal(tmp_path)
    _reserve(journal, "launch-1", "c" * 64)

    with pytest.raises(ValueError, match="introuvable ou ambiguë"):
        find_open_launch(
            journal,
            source_sha256=APPROVED_D48_SOURCE_SHA256,
            model_sha256=APPROVED_D48_MODEL_SHA256,
            predictions_sha256="d" * 64,
        )


def test_refuses_two_open_launches(tmp_path):
    journal = _journal(tmp_path)
    _reserve(journal, "launch-1", "c" * 64)
    _reserve(journal, "launch-2", "c" * 64)

    with pytest.raises(ValueError, match="ambiguë \\(2\\)"):
        find_open_launch(
            journal,
            source_sha256=APPROVED_D48_SOURCE_SHA256,
            model_sha256=APPROVED_D48_MODEL_SHA256,
            predictions_sha256="c" * 64,
        )


def test_refuses_invalid_fingerprints(tmp_path):
    journal = _journal(tmp_path)

    with pytest.raises(ValueError, match="empreintes invalides"):
        find_open_launch(
            journal,
            source_sha256="not-a-hash",
            model_sha256=APPROVED_D48_MODEL_SHA256,
            predictions_sha256="c" * 64,
        )


def _predictions(path: Path, rows: int = 20) -> str:
    frame = pd.DataFrame(
        {
            "label": [0, 1] * (rows // 2),
            "fraud_probability": np.linspace(0.01, 0.99, rows),
            "include_0": [1] * rows,
            "include_1": [0] * rows,
            "gender": ["F", "M"] * (rows // 2),
            "age_group": ["26-35"] * rows,
        }
    )
    frame.to_csv(path, index=False)
    return _sha(path.read_bytes())


def test_load_saved_details_rebuilds_the_details_dict(tmp_path):
    predictions = tmp_path / "predictions.csv"
    digest = _predictions(predictions)

    details = evaluation.load_saved_details(tmp_path, digest)

    assert details["labels"].shape == (20,)
    assert details["members"].shape == (20, 2)
    assert set(details["gender"]) == {"F", "M"}
    assert details["age_group"][0] == "26-35"


def test_load_saved_details_refuses_a_changed_predictions_file(tmp_path):
    predictions = tmp_path / "predictions.csv"
    _predictions(predictions)
    predictions.write_text("label\n0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ne correspond pas au manifeste"):
        evaluation.load_saved_details(tmp_path, "0" * 64)


def test_load_saved_details_refuses_missing_columns(tmp_path):
    predictions = tmp_path / "predictions.csv"
    predictions.write_text("label,gender\n0,F\n", encoding="utf-8")

    with pytest.raises(ValueError, match="colonnes manquantes"):
        evaluation.load_saved_details(tmp_path, _sha(predictions.read_bytes()))


def test_summarize_attaches_the_group_masks(tmp_path):
    details = {
        "labels": np.array([0, 1, 0, 1]),
        "probabilities": np.array([0.1, 0.9, 0.2, 0.8]),
        "members": np.array(
            [[True, False], [False, True], [True, False], [False, True]]
        ),
        "gender": np.array(["F", "M", "F", "M"]),
        "age_group": np.array(["26-35", "26-35", "36-45", "36-45"]),
    }

    evaluation.summarize_details(details, 0.02)

    assert "group_masks" in details
    assert set(details["group_masks"]) == {
        "gender:F",
        "gender:M",
        "age:0-25",
        "age:26-35",
        "age:36-45",
        "age:46-55",
        "age:56-65",
        "age:66-120",
    }


def test_resume_refuses_a_complete_manifest(tmp_path, monkeypatch):
    output = tmp_path / "results"
    output.mkdir()
    (output / "artifact_manifest.json").write_text(
        json.dumps({"status": "complete", "artifacts": {}}), encoding="utf-8"
    )
    args = evaluation.argparse.Namespace(
        resume=output,
        model=tmp_path / "model.joblib",
        journal=tmp_path / "journal.jsonl",
        reference=tmp_path / "ref.json",
        latency_source=tmp_path / "fraudTrain.csv",
        model_sha256=None,
        source_sha256=None,
        output_dir=None,
        tracking_uri=None,
        synthetic=False,
        no_mlflow=False,
        comparison_kind=None,
        comparison_pr_auc=None,
        code_revision=None,
    )

    with pytest.raises(ValueError, match="'predictions_saved' attendu"):
        evaluation.resume(args)


def test_resume_requires_its_inputs(tmp_path):
    args = evaluation.argparse.Namespace(
        resume=tmp_path,
        model=None,
        journal=None,
        reference=None,
        latency_source=None,
        model_sha256=None,
        source_sha256=None,
        output_dir=None,
        tracking_uri=None,
        synthetic=False,
        no_mlflow=False,
        comparison_kind=None,
        comparison_pr_auc=None,
        code_revision=None,
    )

    with pytest.raises(ValueError, match="--journal"):
        evaluation.resume(args)


def test_resume_hands_a_dict_and_the_saved_hash_to_finish(tmp_path, monkeypatch):
    from types import SimpleNamespace

    output = tmp_path / "results"
    (output / "previous_evaluation").mkdir(parents=True)
    digest = _predictions(output / "predictions.csv")
    (output / "artifact_manifest.json").write_text(
        json.dumps(
            {"status": "predictions_saved", "artifacts": {"predictions.csv": digest}}
        ),
        encoding="utf-8",
    )
    (output / "previous_evaluation" / "final_metrics.json").write_text(
        "{}", encoding="utf-8"
    )
    (output / "previous_evaluation" / "final_report.md").write_text(
        "# x", encoding="utf-8"
    )
    journal = _journal(tmp_path)
    _reserve(journal, "launch-1", digest)
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"fake-model")

    real_sha = evaluation.sha256
    monkeypatch.setattr(
        evaluation,
        "sha256",
        lambda path: (
            APPROVED_D48_MODEL_SHA256 if Path(path) == model_path else real_sha(path)
        ),
    )
    monkeypatch.setattr(
        evaluation.joblib, "load", lambda _: SimpleNamespace(alpha=0.02)
    )
    monkeypatch.setattr(evaluation, "load_latency_sample", lambda *a, **k: None)
    monkeypatch.setattr(
        evaluation, "measure_latency", lambda *a, **k: {"p95_ms": 1.0, "calls": 1}
    )
    monkeypatch.setattr(
        evaluation,
        "load_previous_evaluation",
        lambda *a, **k: ({"source": "history"}, {"final_metrics.json": b"raw"}),
    )
    captured = {}

    def fake_finish(*a, **kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(evaluation, "finish", fake_finish)
    args = evaluation.argparse.Namespace(
        resume=output,
        model=model_path,
        journal=journal,
        reference=tmp_path / "ref.json",
        latency_source=tmp_path / "fraudTrain.csv",
        model_sha256=APPROVED_D48_MODEL_SHA256,
        source_sha256=APPROVED_D48_SOURCE_SHA256,
        output_dir=None,
        tracking_uri=None,
        synthetic=False,
        no_mlflow=False,
        comparison_kind="logreg",
        comparison_pr_auc=0.3697,
        code_revision=None,
    )

    assert evaluation.resume(args) == 0

    assert isinstance(captured["previous"], dict), "previous must not be the raw tuple"
    assert captured["previous"] == {"source": "history"}
    assert captured["saved"] == {"sha256": digest}
    assert captured["launch_id"] == "launch-1"
