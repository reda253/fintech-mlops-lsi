"""Journal verrouillé et autorisations explicites des mesures finales."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from ml.src.evaluation.final_artifacts import (
    APPROVED_D48_MODEL_SHA256,
    APPROVED_D48_SOURCE_SHA256,
)

LEGACY_SOURCE = APPROVED_D48_SOURCE_SHA256
LEGACY_MODEL = APPROVED_D48_MODEL_SHA256


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@contextmanager
def journal_lock(journal: Path):
    """Aucune suppression automatique d'un verrou préexistant."""
    if not journal.parent.is_dir():
        raise ValueError("Journal absent ou montage indisponible")
    lock = journal.with_name(journal.name + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            "Journal verrouillé : vérifier le processus et sauvegarder le journal ; "
            "récupération manuelle explicite requise, aucun verrou supprimé"
        ) from exc
    try:
        os.write(
            fd,
            json.dumps(
                {"pid": os.getpid(), "utc": datetime.now(UTC).isoformat()}
            ).encode(),
        )
        os.fsync(fd)
        yield
    finally:
        os.close(fd)
        lock.unlink()


def read_journal(journal: Path) -> tuple[bytes, list[dict]]:
    if not journal.is_file():
        raise ValueError(
            "Journal central absent ou montage indisponible ; refus de lecture"
        )
    raw = journal.read_bytes()
    if not raw.strip() or not raw.endswith(b"\n"):
        raise ValueError("Journal vide ou tronqué ; restauration vérifiée obligatoire")
    entries = []
    prefix = b""
    for number, line in enumerate(raw.splitlines(keepends=True), 1):
        try:
            entry = json.loads(line)
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"Journal tronqué ou invalide, ligne {number}") from exc
        if not isinstance(entry, dict) or entry.get("status") not in {
            "started",
            "reserved",
            "predictions_saved",
            "completed",
            "failed",
        }:
            raise ValueError(f"Entrée du journal invalide, ligne {number}")
        if "entry_sha256" not in entry:
            if entry.get("status") == "started":
                if not re.fullmatch(
                    r"[0-9a-f]{64}", str(entry.get("model_sha256", ""))
                ) or not entry.get("utc"):
                    raise ValueError(f"Entrée ancienne incomplète, ligne {number}")
            elif (
                entry.get("status") != "completed"
                or entry.get("launch_id")
                or not re.fullmatch(
                    r"[0-9a-f]{64}", str(entry.get("source_sha256", ""))
                )
            ):
                raise ValueError(
                    f"Entrée du journal incomplète ou modifiée, ligne {number}"
                )
        if "entry_sha256" in entry:
            recorded = entry.pop("entry_sha256")
            actual = digest_bytes(
                json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()
            )
            if recorded != actual or entry.get("previous_sha256") != digest_bytes(
                prefix
            ):
                raise ValueError(f"Journal modifié, ligne {number}")
            entry["entry_sha256"] = recorded
            required = (
                "launch_id",
                "decision_id",
                "model_sha256",
                "source_sha256",
                "protocol_sha256",
                "utc",
            )
            if any(not entry.get(key) for key in required):
                raise ValueError(f"Entrée du journal incomplète, ligne {number}")
        entries.append(entry)
        prefix += line
    return raw, entries


def _legacy_anchor(entries: list[dict]) -> bool:
    return any(
        first.get("status") == "started"
        and first.get("model_sha256") == LEGACY_MODEL
        and str(first.get("utc", "")).startswith("2026-11-10")
        and second.get("status") == "completed"
        and second.get("source_sha256") == LEGACY_SOURCE
        for first, second in pairwise(entries)
    )


def check_authorization(
    journal: Path,
    authorization: dict,
    *,
    source_sha256: str,
    model_sha256: str,
    decision_id: str,
    protocol_sha256: str,
    reason: str | None,
) -> tuple[bytes, list[dict]]:
    if decision_id == "D47":
        raise ValueError(
            "D47 est réservée à Auth ; décision D48 requise pour cette évaluation"
        )
    raw, entries = read_journal(journal)
    if decision_id == "D48" and any(
        entry.get("decision_id") == "D47" for entry in entries
    ):
        raise ValueError(
            "Entrée D47 présente dans le journal : examen manuel requis avant D48"
        )
    if not re.fullmatch(r"D[0-9]+", decision_id or ""):
        raise ValueError("Identifiant de décision explicite requis")
    for value in (source_sha256, model_sha256, protocol_sha256):
        if not re.fullmatch(r"[0-9a-f]{64}", value or ""):
            raise ValueError("SHA-256 valide requis pour source, modèle et protocole")
    if decision_id == "D48" and (
        source_sha256 != LEGACY_SOURCE or model_sha256 != LEGACY_MODEL
    ):
        raise ValueError("D48 : source et modèle doivent rester ceux du 10 novembre")
    if decision_id == "D48" and not _legacy_anchor(entries):
        raise ValueError("D48 : entrée attendue du 10 novembre absente ou modifiée")
    if any(
        e.get("status") == "completed" and e.get("decision_id") == decision_id
        for e in entries
    ):
        raise ValueError(
            "Autorisation déjà consommée : nouvelle décision approuvée obligatoire"
        )
    terminal = {
        e.get("launch_id")
        for e in entries
        if e.get("status") in {"completed", "failed"}
    }
    if any(
        e.get("status") == "reserved"
        and e.get("launch_id") not in terminal
        and (
            e.get("source_sha256") == source_sha256
            or e.get("decision_id") == decision_id
        )
        for e in entries
    ):
        raise ValueError(
            "Autorisation ou source déjà réservée ; revue manuelle obligatoire"
        )
    expected = {
        "decision_id": decision_id,
        "source_sha256": source_sha256,
        "model_sha256": model_sha256,
        "protocol_sha256": protocol_sha256,
        "journal_sha256": digest_bytes(raw),
        "approved": True,
    }
    if any(authorization.get(key) != value for key, value in expected.items()):
        raise ValueError(
            "Autorisation absente, journal modifié ou liaison décision/source/modèle/protocole incorrecte"
        )
    if not reason or not reason.strip():
        raise ValueError("--reason explicite obligatoire avant lecture")
    return raw, entries


def _append(journal: Path, raw: bytes, entry: dict) -> None:
    entry = {**entry, "previous_sha256": digest_bytes(raw)}
    entry["entry_sha256"] = digest_bytes(
        json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()
    )
    with journal.open("ab") as stream:
        stream.write((json.dumps(entry, ensure_ascii=False) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def reserve_source(
    journal: Path,
    source_name: str,
    source_sha256: str,
    model_sha256: str,
    reason: str | None,
    *,
    decision_id: str,
    protocol_revision: str,
    protocol_sha256: str,
    authorization: dict,
) -> str:
    """Réserve sous verrou ; le libellé de révision n'est pas une autorisation."""
    if not protocol_revision or not protocol_revision.strip():
        raise ValueError("Révision de protocole explicite requise")
    with journal_lock(journal):
        raw, _ = check_authorization(
            journal,
            authorization,
            source_sha256=source_sha256,
            model_sha256=model_sha256,
            decision_id=decision_id,
            protocol_sha256=protocol_sha256,
            reason=reason,
        )
        launch_id = uuid.uuid4().hex
        _append(
            journal,
            raw,
            {
                "status": "reserved",
                "utc": datetime.now(UTC).isoformat(),
                "launch_id": launch_id,
                "source_name": source_name,
                "source_sha256": source_sha256,
                "model_sha256": model_sha256,
                "decision_id": decision_id,
                "protocol_revision": protocol_revision,
                "protocol_sha256": protocol_sha256,
                "reason": reason.strip(),
                "authorization_sha256": digest_bytes(
                    json.dumps(authorization, sort_keys=True).encode()
                ),
            },
        )
    return launch_id


def record_event(journal: Path, launch_id: str, status: str, **details) -> None:
    """Les sauvegardes et la complétion utilisent le même verrou que la réservation."""
    if status not in {"predictions_saved", "completed"}:
        raise ValueError("Statut terminal ou de sauvegarde invalide")
    with journal_lock(journal):
        raw, entries = read_journal(journal)
        matches = [e for e in entries if e.get("launch_id") == launch_id]
        reservation = next((e for e in matches if e["status"] == "reserved"), None)
        if reservation is None or any(e["status"] == "completed" for e in matches):
            raise ValueError("Réservation absente ou autorisation déjà consommée")
        if status == "completed" and not any(
            e["status"] == "predictions_saved" for e in matches
        ):
            raise ValueError("Prédictions non sauvegardées ; complétion refusée")
        binding = {
            key: reservation[key]
            for key in (
                "launch_id",
                "decision_id",
                "model_sha256",
                "source_sha256",
                "protocol_sha256",
                "protocol_revision",
            )
        }
        if set(details) & set(binding):
            raise ValueError("La liaison d'autorisation ne peut pas être modifiée")
        _append(
            journal,
            raw,
            {
                **details,
                **binding,
                "status": status,
                "utc": datetime.now(UTC).isoformat(),
            },
        )
