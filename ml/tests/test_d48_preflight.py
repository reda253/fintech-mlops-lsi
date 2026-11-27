"""D48 : le précontrôle est en lecture seule et refuse toute liaison incomplète."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from ml.scripts import d48_preflight, final_journal
from ml.scripts.evaluate_final_candidate import ROOT


class Preprocessor:
    def transform(self, frame):
        return np.arange(len(frame), dtype=float).reshape(-1, 1)


class Classifier:
    def predict_proba(self, frame):
        probabilities = np.full(len(frame), 0.5)
        return np.column_stack((1 - probabilities, probabilities))


class Candidate:
    alpha = 0.02
    threshold_legit = 0.5
    threshold_fraud = 0.6
    preprocessor = Preprocessor()
    classifier = Classifier()


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _latency_source(root: Path) -> Path:
    data = root / "data" / "raw"
    data.mkdir(parents=True)
    dates = pd.date_range("2020-01-01 08:00:00", periods=40, freq="h")
    frame = pd.DataFrame(
        {
            "trans_date_trans_time": dates.strftime("%Y-%m-%d %H:%M:%S"),
            "dob": "1980-01-01",
            "amt": np.linspace(1.0, 40.0, 40),
            "category": "shopping_net",
            "gender": "F",
            "state": "NY",
            "city_pop": 50000,
            "lat": 40.0,
            "long": -73.0,
            "merch_lat": 40.1,
            "merch_long": -73.1,
        }
    )
    path = data / "fraudTrain.csv"
    frame.to_csv(path, index=False)
    return path


def _environment(root: Path) -> dict[str, Path]:
    model = root / "candidate_model.joblib"
    joblib.dump(Candidate(), model)
    model_sha = _sha(model)

    source = root / "fraudTest.csv"
    source.write_text("label,trans_date_trans_time\n0,2020-06-01 12:00:00\n")
    source_sha = _sha(source)

    reference = root / "results.json"
    _write_json(
        reference,
        {
            "selected_alpha": 0.02,
            "alpha_results": [
                {
                    "alpha": 0.02,
                    "status": "eligible",
                    "quantiles": {"0": 0.5, "1": 0.6},
                }
            ],
        },
    )

    previous = root / "previous_evaluation"
    previous.mkdir()
    _write_json(
        previous / "final_metrics.json",
        {
            "scope": "final_test",
            "model_sha256": model_sha,
            "source_sha256": source_sha,
            "alpha": 0.02,
            "overall": {
                "pr_auc": 0.8,
                "coverage_by_class": {"0": 0.98, "1": 0.97},
                "review_rate": 0.01,
                "automatic_error_rate": 0.02,
                "n_transactions": 30,
                "fraud_count": 3,
            },
        },
    )
    (previous / "final_report.md").write_text("# rapport\n", encoding="utf-8")

    protocol = root / "protocol.md"
    protocol.write_text("# protocole approuve\n", encoding="utf-8")

    journal = root / "journal.jsonl"
    legacy = [
        {
            "status": "started",
            "utc": "2026-11-10T18:41:37+00:00",
            "model_sha256": model_sha,
        },
        {"status": "completed", "source_sha256": source_sha},
    ]
    journal.write_text(
        "".join(json.dumps(entry) + "\n" for entry in legacy), encoding="utf-8"
    )

    authorization = root / "authorization-d48.json"
    _write_json(
        authorization,
        {
            "approved": True,
            "decision_id": "D48",
            "source_sha256": source_sha,
            "model_sha256": model_sha,
            "protocol_sha256": _sha(protocol),
            "journal_sha256": _sha(journal),
        },
    )

    return {
        "model": model,
        "source": source,
        "reference": reference,
        "previous": previous,
        "protocol": protocol,
        "journal": journal,
        "authorization": authorization,
        "latency": _latency_source(root),
        "output": root / "d48-results",
    }


@pytest.fixture
def env(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    environment = _environment(tmp_path)
    monkeypatch.setattr(final_journal, "LEGACY_MODEL", _sha(environment["model"]))
    monkeypatch.setattr(final_journal, "LEGACY_SOURCE", _sha(environment["source"]))
    return environment


def _args(environment: dict[str, Path], **overrides) -> argparse.Namespace:
    values = {
        "model": environment["model"],
        "source": environment["source"],
        "reference": environment["reference"],
        "previous_evaluation": environment["previous"],
        "latency_source": environment["latency"],
        "journal": environment["journal"],
        "protocol_file": environment["protocol"],
        "authorization": environment["authorization"],
        "output_dir": environment["output"],
        "decision_id": "D48",
        "reason": "precontrole synthetique",
        "expected_model_sha256": _sha(environment["model"]),
        "expected_source_sha256": _sha(environment["source"]),
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _argv(args: argparse.Namespace) -> list[str]:
    argv = [
        "--model",
        str(args.model),
        "--source",
        str(args.source),
        "--reference",
        str(args.reference),
        "--previous-evaluation",
        str(args.previous_evaluation),
        "--latency-source",
        str(args.latency_source),
        "--journal",
        str(args.journal),
        "--protocol-file",
        str(args.protocol_file),
        "--authorization",
        str(args.authorization),
        "--output-dir",
        str(args.output_dir),
        "--expected-model-sha256",
        args.expected_model_sha256,
        "--expected-source-sha256",
        args.expected_source_sha256,
    ]
    if getattr(args, "verbose", False):
        argv.append("--verbose")
    return argv


def test_preflight_passes_and_writes_nothing(env, tmp_path: Path):
    args = _args(env)
    journal_before = args.journal.read_bytes()

    checks = d48_preflight.preflight(args)

    assert any("journal lisible" in check for check in checks)
    assert any("autorisation" in check for check in checks)
    assert args.journal.read_bytes() == journal_before
    assert not args.output_dir.exists()
    assert not list(tmp_path.glob(".write-check-*"))


def test_cli_reports_success(env, capsys):
    assert d48_preflight.main(_argv(_args(env))) == 0
    assert "[PRET]" in capsys.readouterr().out


def test_authorization_inside_the_repository_is_refused(env):
    args = _args(env, authorization=ROOT / "docs" / "final_evaluation_protocol.md")

    with pytest.raises(ValueError, match="hors du dépôt"):
        d48_preflight.preflight(args)


def test_journal_without_the_legacy_anchor_is_refused(env):
    args = _args(env)
    args.journal.write_text(
        json.dumps({"status": "completed", "source_sha256": _sha(args.source)}) + "\n",
        encoding="utf-8",
    )
    _write_json(
        args.authorization,
        {
            "approved": True,
            "decision_id": "D48",
            "source_sha256": _sha(args.source),
            "model_sha256": _sha(args.model),
            "protocol_sha256": _sha(args.protocol_file),
            "journal_sha256": _sha(args.journal),
        },
    )

    with pytest.raises(ValueError, match="10 novembre"):
        d48_preflight.preflight(args)


def test_draft_authorization_is_refused(env):
    args = _args(env)
    payload = json.loads(args.authorization.read_text(encoding="utf-8"))
    payload["approved"] = False
    _write_json(args.authorization, payload)

    with pytest.raises(ValueError, match="Autorisation"):
        d48_preflight.preflight(args)


def test_wrong_model_hash_is_refused(env):
    args = _args(env, expected_model_sha256="a" * 64)

    with pytest.raises(ValueError, match="modèle"):
        d48_preflight.preflight(args)


def test_wrong_protocol_hash_in_authorization_is_refused(env):
    args = _args(env)
    payload = json.loads(args.authorization.read_text(encoding="utf-8"))
    payload["protocol_sha256"] = "b" * 64
    _write_json(args.authorization, payload)

    with pytest.raises(ValueError, match="Autorisation"):
        d48_preflight.preflight(args)


def test_existing_output_directory_is_refused(env):
    args = _args(env)
    args.output_dir.mkdir()

    with pytest.raises(ValueError, match="déjà présent"):
        d48_preflight.preflight(args)


def test_missing_authorization_is_refused_with_a_clear_message(env):
    args = _args(env)
    args.authorization.unlink()

    with pytest.raises(ValueError, match="Autorisation D48 absente"):
        d48_preflight.preflight(args)


def test_unreadable_authorization_is_refused_with_a_clear_message(env):
    args = _args(env)
    args.authorization.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="Autorisation D48 illisible"):
        d48_preflight.preflight(args)


def test_verbose_run_shows_the_checks_passed_before_a_failure(env, capsys):
    args = _args(env, verbose=True)
    args.authorization.unlink()

    assert d48_preflight.main(_argv(args)) == 2

    captured = capsys.readouterr()
    assert "[OK] journal lisible" in captured.out
    assert "[OK] source finale" in captured.out
    assert "[OK] candidat figé" in captured.out
    assert "[OK] protocole" in captured.out
    assert "Autorisation D48 absente" in captured.err
    assert "[PRET]" not in captured.out


def test_missing_journal_is_refused(env):
    args = _args(env)
    args.journal.unlink()

    with pytest.raises(ValueError, match="Journal"):
        d48_preflight.preflight(args)


def test_main_returns_two_on_failure(env, capsys):
    args = _args(env, expected_source_sha256="a" * 64)

    assert d48_preflight.main(_argv(args)) == 2
    assert "[ECHEC]" in capsys.readouterr().err


def test_non_d48_decision_is_refused_before_any_read(env):
    args = _args(env, decision_id="D49")

    with pytest.raises(ValueError, match="D48 requise"):
        d48_preflight.preflight(args)


def test_output_inside_the_repository_is_refused(env):
    args = _args(env, output_dir=ROOT / "d48-results")

    with pytest.raises(ValueError, match="hors du dépôt"):
        d48_preflight.preflight(args)


@pytest.mark.parametrize("approved", [1, "true", None])
def test_authorization_approved_must_be_the_boolean_true(env, approved):
    args = _args(env)
    payload = json.loads(args.authorization.read_text(encoding="utf-8"))
    payload["approved"] = approved
    _write_json(args.authorization, payload)

    with pytest.raises(ValueError, match="Autorisation"):
        d48_preflight.preflight(args)


@pytest.mark.parametrize(
    "field", ["decision_id", "source_sha256", "model_sha256", "journal_sha256"]
)
def test_wrong_authorization_field_is_refused(env, field):
    args = _args(env)
    payload = json.loads(args.authorization.read_text(encoding="utf-8"))
    payload[field] = "D49" if field == "decision_id" else "b" * 64
    _write_json(args.authorization, payload)

    with pytest.raises(ValueError, match="Autorisation"):
        d48_preflight.preflight(args)


def test_journal_with_a_d47_entry_is_refused_for_d48(env):
    args = _args(env)
    raw, _entries = final_journal.read_journal(args.journal)
    final_journal._append(
        args.journal,
        raw,
        {
            "status": "reserved",
            "utc": "2026-11-12T10:00:00+00:00",
            "launch_id": "old-d47",
            "decision_id": "D47",
            "model_sha256": "d" * 64,
            "source_sha256": "e" * 64,
            "protocol_sha256": "f" * 64,
        },
    )
    payload = json.loads(args.authorization.read_text(encoding="utf-8"))
    payload["journal_sha256"] = _sha(args.journal)
    _write_json(args.authorization, payload)

    with pytest.raises(ValueError, match="Entrée D47"):
        d48_preflight.preflight(args)
