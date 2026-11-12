"""Pannes et concurrence : uniquement des fichiers et modèles synthétiques."""

import json
import multiprocessing
from pathlib import Path

import numpy as np
import pytest

from ml.scripts import evaluate_final_candidate as evaluation
from ml.scripts import final_journal as journal_api
from ml.scripts.final_tracking import verify_saved


class Preprocessor:
    def transform(self, frame):
        return np.arange(len(frame)).reshape(-1, 1)


class Classifier:
    def predict_proba(self, frame):
        p = np.resize([0.1, 0.8, 0.4, 0.95], len(frame))
        return np.column_stack((1 - p, p))


class Candidate:
    alpha = 0.02
    threshold_legit = 0.5
    threshold_fraud = 0.6
    preprocessor = Preprocessor()
    classifier = Classifier()


def write_history(path):
    path.write_text(
        json.dumps({"status": "completed", "source_sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )


def approved(path, decision="D99", digest="a" * 64, model="b" * 64, protocol="c" * 64):
    return {
        "approved": True,
        "decision_id": decision,
        "source_sha256": digest,
        "model_sha256": model,
        "protocol_sha256": protocol,
        "journal_sha256": evaluation.sha256(path),
    }


def reserve(path, authorization, revision="one", name="source.csv"):
    return journal_api.reserve_source(
        path,
        name,
        authorization["source_sha256"],
        authorization["model_sha256"],
        "autorisation synthétique",
        decision_id=authorization["decision_id"],
        protocol_revision=revision,
        protocol_sha256=authorization["protocol_sha256"],
        authorization=authorization,
    )


@pytest.fixture
def synthetic_launch(tmp_path, monkeypatch):
    # Toutes les sources de cette fixture sont synthétiques : D99 reste interne aux tests.
    monkeypatch.setattr(evaluation, "FINAL_DECISION_ID", "D99")
    source = tmp_path / "fraudTest.csv"  # Uniquement un fichier synthétique temporaire.
    evaluation.synthetic_data().to_csv(source, index=False)
    model = tmp_path / "model.joblib"
    model.write_bytes(b"synthetic-model")
    ref = tmp_path / "reference.json"
    ref.write_text(
        json.dumps(
            {
                "selected_alpha": 0.02,
                "alpha_results": [
                    {
                        "alpha": 0.02,
                        "status": "eligible",
                        "quantiles": {"0": 0.5, "1": 0.6},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    protocol = tmp_path / "approved.md"
    protocol.write_text("Synthetic fixed protocol", encoding="utf-8")
    journal = tmp_path / "journal.jsonl"
    write_history(journal)
    auth = tmp_path / "authorization.json"
    auth.write_text(
        json.dumps(
            approved(
                journal,
                digest=evaluation.sha256(source),
                model=evaluation.sha256(model),
                protocol=evaluation.sha256(protocol),
            )
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    args = [
        "--model",
        str(model),
        "--reference",
        str(ref),
        "--source",
        str(source),
        "--output-dir",
        str(output),
        "--model-sha256",
        evaluation.sha256(model),
        "--source-sha256",
        evaluation.sha256(source),
        "--journal",
        str(journal),
        "--decision-id",
        "D99",
        "--protocol-revision",
        "one",
        "--reason",
        "synthetic test",
        "--authorization",
        str(auth),
        "--protocol-file",
        str(protocol),
        "--latency-source",
        str(tmp_path / "dev.csv"),
        "--confirm-final-test",
    ]
    monkeypatch.setattr(evaluation.joblib, "load", lambda _: Candidate())
    dev = evaluation.synthetic_data().drop(columns="is_fraud")
    monkeypatch.setattr(evaluation, "load_latency_sample", lambda _: dev)
    monkeypatch.setattr(
        evaluation, "measure_latency", lambda *_: {"status": "UNVERIFIED"}
    )
    original = evaluation.bootstrap_intervals
    monkeypatch.setattr(
        evaluation, "bootstrap_intervals", lambda *a: original(*a, resamples=25)
    )
    monkeypatch.setattr(evaluation, "publish_saved", lambda *_: {"status": "published"})
    return args, source, journal, output


def deny_source(monkeypatch, source):
    original = Path.open
    opened = []

    def guarded(path, *args, **kwargs):
        if path.resolve() == source.resolve():
            opened.append(True)
            pytest.fail("La source finale ne doit pas être ouverte")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    return opened


def test_invalid_latency_fails_before_final_source_read(synthetic_launch, monkeypatch):
    args, source, journal, output = synthetic_launch
    before = journal.read_bytes()
    opened = deny_source(monkeypatch, source)

    def invalid(_):
        raise ValueError("Source de latence invalide")

    monkeypatch.setattr(evaluation, "load_latency_sample", invalid)
    with pytest.raises(ValueError, match="latence"):
        evaluation.main(args)
    assert not opened and not output.exists() and journal.read_bytes() == before


@pytest.mark.parametrize(
    "failure", ["disk", "permissions", "mount", "model", "protocol"]
)
def test_preflight_failures_do_not_read_final_source(
    synthetic_launch, monkeypatch, failure
):
    args, source, _journal, output = synthetic_launch
    opened = deny_source(monkeypatch, source)
    if failure == "disk":
        from types import SimpleNamespace

        monkeypatch.setattr(
            evaluation.shutil, "disk_usage", lambda _: SimpleNamespace(free=0)
        )
    elif failure == "permissions":

        def no_write(*a, **k):
            raise PermissionError("synthetic read-only output")

        monkeypatch.setattr(evaluation.tempfile, "mkstemp", no_write)
    elif failure == "mount":
        args[args.index("--output-dir") + 1] = str(output / "missing-mount" / "out")
    elif failure == "model":
        args[args.index("--model-sha256") + 1] = "d" * 64
    else:
        Path(args[args.index("--protocol-file") + 1]).write_text(
            "changed protocol", encoding="utf-8"
        )
    with pytest.raises((ValueError, PermissionError)):
        evaluation.main(args)
    assert not opened and not output.exists()


@pytest.mark.parametrize(
    "state", ["absent", "empty", "truncated", "invalid", "modified"]
)
def test_bad_journal_fails_before_final_read(synthetic_launch, monkeypatch, state):
    args, source, journal, output = synthetic_launch
    if state == "absent":
        journal.unlink()
    elif state == "empty":
        journal.write_bytes(b"")
    elif state == "truncated":
        journal.write_bytes(b'{"status":"completed"}')
    elif state == "invalid":
        journal.write_bytes(b"not-json\n")
    else:
        write_history(journal)
        with journal.open("ab") as stream:
            stream.write(b'{"status":"completed","source_sha256":"changed"}\n')
    opened = deny_source(monkeypatch, source)
    with pytest.raises(ValueError, match="Journal|journal|Autorisation|Entrée"):
        evaluation.main(args)
    assert not opened and not output.exists()


def test_bootstrap_failure_preserves_atomic_predictions(synthetic_launch, monkeypatch):
    args, _, journal, output = synthetic_launch

    def broken(*a, **k):
        raise RuntimeError("injected bootstrap failure")

    monkeypatch.setattr(evaluation, "bootstrap_intervals", broken)
    with pytest.raises(RuntimeError, match="bootstrap"):
        evaluation.main(args)
    manifest = json.loads(
        (output / "artifact_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["artifacts"]["predictions.csv"] == evaluation.sha256(
        output / "predictions.csv"
    )
    import pandas as pd

    rows = pd.read_csv(output / "predictions.csv")
    assert len(rows) == 4
    assert list(rows.columns) == [
        "label",
        "fraud_probability",
        "include_0",
        "include_1",
        "gender",
        "age_group",
    ]
    assert not list(output.glob(".pending-*"))
    entries = journal_api.read_journal(journal)[1]
    assert entries[-1]["status"] == "predictions_saved"
    assert not any(
        e.get("decision_id") == "D99" and e["status"] == "completed" for e in entries
    )


def test_interruption_during_prediction_save_stops_analysis(
    synthetic_launch, monkeypatch
):
    args, _, journal, output = synthetic_launch
    original = evaluation.os.replace

    def interrupted(temporary, destination):
        if Path(destination).name == "predictions.csv":
            raise OSError("interrupted immediately after inference")
        return original(temporary, destination)

    monkeypatch.setattr(evaluation.os, "replace", interrupted)
    monkeypatch.setattr(
        evaluation, "bootstrap_intervals", lambda *a: pytest.fail("bootstrap interdit")
    )
    with pytest.raises(OSError, match="inference"):
        evaluation.main(args)
    assert journal_api.read_journal(journal)[1][-1]["status"] == "reserved"
    assert not (output / "predictions.csv").exists()
    assert not list(output.glob(".pending-*"))


def test_atomic_replace_preserves_existing_destination(tmp_path, monkeypatch):
    path = tmp_path / "saved.csv"
    path.write_bytes(b"complete")

    def interrupted(*a):
        raise OSError("rename interrupted")

    monkeypatch.setattr(evaluation.os, "replace", interrupted)
    with pytest.raises(OSError):
        evaluation.atomic_write(path, b"partial")
    assert path.read_bytes() == b"complete" and not list(tmp_path.glob(".pending-*"))


def test_final_mode_synthetic_end_to_end_and_consumed_decision(synthetic_launch):
    args, _, journal, output = synthetic_launch
    assert evaluation.main(args) == 0
    result = verify_saved(output)
    assert (
        result["model_status"] == "provisional" and result["promotion_ready"] is False
    )
    entries = journal_api.read_journal(journal)[1]
    reservation = entries[1]
    assert [e["status"] for e in entries[1:]] == [
        "reserved",
        "predictions_saved",
        "completed",
    ]
    assert entries[-1]["protocol_sha256"] == reservation["protocol_sha256"]
    auth = approved(
        journal,
        digest=reservation["source_sha256"],
        model=reservation["model_sha256"],
        protocol=reservation["protocol_sha256"],
    )
    with pytest.raises(ValueError, match="consommée"):
        reserve(journal, auth, revision="new-name", name="copy.csv")
    before = journal.read_bytes()
    with pytest.raises(ValueError, match="consommée"):
        journal_api.record_event(journal, reservation["launch_id"], "completed")
    assert journal.read_bytes() == before


@pytest.mark.parametrize(
    "key",
    [
        "decision_id",
        "model_sha256",
        "source_sha256",
        "protocol_sha256",
        "journal_sha256",
        "approved",
    ],
)
def test_authorization_binds_every_field(tmp_path, key):
    path = tmp_path / "journal.jsonl"
    write_history(path)
    auth = approved(path)
    auth[key] = False if key == "approved" else "incorrect"
    with pytest.raises(ValueError, match="Autorisation"):
        journal_api.check_authorization(
            path,
            auth,
            source_sha256="a" * 64,
            model_sha256="b" * 64,
            decision_id="D99",
            protocol_sha256="c" * 64,
            reason="synthetic",
        )
    assert len(journal_api.read_journal(path)[1]) == 1


def test_d48_requires_legacy_anchor_and_cannot_be_reused(tmp_path):
    path = tmp_path / "journal.jsonl"
    write_history(path)
    with pytest.raises(ValueError, match="10 novembre"):
        reserve(path, approved(path, "D48"))
    legacy = [
        {
            "status": "started",
            "utc": "2026-11-10T18:41:37+00:00",
            "model_sha256": journal_api.LEGACY_MODEL,
        },
        {"status": "completed", "source_sha256": journal_api.LEGACY_SOURCE},
    ]
    path.write_text("".join(json.dumps(e) + "\n" for e in legacy), encoding="utf-8")
    auth = approved(path, "D48", journal_api.LEGACY_SOURCE, journal_api.LEGACY_MODEL)
    launch = reserve(path, auth)
    journal_api.record_event(
        path, launch, "predictions_saved", predictions_sha256="d" * 64
    )
    journal_api.record_event(path, launch, "completed")
    auth = approved(path, "D48", journal_api.LEGACY_SOURCE, journal_api.LEGACY_MODEL)
    with pytest.raises(ValueError, match="consommée"):
        reserve(path, auth, revision="different", name="renamed.csv")


def test_journal_hash_chain_detects_modified_entry(tmp_path):
    path = tmp_path / "journal.jsonl"
    write_history(path)
    reserve(path, approved(path))
    text = path.read_text(encoding="utf-8").replace(
        "autorisation synthétique", "modified reason"
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="modifié"):
        journal_api.read_journal(path)


def test_abandoned_lock_not_removed_and_completion_uses_same_lock(tmp_path):
    path = tmp_path / "journal.jsonl"
    write_history(path)
    launch = reserve(path, approved(path))
    lock = path.with_name(path.name + ".lock")
    lock.write_text('{"pid":-1,"utc":"old"}', encoding="utf-8")
    original = path.read_bytes()
    with pytest.raises(ValueError, match="récupération manuelle"):
        journal_api.record_event(path, launch, "predictions_saved")
    assert lock.exists() and path.read_bytes() == original


def race_worker(path, auth, ready, start, queue):
    ready.put(True)
    if not start.wait(timeout=30):
        queue.put("start_timeout")
        return
    try:
        reserve(Path(path), auth)
        queue.put("reserved")
    except ValueError as exc:
        queue.put(str(exc))


def test_two_processes_only_one_reservation(tmp_path):
    path = tmp_path / "journal.jsonl"
    write_history(path)
    ctx = multiprocessing.get_context("spawn")
    ready, queue, start = ctx.Queue(), ctx.Queue(), ctx.Event()
    processes = [
        ctx.Process(
            target=race_worker, args=(str(path), approved(path), ready, start, queue)
        )
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        for _ in processes:
            assert ready.get(timeout=60) is True
        start.set()
        outcomes = [queue.get(timeout=60) for _ in processes]
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
        assert outcomes.count("reserved") == 1
        assert len(journal_api.read_journal(path)[1]) == 2
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
        for q in (ready, queue):
            q.close()
            q.join_thread()


def test_missing_arguments_are_listed_together(tmp_path, capsys):
    with pytest.raises(SystemExit):
        evaluation.main(
            [
                "--model",
                "unused",
                "--reference",
                "unused",
                "--source",
                "fraudTest.csv",
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
    error = capsys.readouterr().err
    for flag in (
        "--journal",
        "--reason",
        "--protocol-file",
        "--authorization",
        "--latency-source",
        "--model-sha256",
    ):
        assert flag in error


def test_operational_equity_and_undefined_metrics():
    from ml.scripts.final_metrics import decision_metrics, weighted_metrics

    labels = np.array([1, 1, 1, 1, 0, 0, 0, 0])
    members = np.tile(
        [[True, False], [False, True], [True, True], [False, False]], (2, 1)
    )
    metrics = decision_metrics(labels, members, np.ones(8))
    assert metrics == {
        "auto_block_fraud_rate": 0.25,
        "fraud_interception_rate": 0.75,
        "auto_block_legitimate_rate": 0.25,
        "review_rate": 0.5,
    }
    undefined = weighted_metrics(
        np.array([0, 0]), np.array([0.1, 0.2]), np.ones((2, 2), dtype=bool), np.ones(2)
    )
    assert undefined["automatic_error_rate"] is None
    assert undefined["recall_point_prediction"] is None
    empty = weighted_metrics(
        np.array([0, 0]), np.array([0.1, 0.2]), np.ones((2, 2), dtype=bool), np.zeros(2)
    )
    assert empty and all(value is None for value in empty.values())


def test_completion_requires_saved_predictions(tmp_path):
    path = tmp_path / "journal.jsonl"
    write_history(path)
    launch = reserve(path, approved(path))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="non sauvegardées"):
        journal_api.record_event(path, launch, "completed")
    assert path.read_bytes() == before


def test_manifest_detects_changed_predictions(synthetic_launch):
    args, _, _, output = synthetic_launch
    assert evaluation.main(args) == 0
    with (output / "predictions.csv").open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(ValueError, match="predictions.csv"):
        verify_saved(output)


def test_journal_config_and_no_implicit_machine_path(tmp_path, monkeypatch):
    monkeypatch.delenv("FINAL_EVALUATION_JOURNAL", raising=False)
    assert evaluation.resolve_journal(None) is None
    path = tmp_path / "shared.jsonl"
    monkeypatch.setenv("FINAL_EVALUATION_JOURNAL", str(path))
    assert evaluation.resolve_journal(None) == path.resolve()
    assert (
        evaluation.resolve_journal(tmp_path / "explicit.jsonl")
        == (tmp_path / "explicit.jsonl").resolve()
    )
    with pytest.raises(ValueError, match="hors dépôt"):
        evaluation.resolve_journal(evaluation.ROOT / "not-created.jsonl")
    assert not path.exists()


def test_single_latency_measurement_before_source_read(synthetic_launch, monkeypatch):
    args, source, _, _ = synthetic_launch
    calls = []
    original = Path.open

    def latency(*_):
        calls.append("latency")
        return {"status": "UNVERIFIED"}

    def observed(path, *a, **k):
        if path.resolve() == source.resolve():
            assert calls == ["latency"]
            calls.append("source")
        return original(path, *a, **k)

    monkeypatch.setattr(evaluation, "measure_latency", latency)
    monkeypatch.setattr(Path, "open", observed)
    assert evaluation.main(args) == 0
    assert calls == ["latency", "source"]


def write_previous_evaluation(args, folder):
    folder.mkdir()
    overall, _ = evaluation.evaluate(Candidate(), evaluation.synthetic_data())
    data = {
        "scope": "final_test",
        "model_sha256": args[args.index("--model-sha256") + 1],
        "source_sha256": args[args.index("--source-sha256") + 1],
        "alpha": 0.02,
        "overall": overall,
    }
    metrics = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    report = "# Rapport original synthétique — 10 novembre\nValeurs conservées telles quelles.\n".encode()
    (folder / "final_metrics.json").write_bytes(metrics)
    (folder / "final_report.md").write_bytes(report)
    return metrics, report


def test_remeasurement_preserves_original_bytes_and_labels_report(
    synthetic_launch, tmp_path
):
    args, _, _, output = synthetic_launch
    previous = tmp_path / "previous"
    old_metrics, old_report = write_previous_evaluation(args, previous)
    assert evaluation.main([*args, "--previous-evaluation", str(previous)]) == 0
    assert (previous / "final_metrics.json").read_bytes() == old_metrics
    assert (previous / "final_report.md").read_bytes() == old_report
    archived = output / "previous_evaluation"
    assert (archived / "final_metrics.json").read_bytes() == old_metrics
    assert (archived / "final_report.md").read_bytes() == old_report
    result = verify_saved(output)
    assert result["measurement"]["number"] == 2
    assert result["measurement"]["independent"] is False
    assert result["measurement"]["post_hoc"] is True
    assert (
        result["previous_evaluation"]["overall"] == json.loads(old_metrics)["overall"]
    )
    report = (output / "final_report.md").read_text(encoding="utf-8")
    assert "Seconde mesure post hoc, non indépendante" in report
    assert "Première mesure — 10 novembre 2026" in report
    assert "previous_evaluation/final_report.md" in report
    assert (
        result["promotion_ready"] is False and result["model_status"] == "provisional"
    )
    manifest = json.loads(
        (output / "artifact_manifest.json").read_text(encoding="utf-8")
    )
    for name in ("final_report.md", "final_metrics.json"):
        assert manifest["artifacts"][
            f"previous_evaluation/{name}"
        ] == evaluation.sha256(archived / name)


@pytest.mark.parametrize(
    "field,value",
    [("model_sha256", "a" * 64), ("source_sha256", "b" * 64), ("alpha", 0.05)],
)
def test_previous_measurement_mismatch_fails_before_final_read(
    synthetic_launch, tmp_path, monkeypatch, field, value
):
    args, source, journal, output = synthetic_launch
    previous = tmp_path / "previous"
    write_previous_evaluation(args, previous)
    path = previous / "final_metrics.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[field] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    before = journal.read_bytes()
    opened = deny_source(monkeypatch, source)
    with pytest.raises(ValueError, match="différent|différente"):
        evaluation.main([*args, "--previous-evaluation", str(previous)])
    assert not opened and journal.read_bytes() == before and not output.exists()


@pytest.mark.parametrize("missing", ["final_metrics.json", "final_report.md"])
def test_missing_previous_artifact_fails_before_final_read(
    synthetic_launch, tmp_path, monkeypatch, missing
):
    args, source, _, output = synthetic_launch
    previous = tmp_path / "previous"
    write_previous_evaluation(args, previous)
    (previous / missing).unlink()
    opened = deny_source(monkeypatch, source)
    with pytest.raises(ValueError, match="précédente"):
        evaluation.main([*args, "--previous-evaluation", str(previous)])
    assert not opened and not output.exists()


def test_d48_requires_previous_evaluation_before_any_model_or_source_read(
    tmp_path, monkeypatch, capsys
):
    model = tmp_path / "unread.joblib"
    monkeypatch.setattr(
        evaluation.joblib, "load", lambda _: pytest.fail("chargement interdit")
    )
    with pytest.raises(SystemExit):
        evaluation.main(
            [
                "--synthetic",
                "--decision-id",
                "D48",
                "--model",
                str(model),
                "--reference",
                str(tmp_path / "ref.json"),
                "--output-dir",
                str(tmp_path / "out"),
                "--no-mlflow",
            ]
        )
    assert "--previous-evaluation" in capsys.readouterr().err


def test_tampered_historical_copy_rejected_by_republish(synthetic_launch, tmp_path):
    args, _, _, output = synthetic_launch
    previous = tmp_path / "previous"
    write_previous_evaluation(args, previous)
    assert evaluation.main([*args, "--previous-evaluation", str(previous)]) == 0
    with (output / "previous_evaluation/final_report.md").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="Historique"):
        verify_saved(output)


def test_d48_saved_result_without_history_is_not_publishable(synthetic_launch):
    args, _, _, output = synthetic_launch
    assert evaluation.main(args) == 0
    path = output / "final_metrics.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["decision_id"] = "D48"
    path.write_text(json.dumps(data), encoding="utf-8")
    manifest_path = output / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["final_metrics.json"] = evaluation.sha256(path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="historique"):
        verify_saved(output)


def test_historical_archives_republished_without_reading_originals(
    synthetic_launch, tmp_path, monkeypatch
):
    import sys
    from types import SimpleNamespace

    from ml.scripts import final_tracking

    args, source, _, output = synthetic_launch
    previous = tmp_path / "previous"
    write_previous_evaluation(args, previous)
    assert evaluation.main([*args, "--previous-evaluation", str(previous)]) == 0
    logged = []
    tags = {}

    class Run:
        info = SimpleNamespace(run_id="synthetic-history-run")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class Tracking:
        fail = True

        def set_tracking_uri(self, uri):
            pass

        def set_experiment(self, name):
            pass

        def start_run(self, **kwargs):
            return Run()

        def set_tags(self, values):
            tags.update(values)

        def log_params(self, values):
            pass

        def log_metrics(self, values):
            if self.fail:
                raise OSError("simulated tracking outage")

        def log_artifact(self, path, artifact_path=None):
            logged.append((Path(path).name, artifact_path))

    tracking = Tracking()
    monkeypatch.setitem(sys.modules, "mlflow", tracking)
    monkeypatch.setattr(
        final_tracking, "get_tracking_uri", lambda _: "http://localhost:5000"
    )
    assert final_tracking.publish_saved(output)["status"] == "failed"
    original_open = Path.open

    def saved_only(path, *a, **k):
        if path.resolve() == source.resolve() or path.resolve().is_relative_to(
            previous.resolve()
        ):
            pytest.fail(
                "Ni source finale ni originaux historiques ne doivent être relus"
            )
        return original_open(path, *a, **k)

    monkeypatch.setattr(Path, "open", saved_only)
    tracking.fail = False
    state = final_tracking.publish_saved(output)
    assert state["status"] == "published" and state["run_id"] == "synthetic-history-run"
    assert ("final_metrics.json", "previous_evaluation") in logged
    assert ("final_report.md", "previous_evaluation") in logged
    assert tags["measurement_number"] == "2"
    assert tags["measurement_independent"] == "false"
    assert tags["measurement_post_hoc"] == "true"


@pytest.mark.parametrize(
    "field,value",
    [
        ("n_transactions", float("nan")),
        ("n_transactions", float("inf")),
        ("n_transactions", float("-inf")),
        ("n_transactions", 0),
        ("n_transactions", -1),
        ("n_transactions", 4.5),
        ("n_transactions", "4"),
        ("n_transactions", True),
        ("n_transactions", None),
        ("fraud_count", -2),
        ("fraud_count", 5),
        ("fraud_count", 1.5),
        ("fraud_count", "2"),
        ("fraud_count", False),
        ("fraud_count", None),
        ("fraud_count", float("nan")),
        ("fraud_count", float("inf")),
        ("pr_auc", True),
        ("class_counts", None),
        ("covered_counts", None),
        ("class_counts", {"0": 3, "1": 2}),
        ("class_counts", {"0": 4, "1": 0}),
        ("class_counts", {"0": -1, "1": 2}),
        ("covered_counts", {"0": 3, "1": 2}),
        ("covered_counts", {"0": 1, "1": -1}),
        ("covered_counts", {"0": True, "1": 1}),
        ("extra_metrics", {"nested": [0.2, {"ece": float("nan")}]}),
        ("extra_metrics", {"nested": [float("inf")]}),
        ("extra_metrics", {"nested": [float("-inf")]}),
    ],
)
def test_invalid_historical_aggregates_rejected_before_reservation(
    synthetic_launch, tmp_path, monkeypatch, field, value
):
    args, source, journal, output = synthetic_launch
    previous = tmp_path / "previous"
    write_previous_evaluation(args, previous)
    path = previous / "final_metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8"))
    metrics["overall"][field] = value
    path.write_text(json.dumps(metrics), encoding="utf-8")
    original_history = path.read_bytes()
    original_journal = journal.read_bytes()
    opened = deny_source(monkeypatch, source)
    monkeypatch.setattr(
        evaluation,
        "reserve_source",
        lambda *a, **k: pytest.fail("réservation interdite"),
    )
    monkeypatch.setattr(
        evaluation,
        "bootstrap_intervals",
        lambda *a, **k: pytest.fail("bootstrap interdit"),
    )
    with pytest.raises(ValueError, match="historique|précédente"):
        evaluation.main([*args, "--previous-evaluation", str(previous)])
    assert not opened and not output.exists()
    assert journal.read_bytes() == original_journal
    assert path.read_bytes() == original_history


@pytest.mark.parametrize("frauds", [0, 4])
def test_historical_count_boundaries_and_undefined_metrics_are_preserved(
    synthetic_launch, tmp_path, frauds
):
    from ml.scripts.final_history import load_previous_evaluation

    args, _, _, _ = synthetic_launch
    previous = tmp_path / "previous"
    write_previous_evaluation(args, previous)
    path = previous / "final_metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8"))
    metrics["overall"] = {
        "n_transactions": 4,
        "fraud_count": frauds,
        "class_counts": {"0": 4 - frauds, "1": frauds},
        "covered_counts": {"0": 4 - frauds, "1": frauds},
        "coverage_by_class": {
            "0": 1.0 if frauds < 4 else None,
            "1": 1.0 if frauds else None,
        },
        "pr_auc": None,
        "review_rate": 0.0,
        "automatic_error_rate": None,
        "extra_metrics": {"undefined": None, "nested": [None, 0.25]},
    }
    original = (json.dumps(metrics) + "\n").encode()
    path.write_bytes(original)
    history, payloads = load_previous_evaluation(
        previous, metrics["model_sha256"], metrics["source_sha256"], 0.02
    )
    assert history["overall"] == metrics["overall"]
    assert history["overall"]["automatic_error_rate"] is None
    assert payloads["final_metrics.json"] == original
    json.dumps(history, allow_nan=False)


class ParityPreprocessor:
    def transform(self, frame):
        return frame[["amt"]].to_numpy(dtype=float)


class ParityClassifier:
    def predict_proba(self, features):
        p = 0.1 + np.asarray(features, dtype=float)[:, 0] / 2000
        return np.column_stack((1 - p, p))


class ParityCalibrator:
    def predict(self, probabilities):
        return np.asarray(probabilities) * 0.8 + 0.05


@pytest.mark.parametrize("nested", [False, True])
def test_evaluation_matches_serving_with_prior_and_calibration(nested):
    from validation.fold_data import correct_proba

    from ml.src.model.fraud_detector import FraudDetectorModel

    class NestedClassifier:
        def predict_proba(self, features):
            raw = ParityClassifier().predict_proba(features)[:, 1]
            p = ParityCalibrator().predict(correct_proba(raw, 0.5))
            return np.column_stack((1 - p, p))

    model = FraudDetectorModel(
        preprocessor=ParityPreprocessor(),
        classifier=NestedClassifier() if nested else ParityClassifier(),
        beta=None if nested else 0.5,
        calibrator=None if nested else ParityCalibrator(),
        threshold_legit=0.5,
        threshold_fraud=0.6,
        alpha=0.02,
    )
    frame = evaluation.synthetic_data()
    _, _, details = evaluation.evaluate(model, frame, return_details=True)
    records = frame.drop(columns="is_fraud").to_dict(orient="records")
    expected = np.array([model.calibrated_probability(record) for record in records])
    assert np.allclose(details["probabilities"], expected, rtol=0, atol=1e-12)
    for index, record in enumerate(records):
        serving = model.predict_one(record)
        assert serving["fraud_probability"] == pytest.approx(round(expected[index], 4))
        assert (
            serving["prediction_set"]
            == np.flatnonzero(details["members"][index]).tolist()
        )
    if not nested:
        uncorrected = ParityClassifier().predict_proba(
            ParityPreprocessor().transform(frame)
        )[:, 1]
        assert not np.allclose(details["probabilities"], uncorrected)


def test_no_batch_with_external_calibration_fails_closed():
    model = Candidate()
    model.beta = 0.5
    with pytest.raises(ValueError, match="batch_probabilities"):
        evaluation.evaluate(model, evaluation.synthetic_data())


def test_latency_mount_contract_without_reading_data(tmp_path):
    from validation.fold_data import guard_training_source

    assert (
        guard_training_source(tmp_path / "data/raw/fraudTrain.csv").name
        == "fraudTrain.csv"
    )
    assert (
        guard_training_source(tmp_path / "data/raw/FRAUDTRAIN.CSV").name
        == "FRAUDTRAIN.CSV"
    )
    with pytest.raises(ValueError, match="Source interdite"):
        guard_training_source(tmp_path / "data/fraudTrain.csv")
    with pytest.raises(ValueError, match="Source interdite"):
        guard_training_source(tmp_path / "data/raw/fraudTest.csv")


def test_complete_manifest_and_outputs_are_atomic(synthetic_launch, monkeypatch):
    args, _, _, output = synthetic_launch
    written = []
    original = evaluation.atomic_write

    def recorded(path, content):
        written.append(path.name)
        return original(path, content)

    monkeypatch.setattr(evaluation, "atomic_write", recorded)
    assert evaluation.main(args) == 0
    assert {
        "predictions.csv",
        "final_metrics.json",
        "fairness_groups.csv",
        "bootstrap_intervals.json",
        "final_report.md",
        "artifact_manifest.json",
    }.issubset(written)
    manifest = json.loads(
        (output / "artifact_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "complete"
    assert verify_saved(output)["model_status"] == "provisional"


def test_final_cli_refuses_auth_decision_before_opening_source(
    synthetic_launch, monkeypatch, capsys
):
    args, source, journal, output = synthetic_launch
    monkeypatch.setattr(evaluation, "FINAL_DECISION_ID", "D48")
    args[args.index("--decision-id") + 1] = "D47"
    original_journal = journal.read_bytes()
    opened = deny_source(monkeypatch, source)
    with pytest.raises(SystemExit):
        evaluation.main(args)
    assert "D47" in capsys.readouterr().err and not opened
    assert journal.read_bytes() == original_journal and not output.exists()


def test_legacy_auth_decision_is_refused_before_journal_read(tmp_path):
    with pytest.raises(ValueError, match="D47.*Auth"):
        journal_api.check_authorization(
            tmp_path / "not-created.jsonl",
            {},
            source_sha256="a" * 64,
            model_sha256="b" * 64,
            decision_id="D47",
            protocol_sha256="c" * 64,
            reason="synthetic",
        )


def test_final_synthetic_d48_with_history_and_single_use(
    synthetic_launch, tmp_path, monkeypatch
):
    args, source, journal, output = synthetic_launch
    monkeypatch.setattr(evaluation, "FINAL_DECISION_ID", "D48")
    source_hash = evaluation.sha256(source)
    model_hash = args[args.index("--model-sha256") + 1]
    protocol_hash = evaluation.sha256(Path(args[args.index("--protocol-file") + 1]))
    monkeypatch.setattr(journal_api, "LEGACY_SOURCE", source_hash)
    monkeypatch.setattr(journal_api, "LEGACY_MODEL", model_hash)
    legacy = [
        {
            "status": "started",
            "utc": "2026-11-10T18:00:00+00:00",
            "model_sha256": model_hash,
        },
        {"status": "completed", "source_sha256": source_hash},
    ]
    journal.write_text("".join(json.dumps(e) + "\n" for e in legacy), encoding="utf-8")
    authorization = Path(args[args.index("--authorization") + 1])
    authorization.write_text(
        json.dumps(approved(journal, "D48", source_hash, model_hash, protocol_hash)),
        encoding="utf-8",
    )
    args[args.index("--decision-id") + 1] = "D48"
    history = tmp_path / "historical"
    write_previous_evaluation(args, history)
    args += ["--previous-evaluation", str(history)]
    assert evaluation.main(args) == 0
    result = verify_saved(output)
    assert result["decision_id"] == "D48"
    assert result["measurement"]["independent"] is False
    assert result["promotion_ready"] is False
    args[args.index("--output-dir") + 1] = str(tmp_path / "second")
    opened = deny_source(monkeypatch, source)
    with pytest.raises(ValueError, match="consommée"):
        evaluation.main(args)
    assert not opened


@pytest.mark.parametrize("status", ["reserved", "completed"])
def test_d48_refuses_any_previous_d47_entry(tmp_path, status):
    journal = tmp_path / "journal.jsonl"
    legacy = [
        {
            "status": "started",
            "utc": "2026-11-10T18:00:00+00:00",
            "model_sha256": journal_api.LEGACY_MODEL,
        },
        {"status": "completed", "source_sha256": journal_api.LEGACY_SOURCE},
    ]
    journal.write_text("".join(json.dumps(e) + "\n" for e in legacy), encoding="utf-8")
    raw, _ = journal_api.read_journal(journal)
    journal_api._append(
        journal,
        raw,
        {
            "status": status,
            "utc": "2026-11-12T10:00:00+00:00",
            "launch_id": "old-synthetic",
            "decision_id": "D47",
            "model_sha256": "d" * 64,
            "source_sha256": "e" * 64,
            "protocol_sha256": "f" * 64,
        },
    )
    auth = approved(journal, "D48", journal_api.LEGACY_SOURCE, journal_api.LEGACY_MODEL)
    before = journal.read_bytes()
    with pytest.raises(ValueError, match="Entrée D47"):
        reserve(journal, auth, revision="different", name="copy.csv")
    assert journal.read_bytes() == before
