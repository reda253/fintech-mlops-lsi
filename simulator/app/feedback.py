"""Delayed true labels dispatcher for simulated chargebacks (Decision D19, §5.9)."""

from __future__ import annotations

import heapq
import logging
import time
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class FeedbackScheduler:
    """Schedules and dispatches delayed ground truth feedback to risk-service."""

    def __init__(self, default_delay_seconds: float = 120.0):
        self.default_delay_seconds = default_delay_seconds
        self._heap: list[tuple[float, str, bool]] = []

    def schedule(self, trans_num: str, is_fraud: bool, delay_seconds: float | None = None) -> float:
        """Schedule a feedback event for trans_num. Returns the due epoch timestamp."""
        delay = self.default_delay_seconds if delay_seconds is None else delay_seconds
        due_time = time.time() + delay
        heapq.heappush(self._heap, (due_time, trans_num, is_fraud))
        return due_time

    def get_due_feedbacks(self, now: float | None = None) -> list[dict[str, Any]]:
        """Pop and return all feedback payloads whose delay has expired."""
        current_time = time.time() if now is None else now
        due_items = []

        while self._heap and self._heap[0][0] <= current_time:
            due_time, trans_num, is_fraud = heapq.heappop(self._heap)
            reported_at = datetime.fromtimestamp(due_time, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            due_items.append({
                "transNum": trans_num,
                "isFraud": is_fraud,
                "reportedAt": reported_at,
            })

        return due_items

    @property
    def pending_count(self) -> int:
        return len(self._heap)
