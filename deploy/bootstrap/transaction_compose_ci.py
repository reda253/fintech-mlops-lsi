"""Disposable Transaction integration test. Never uses the developer's Compose project."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import uuid

from transaction_smoke_test import assert_stays_ready, wait_for_checks


ROOT = Path(__file__).resolve().parents[2]


def assert_isolated(config, project):
    if not project.startswith("transaction-ci-") or config.get("name") != project:
        raise ValueError("Expected a private transaction-ci project")
    services = config["services"]
    for name in ("postgres", "rabbitmq"):
        if services[name].get("container_name") or services[name].get("ports"):
            raise ValueError(f"{name}: fixed name or exposed dependency port")
    mounts = services["postgres"].get("volumes", [])
    if len(mounts) != 1 or mounts[0].get("source") != "transaction_ci_data":
        raise ValueError("PostgreSQL must use only the disposable test volume")
    volume = config["volumes"]["transaction_ci_data"]
    if volume.get("external") or volume.get("name") != project + "_transaction_ci_data":
        raise ValueError("PostgreSQL volume must belong to this private project")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Image already built in this Docker daemon")
    parser.add_argument("--config-only", action="store_true", help="Validate isolation without starting containers")
    args = parser.parse_args()
    project = "transaction-ci-" + uuid.uuid4().hex[:12]
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = project
    env["TRANSACTION_IMAGE"] = args.image
    env["TRANSACTION_CI_POSTGRES_PASSWORD"] = secrets.token_hex(24)
    env["TRANSACTION_CI_RABBIT_PASSWORD"] = secrets.token_hex(24)
    db_password = secrets.token_hex(24)
    if env.get("GITHUB_ACTIONS") == "true":
        for password in (db_password, env["TRANSACTION_CI_POSTGRES_PASSWORD"], env["TRANSACTION_CI_RABBIT_PASSWORD"]):
            print(f"::add-mask::{password}", flush=True)
    compose = ["docker", "compose", "-p", project, "-f", "docker-compose.yml",
               "-f", "docker-compose.transaction.yml", "-f", "deploy/bootstrap/transaction-ci.override.yml"]

    def run(*arguments, capture=False, input_text=None, extra_env=None):
        return subprocess.run(
            compose + list(arguments), cwd=ROOT, env=env | (extra_env or {}),
            input=input_text, text=True, check=True, capture_output=capture,
            timeout=240,
        )

    with tempfile.TemporaryDirectory(prefix="transaction-ci-") as temporary:
        env_file = Path(temporary) / "transaction.env"
        env_file.write_text(
            f"DB_PASSWORD={db_password}\nRABBITMQ_USER=transaction_ci\n"
            f"RABBITMQ_PASSWORD={env['TRANSACTION_CI_RABBIT_PASSWORD']}\n",
            encoding="utf-8",
        )
        env["TRANSACTION_ENV_FILE"] = str(env_file)
        # Validate the merged model before allowing startup or destructive cleanup.
        config = json.loads(run("config", "--format", "json", capture=True).stdout)
        assert_isolated(config, project)
        if args.config_only:
            print("Transaction Compose configuration and isolation checks passed")
            return
        try:
            run("up", "-d", "--wait", "--wait-timeout", "120", "postgres", "rabbitmq")
            run(
                "exec", "-T", "-e", "DB_PASSWORD", "postgres", "psql", "-U", "fintech",
                "-d", "fintech", "-v", "ON_ERROR_STOP=1",
                extra_env={"DB_PASSWORD": db_password},
                input_text=(
                    "\\getenv transaction_pwd DB_PASSWORD\n"
                    "CREATE ROLE transaction_user LOGIN PASSWORD :'transaction_pwd';\n"
                    "CREATE SCHEMA transaction AUTHORIZATION transaction_user;\n"
                    "ALTER ROLE transaction_user SET search_path = transaction;\n"
                ),
            )
            run("up", "-d", "--no-build", "--wait", "--wait-timeout", "150", "transaction-service")
            user = run("exec", "-T", "transaction-service", "id", "-u", capture=True).stdout.strip()
            if user != "10001":
                raise AssertionError("Expected runtime UID 10001")
            port = run("port", "transaction-service", "8083", capture=True).stdout.strip()
            base_url = "http://" + port
            wait_for_checks(base_url)
            result = run("exec", "-T", "postgres", "psql", "-U", "fintech", "-d", "fintech",
                         "-Atc", "SELECT version FROM transaction.flyway_schema_history WHERE success ORDER BY installed_rank;",
                         capture=True).stdout.splitlines()
            if "1" not in result:
                raise AssertionError("Flyway V1 was not applied")
            # RabbitMQ is off the request path (outbox, D15): the pod must stay in rotation.
            print("Testing outage and recovery: rabbitmq (readiness must stay UP)", flush=True)
            run("stop", "rabbitmq")
            assert_stays_ready(base_url, duration=20)
            run("start", "rabbitmq")
            wait_for_checks(base_url, "UP", timeout=150)
            # Without PostgreSQL the service cannot work: the pod must leave rotation, then return.
            print("Testing outage and recovery: postgres (readiness must go DOWN)", flush=True)
            run("stop", "postgres")
            wait_for_checks(base_url, "DOWN", timeout=90)
            run("start", "postgres")
            wait_for_checks(base_url, "UP", timeout=150)
            print("Transaction integration passed: UID, Flyway, probes, security, dependency outages and recovery", flush=True)
        except Exception:
            # No `config` or `inspect` dump: those can expose credentials.
            try:
                run("logs", "--no-color", "--tail", "80", "transaction-service")
            except subprocess.SubprocessError:
                pass
            raise
        finally:
            run("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
