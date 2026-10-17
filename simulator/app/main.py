"""Simulator CLI entry point for replaying Sparkov transactions and chargebacks."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from app.config import settings
from app.feedback import FeedbackScheduler
from app.replayer import load_and_sort_transactions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SIMULATOR] %(message)s")
logger = logging.getLogger("simulator")


def run_simulation(
    data_path: Path,
    tps: float = 10.0,
    feedback_delay: float = 120.0,
    dry_run: bool = True,
    limit: int | None = None,
) -> None:
    """Run chronological transaction playback and schedule delayed chargebacks."""
    if not data_path.is_file():
        logger.error("Data file not found at %s", data_path)
        sys.exit(1)

    transactions = load_and_sort_transactions(data_path, limit=limit)
    scheduler = FeedbackScheduler(default_delay_seconds=feedback_delay)

    interval = 1.0 / max(tps, 0.1)
    logger.info("Starting simulation: %d transactions, %.1f TPS, dry_run=%s", len(transactions), tps, dry_run)

    for i, item in enumerate(transactions, 1):
        payload = item["payload"]
        trans_num = item["trans_num"]
        is_fraud = item["is_fraud"]

        if dry_run:
            logger.info(
                "[%d/%d] [DRY-RUN] Sent transNum=%s amount=%.2f is_fraud=%s",
                i, len(transactions), trans_num, payload["amount"], is_fraud,
            )
        else:
            # When gateway is deployed: post to /api/v1/transactions with JWT
            logger.info("Live submission for transNum=%s (pending gateway readiness)", trans_num)

        # Schedule delayed true label (chargeback)
        scheduler.schedule(trans_num, is_fraud, delay_seconds=feedback_delay)

        # Process any due feedback
        due_feedbacks = scheduler.get_due_feedbacks()
        for feedback in due_feedbacks:
            logger.info("[FEEDBACK] Dispatched true label for transNum=%s (isFraud=%s)", feedback["transNum"], feedback["isFraud"])

        time.sleep(interval)

    logger.info("Simulation completed. Pending chargeback feedback queue size: %d", scheduler.pending_count)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sparkov Transaction and Chargeback Simulator")
    parser.add_argument("--data-path", type=Path, default=Path(settings.data_path))
    parser.add_argument("--tps", type=float, default=settings.tps)
    parser.add_argument("--feedback-delay", type=float, default=settings.feedback_delay_seconds)
    parser.add_argument("--dry-run", action="store_true", default=settings.dry_run)
    parser.add_argument("--limit", type=int, default=settings.limit)

    args = parser.parse_args()
    run_simulation(
        data_path=args.data_path,
        tps=args.tps,
        feedback_delay=args.feedback_delay,
        dry_run=args.dry_run,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
