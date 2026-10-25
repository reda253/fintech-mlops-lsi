"""Check the actual static server and proxy against the disposable Gateway fixture."""

from html.parser import HTMLParser
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        path = attributes.get("src") if tag == "script" else attributes.get("href") if tag == "link" else None
        if path and path.startswith("/assets/"):
            self.paths.append(path)


def request(base_url, path, *, method="GET", data=None, headers=None):
    req = Request(base_url.rstrip("/") + path, data=data, headers=headers or {}, method=method)
    try:
        response = urlopen(req, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


def verify_static(base_url):
    status, headers, index = request(base_url, "/")
    if status != 200 or b'<div id="root"></div>' not in index:
        raise AssertionError("Expected compiled React HTML")
    if headers.get("X-Content-Type-Options") != "nosniff":
        raise AssertionError("Expected nosniff response header")
    for path in ("/login", "/dashboard", "/clients/test-id"):
        if request(base_url, path)[2] != index:
            raise AssertionError(f"SPA fallback failed: {path}")
    if "no-cache" not in request(base_url, "/index.html")[1].get("Cache-Control", ""):
        raise AssertionError("index.html must not be cached long-term")
    assets = Assets()
    assets.feed(index.decode())
    if not assets.paths:
        raise AssertionError("No compiled assets found")
    for path in assets.paths:
        status, headers, body = request(base_url, path)
        if status != 200 or not body or body == index or "max-age=31536000" not in headers.get("Cache-Control", ""):
            raise AssertionError(f"Missing or uncached compiled asset: {path}")
    for path in ("/assets/missing.js", "/.env", "/actuator/health", "/internal/ping", "/predict"):
        if request(base_url, path)[0] != 404:
            raise AssertionError(f"Expected HTTP 404 for {path}")
    status, _, health = request(base_url, "/healthz")
    if status != 200 or json.loads(health) != {"status": "UP"}:
        raise AssertionError("Frontend healthcheck failed")


def verify_proxy(base_url):
    path = "/api/v1/echo?query=a%20b"
    status, _, body = request(base_url, path, method="POST", data=b'{"test":true}', headers={
        "Authorization": "Bearer frontend-ci-test", "X-Correlation-Id": "frontend-ci", "Content-Type": "application/json",
    })
    result = json.loads(body)
    if status != 200 or result != {
        "status": 200, "path": path, "method": "POST", "authorization": "Bearer frontend-ci-test",
        "correlationId": "frontend-ci", "body": '{"test":true}',
    }:
        raise AssertionError("Proxy did not preserve path, query, method, body or headers")
    status, headers, _ = request(base_url, "/api/v1/denied")
    if status != 401 or headers.get("WWW-Authenticate") != "Bearer":
        raise AssertionError("Upstream authentication rejection was not preserved")
    with urlopen(base_url + "/api/v1/notifications/stream", timeout=3) as response:
        if response.headers.get_content_type() != "text/event-stream" or response.readline() != b"event: ping\n":
            raise AssertionError("SSE event was not delivered immediately")


def wait_for_checks(base_url, timeout=60):
    deadline = time.monotonic() + timeout
    while True:
        try:
            verify_static(base_url)
            verify_proxy(base_url)
            print("Frontend checks passed: SPA, assets, cache, health, proxy, auth rejection and SSE", flush=True)
            return
        except (AssertionError, URLError, OSError, ValueError) as error:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Frontend checks timed out: {error}") from error
            time.sleep(2)
