"""Test the frontend in a private Compose project with an explicit fake Gateway."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid

from frontend_smoke_test import request, wait_for_checks


ROOT = Path(__file__).resolve().parents[2]


def assert_isolated(config, project):
    if not project.startswith("frontend-ci-") or config.get("name") != project or config.get("volumes"):
        raise ValueError("Expected isolated frontend-ci project without named volumes")
    for service in config["services"].values():
        if service.get("container_name"):
            raise ValueError("Fixed container names are not allowed in this fixture")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--browser-tests", action="store_true", help="Requires local npm dependencies and Playwright Chromium")
    args = parser.parse_args()
    project = "frontend-ci-" + uuid.uuid4().hex[:12]
    env = os.environ.copy() | {"FRONTEND_IMAGE": args.image}
    compose = ["docker", "compose", "-p", project, "-f", "deploy/bootstrap/frontend-ci.compose.yml"]

    def run(*arguments, capture=False, timeout=180):
        return subprocess.run(compose + list(arguments), cwd=ROOT, env=env,
                              text=True, check=True, capture_output=capture, timeout=timeout)

    config = json.loads(run("config", "--format", "json", capture=True).stdout)
    assert_isolated(config, project)
    try:
        run("up", "-d", "--wait", "--wait-timeout", "90")
        uid = run("exec", "-T", "frontend", "id", "-u", capture=True).stdout.strip()
        if uid != "10001":
            raise AssertionError("Expected frontend UID 10001")
        port = run("port", "frontend", "8080", capture=True).stdout.strip()
        base_url = "http://" + port
        wait_for_checks(base_url)
        for invalid in ("http://gateway:8080/path", "http://gateway:99999", "http://user:pass@gateway:8080",
                        "http://gateway:8080\ninvalid directive;", "https://gateway:8080"):
            try:
                run("run", "--rm", "--no-deps", "-e", "GATEWAY_UPSTREAM=" + invalid, "frontend", capture=True, timeout=20)
            except subprocess.CalledProcessError as error:
                if error.returncode != 1 or "GATEWAY_UPSTREAM" not in error.stderr:
                    raise AssertionError("Expected entrypoint validation failure") from error
            else:
                raise AssertionError("Invalid upstream was accepted")
        if args.browser_tests:
            executable = "npm.cmd" if os.name == "nt" else "npm"
            subprocess.run(
                [executable, "exec", "--", "playwright", "test", "--config", "playwright.docker.config.ts"],
                cwd=ROOT / "frontend", env=env | {"FRONTEND_BASE_URL": base_url}, check=True, timeout=180,
            )
        run("stop", "api-gateway")
        status, _, body = request(base_url, "/healthz")
        if status != 200 or json.loads(body) != {"status": "UP"}:
            raise AssertionError("Frontend health must not depend on Gateway availability")
        if request(base_url, "/api/v1/echo")[0] not in (502, 504):
            raise AssertionError("Gateway outage must not return a fake SPA HTTP 200")
        run("start", "api-gateway")
        wait_for_checks(base_url)
    except Exception:
        try:
            run("logs", "--no-color", "--tail", "50")
        except subprocess.SubprocessError:
            pass
        raise
    finally:
        run("down", "--remove-orphans")


if __name__ == "__main__":
    main()
