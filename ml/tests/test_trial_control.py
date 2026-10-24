"""Le timeout est une fonctionnalite testee, pas une assertion de performance."""

from time import monotonic, sleep

import pytest
from benchmark.trial_control import run_in_subprocess, timeout_summary


def echo(value):
    return value


def wait_forever():
    while True:
        sleep(1)


def test_spawn_returns_real_worker_result():
    result = run_in_subprocess(echo, (42,), seconds=300, deadline=monotonic() + 300)
    assert result["status"] == "COMPLETE"
    assert result["result"] == 42


def test_timeout_interrupts_worker_without_fake_score():
    result = run_in_subprocess(
        wait_forever, (), seconds=0.05, deadline=monotonic() + 300
    )
    assert result["status"] == "FAIL"
    assert result["reason"] == "trial_timeout"
    assert "result" not in result


def test_expired_study_does_not_start_worker():
    result = run_in_subprocess(wait_forever, (), seconds=300, deadline=monotonic() - 1)
    assert result["reason"] == "study_timeout"
    assert result["seconds"] == 0


@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan"), True])
def test_invalid_timeout_rejected(seconds):
    with pytest.raises(ValueError, match="Delai"):
        run_in_subprocess(echo, (1,), seconds=seconds, deadline=monotonic() + 1)


def test_alert_is_strictly_above_twenty_percent():
    completed = {"status": "COMPLETE"}
    interrupted = {"status": "FAIL", "reason": "trial_timeout"}
    at_boundary = timeout_summary([interrupted, *([completed] * 4)])
    assert at_boundary["timeout_count"] == 1
    assert at_boundary["timeout_fraction"] == 0.2
    assert at_boundary["timeout_alert"] is False
    above = timeout_summary([interrupted, interrupted, *([completed] * 3)])
    assert above["timeout_count"] == 2
    assert above["timeout_alert"] is True


def test_empty_summary_is_not_an_alert():
    assert timeout_summary([]) == {
        "attempted": 0,
        "completed": 0,
        "timeout_count": 0,
        "timeout_fraction": 0.0,
        "timeout_alert": False,
    }
