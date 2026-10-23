"""Supervision murale des essais ; aucun acces aux donnees ni a MLflow."""

from __future__ import annotations

import math
import multiprocessing as mp
from time import monotonic


def _send_result(connection, worker, args):
    try:
        connection.send({"status": "COMPLETE", "result": worker(*args)})
    except (ValueError, RuntimeError, ArithmeticError, TypeError, OSError) as exc:
        connection.send({"status": "FAIL", "exception_type": type(exc).__name__})
    finally:
        connection.close()


def run_in_subprocess(worker, args, *, seconds, deadline):
    """Borne demarrage et calcul par min(delai d'essai, temps d'etude restant).

    Les essais interrompus ne recoivent aucun score. Le nettoyage du processus
    est borne separement ; le processus parent conserve les runs et l'etude.
    """
    if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Delai d'essai fini strictement positif requis.")
    if not math.isfinite(deadline):
        raise ValueError("Echeance d'etude finie requise.")
    start = monotonic()
    remaining = deadline - start
    if remaining <= 0:
        return {"status": "FAIL", "reason": "study_timeout", "seconds": 0.0}
    budget = min(seconds, remaining)
    reason = "study_timeout" if remaining <= seconds else "trial_timeout"
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_send_result, args=(sender, worker, args))
    try:
        process.start()
        sender.close()
        if receiver.poll(max(0, budget - (monotonic() - start))):
            try:
                result = receiver.recv()
            except EOFError:
                result = {"status": "FAIL", "reason": "worker_exit"}
            if monotonic() - start > budget:
                result = {"status": "FAIL", "reason": reason}
        else:
            result = {"status": "FAIL", "reason": reason}
    finally:
        sender.close()
        receiver.close()
        if process.pid is not None:
            process.join(timeout=0 if process.is_alive() else 1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            if process.is_alive():
                raise RuntimeError("Le processus d'essai ne s'est pas arrete.")
            process.close()
    result["seconds"] = monotonic() - start
    return result


def timeout_summary(rows, *, alert_fraction=0.2):
    """Compte les essais interrompus ; alerte strictement au-dessus de 20 %."""
    timed_out = sum(
        row.get("reason") in {"trial_timeout", "study_timeout"} for row in rows
    )
    fraction = timed_out / len(rows) if rows else 0.0
    return {
        "attempted": len(rows),
        "completed": sum(row["status"] == "COMPLETE" for row in rows),
        "timeout_count": timed_out,
        "timeout_fraction": fraction,
        "timeout_alert": fraction > alert_fraction,
    }
