"""Test the reviewed Auth V1 to V2 upgrade in disposable Docker containers."""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, HTTPRedirectHandler, Request, build_opener


OLD = "e9a57d9ce1f864d1da5a027dfbdede644eb13fe7"
NEW = "e17a4934c6e9170e76014ea1e6ad195778f119a8"
REPO = "reda253/fintech-mlops-lsi"
MODULES = ("auth-service", "api-gateway", "postgres")
ME = "/api/v1/auth/me"
HISTORY = "SELECT version FROM auth.flyway_schema_history WHERE success ORDER BY installed_rank;"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def release_images(inventory):
    require(inventory.get("repository") == REPO and inventory.get("commit") == NEW
            and inventory.get("schema") == 1 and inventory.get("platform") == "linux/amd64",
            "Expected the reviewed e17a493 GHCR inventory")
    images = {}
    for module in MODULES:
        image = inventory.get("images", {}).get(module, "")
        require(isinstance(image, str) and re.fullmatch(
            re.escape(f"ghcr.io/{REPO}/{module}@sha256:") + r"[a-f0-9]{64}", image),
            f"Invalid image reference for {module}")
        images[module] = image
    return images


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


HTTP = build_opener(ProxyHandler({}), NoRedirect())


def request(port, path, payload=None, token=None):
    headers = {}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = Request(f"http://127.0.0.1:{port}{path}", headers=headers,
                  data=None if payload is None else json.dumps(payload).encode())
    try:
        with HTTP.open(req, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        error.close()
        return error.code, None


def wait_for(check, name):
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {name}")


def docker(*args, env=None, stdin=None, timeout=60):
    result = subprocess.run(["docker", *args], input=stdin, env=env, capture_output=True,
                            encoding="utf-8", timeout=timeout)
    if result.returncode:
        # Do not print Docker stdout/stderr: it can contain synthetic credentials.
        raise RuntimeError(f"Docker {args[0]} failed (exit {result.returncode})")
    return result.stdout.strip()


def image_revision(image):
    return docker("image", "inspect", "--format",
                  '{{index .Config.Labels "org.opencontainers.image.revision"}}', image)


def run(inventory, openssl):
    images = release_images(inventory)
    old_auth = f"fintech-auth-service:{OLD}"
    require(image_revision(old_auth) == OLD, "Missing or mismatched V1 local Auth image")
    for module, image in images.items():
        print(f"Pulling reviewed {module} image", flush=True)
        docker("pull", "--platform", "linux/amd64", image, timeout=300)
        require(image_revision(image) == NEW, f"Unexpected source revision for {module}")
    key = subprocess.run([openssl, "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
                         capture_output=True, text=True, check=True, timeout=60).stdout
    password = secrets.token_hex(24)
    prefix = "fintech-auth-upgrade-" + secrets.token_hex(6)
    with ExitStack() as cleanup:
        network = docker("network", "create", prefix)
        require(re.fullmatch(r"[a-f0-9]{64}", network), "Unexpected network ID")
        cleanup.callback(docker, "network", "rm", network)

        def start(name, image, variables, *flags, port=None, stack=cleanup):
            publish = ("-p", f"127.0.0.1::{port}") if port else ()
            options = [part for key_name in variables for part in ("-e", key_name)]
            container = docker("run", "-d", "--name", f"{prefix}-{name}", "--network", network,
                               "--network-alias", name, "--cap-drop", "ALL",
                               "--security-opt", "no-new-privileges", *publish, *flags, *options,
                               image, env=os.environ | variables)
            require(re.fullmatch(r"[a-f0-9]{64}", container), "Unexpected container ID")
            stack.callback(docker, "rm", "-f", "-v", container)
            if not port:
                return container
            binding = docker("port", container, f"{port}/tcp")
            require(re.fullmatch(r"127\.0\.0\.1:[0-9]+", binding), "Expected loopback-only binding")
            return int(binding.rsplit(":", 1)[1])

        db = start("postgres", images["postgres"], {
            "POSTGRES_PASSWORD": secrets.token_hex(24), "POSTGRES_DB": "fintech",
            "PGDATA": "/var/lib/postgresql/data/pgdata",
        }, "--memory", "512m", "--tmpfs", "/var/lib/postgresql/data:rw,uid=70,gid=70,mode=0700,size=256m")

        def pg_ready():
            try:
                docker("exec", db, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", "fintech")
                return True
            except RuntimeError:
                return False

        def sql(statement):
            return docker("exec", "-i", db, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                          "-U", "postgres", "-d", "fintech", stdin=statement)

        wait_for(pg_ready, "PostgreSQL")
        sql(f"CREATE ROLE auth_user LOGIN PASSWORD '{password}'; CREATE SCHEMA auth AUTHORIZATION auth_user;")
        auth_env = {"DB_URL": "jdbc:postgresql://postgres:5432/fintech",
                    "DB_USER": "auth_user", "DB_PASSWORD": password}
        app_flags = ("--memory", "512m", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=128m")

        def ready(port):
            return request(port, "/actuator/health/readiness") == (200, {"status": "UP"})

        with ExitStack() as v1:
            old_port = start("auth-v1", old_auth, auth_env, *app_flags, port=8081, stack=v1)
            wait_for(lambda: ready(old_port), "Auth V1")
            require(sql(HISTORY).splitlines() == ["1"], "Expected V1 only before upgrade")
            sql("INSERT INTO auth.users (id, username, password_hash, roles, enabled) "
                "VALUES ('9879fb23-7b7d-4529-807e-3bf2be571054', 'upgrade-fixture', "
                "'not-a-login-hash', ARRAY['ANALYSTE'], false);")
        print("Baseline: Auth V1 applied and fixture row inserted.", flush=True)
        auth_port = start("auth", images["auth-service"], auth_env | {"JWT_PRIVATE_KEY": key},
                          *app_flags, port=8081)
        wait_for(lambda: ready(auth_port), "Auth V2")
        require(sql(HISTORY).splitlines() == ["1", "2"], "Expected successful V1 and V2 migrations")
        require(sql("SELECT username FROM auth.users WHERE id = '9879fb23-7b7d-4529-807e-3bf2be571054' "
                    "AND NOT enabled;") == "upgrade-fixture", "Pre-upgrade row not preserved")
        print("Upgrade: Flyway V2 applied and V1 data preserved.", flush=True)

        gateway = start("gateway", images["api-gateway"], {
            "AUTH_URI": "http://auth:8081", "JWKS_URI": "http://auth:8081/.well-known/jwks.json",
        }, *app_flags, port=8080)
        wait_for(lambda: ready(gateway), "Gateway")
        require(request(gateway, ME)[0] == 401, "Gateway did not reject anonymous request")
        require(request(gateway, ME, token="invalid-test-token")[0] == 401,
                "Gateway did not reject invalid token")
        status, login = request(gateway, "/api/v1/auth/login", {
            "username": "admin", "password": "admin-demo-2026",
        })
        require(status == 200 and isinstance(login, dict) and isinstance(login.get("accessToken"), str),
                f"Fixture login through Gateway failed (HTTP {status})")
        status, user = request(gateway, ME, token=login["accessToken"])
        require(status == 200 and isinstance(user, dict) and user.get("username") == "admin",
                f"Gateway/Auth did not accept the issued JWT (HTTP {status})")
        print("Gateway: anonymous and invalid JWT rejected; signed JWT accepted by /me.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--openssl", default="openssl")
    args = parser.parse_args()
    run(json.loads(args.inventory.read_text(encoding="utf-8")), args.openssl)
