"""HTTP checks for Transaction; no credentials or third-party Python packages."""

import argparse
import json
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(base_url, path, method="GET"):
    correlation_id = str(uuid.uuid4())
    req = Request(
        base_url.rstrip("/") + path,
        headers={"X-Correlation-Id": correlation_id},
        method=method,
    )
    try:
        response = urlopen(req, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        body = json.loads(response.read())
        if response.headers.get("X-Correlation-Id") != correlation_id:
            raise AssertionError(f"{method} {path}: correlation ID not preserved")
        return response.status, response.headers, body


def verify(base_url, expected_readiness="UP"):
    status, _, body = request(base_url, "/actuator/health/liveness")
    if status != 200 or body.get("status") != "UP":
        raise AssertionError("Liveness must remain HTTP 200 UP")
    status, _, body = request(base_url, "/actuator/health/readiness")
    expected_status = 200 if expected_readiness == "UP" else 503
    if status != expected_status or body.get("status") != expected_readiness:
        raise AssertionError(f"Readiness must be HTTP {expected_status} {expected_readiness}")
    for method, path in (
        ("GET", "/actuator/prometheus"),
        ("GET", "/actuator/health"),
        ("GET", "/api/v1/transactions"),
        ("POST", "/actuator/health/liveness"),
        ("POST", "/actuator/health/readiness"),
    ):
        status, headers, body = request(base_url, path, method)
        if status != 401 or not headers.get("WWW-Authenticate", "").startswith("Bearer"):
            raise AssertionError(f"{method} {path}: expected HTTP 401 Bearer")
        if body.get("status") != 401:
            raise AssertionError(f"{method} {path}: expected Problem Details status 401")


def wait_for_checks(base_url, expected_readiness="UP", timeout=120):
    deadline = time.monotonic() + timeout
    while True:
        try:
            verify(base_url, expected_readiness)
            return
        except (AssertionError, URLError, OSError, ValueError) as error:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"HTTP checks timed out: {error}") from error
            time.sleep(2)


def assert_stays_ready(base_url, duration=20):
    """Readiness must stay UP for the whole window (e.g. RabbitMQ down: the outbox buffers)."""
    deadline = time.monotonic() + duration
    while True:
        try:
            verify(base_url, "UP")
        except (AssertionError, URLError, OSError, ValueError) as error:
            raise RuntimeError(f"Readiness left UP during the outage: {error}") from error
        if time.monotonic() >= deadline:
            return
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--expected-readiness", choices=("UP", "DOWN"), default="UP")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    wait_for_checks(args.base_url, args.expected_readiness, args.timeout)
    print(f"HTTP checks passed: readiness {args.expected_readiness}, liveness UP, protected routes 401")


if __name__ == "__main__":
    main()
