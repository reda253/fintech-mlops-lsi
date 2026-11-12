"""Verify SealedSecret-to-Auth JWT wiring on the disposable GitOps kind lab."""

import argparse
import copy
import json
from pathlib import Path
import secrets
import subprocess
from urllib.parse import urlsplit
from uuid import uuid4

from auth_upgrade_smoke import HISTORY, ME, release_images, request
from check_kubernetes_data import validate_data
from check_kubernetes_manifests import kubectl, render, require, validate
from kubernetes_data_smoke import PortForward, secret
from kubernetes_kind_smoke import OWNER_LABEL, PREFIX, can_cleanup


CONTEXT = "kind-fintech-gitops-lab"
NODE = "fintech-gitops-lab-control-plane"
SIGNING_SECRET = "auth-signing-test"


def signing_env():
    return {"name": "JWT_PRIVATE_KEY",
            "valueFrom": {"secretKeyRef": {"name": SIGNING_SECRET, "key": "private-key"}}}


def workload_resources(apps, data, namespace, images):
    validate(apps, allow_placeholder=True)
    validate_data(data, allow_placeholder=True)
    apps = copy.deepcopy([item for item in apps
                          if item["metadata"]["name"] in {"auth-service", "api-gateway"}
                          or item["metadata"]["name"].startswith(("auth-service-config-", "api-gateway-config-"))])
    postgres = copy.deepcopy(next(item for item in data if item["kind"] == "StatefulSet"
                                  and item["metadata"]["name"] == "postgres"))
    postgres_service = copy.deepcopy(next(item for item in data if item["kind"] == "Service"
                                          and item["metadata"]["name"] == "postgres"))
    headless = copy.deepcopy(next(item for item in data if item["kind"] == "Service"
                                  and item["metadata"]["name"] == "postgres-headless"))
    auth_url = f"http://auth-service.{namespace}.svc.cluster.local:8081"
    for item in apps:
        name = item["metadata"]["name"]
        if item["kind"] == "Deployment":
            item["spec"]["replicas"] = 1
            container = item["spec"]["template"]["spec"]["containers"][0]
            container.update(image=images[name], imagePullPolicy="Always")
            if name == "auth-service":
                container["env"] = [entry for entry in container["env"]
                                    if not entry["name"].startswith("RABBITMQ_")] + [signing_env()]
        elif item["kind"] == "ConfigMap":
            config = item["data"]
            config["JWKS_URI"] = auth_url + "/.well-known/jwks.json"
            if name.startswith("auth-service-"):
                config.update(DB_URL=f"jdbc:postgresql://postgres.{namespace}.svc.cluster.local:5432/fintech",
                              RABBITMQ_HOST="127.0.0.1")
            else:
                config.update({key: "http://127.0.0.1:9" for key in config if key.endswith("_URI")
                               and key not in {"AUTH_URI", "JWKS_URI"}})
                config["AUTH_URI"] = auth_url
    postgres["spec"].pop("volumeClaimTemplates")
    postgres["spec"].pop("persistentVolumeClaimRetentionPolicy")
    pod = postgres["spec"]["template"]["spec"]
    pod["nodeSelector"] = {"kubernetes.io/hostname": NODE}
    pod["volumes"].append({"name": "data", "emptyDir": {"sizeLimit": "512Mi"}})
    pg = pod["containers"][0]
    pg.update(image=images["postgres"], imagePullPolicy="Always")
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        pg[probe]["exec"]["command"][1:1] = ["-h", "127.0.0.1"]
    data = [postgres, postgres_service, headless]
    for item in apps + data:
        item["metadata"]["namespace"] = namespace
    return apps, data


def install(namespace, objects):
    # Create, not apply: avoid last-applied annotations on temporary Secrets.
    result = kubectl(CONTEXT, "-n", namespace, "create", "-f", "-", capture_output=True,
                     input=json.dumps({"apiVersion": "v1", "kind": "List", "items": objects}))
    print(result.stdout.strip(), flush=True)


def seal_key(namespace, key, kubeseal):
    result = subprocess.run(
        [kubeseal, "--context", CONTEXT, "--scope", "strict", "--format", "json"],
        input=json.dumps(secret(namespace, SIGNING_SECRET, {"private-key": key})),
        capture_output=True, text=True, check=True, timeout=60,
    )
    sealed = json.loads(result.stdout)
    require(sealed.get("kind") == "SealedSecret"
            and sealed["metadata"]["name"] == SIGNING_SECRET
            and sealed["metadata"]["namespace"] == namespace
            and set(sealed["spec"]["encryptedData"]) == {"private-key"}, "Unexpected sealing output")
    return sealed


def verify_login(port):
    require(request(port, ME)[0] == 401, "Expected anonymous HTTP 401")
    require(request(port, ME, token="invalid-test-token")[0] == 401, "Expected invalid JWT HTTP 401")
    code, login = request(port, "/api/v1/auth/login", {"username": "admin", "password": "admin-demo-2026"})
    require(code == 200 and isinstance(login, dict) and isinstance(login.get("accessToken"), str),
            f"Fixture login failed (HTTP {code})")
    code, profile = request(port, ME, token=login["accessToken"])
    require(code == 200 and isinstance(profile, dict) and profile.get("username") == "admin",
            f"Signed JWT was not accepted (HTTP {code})")


def run(inventory, openssl, kubeseal):
    images = release_images(inventory)
    nodes = json.loads(kubectl(CONTEXT, "get", "nodes", "-o", "json", capture_output=True).stdout)
    require([item["metadata"]["name"] for item in nodes["items"]] == [NODE],
            "Expected exactly the disposable GitOps lab node")
    namespace, owner = PREFIX + uuid4().hex[:12], uuid4().hex
    apps, data = workload_resources(render(CONTEXT), render(CONTEXT, "deploy/k8s/data"), namespace, images)
    key = subprocess.run([openssl, "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
                         capture_output=True, text=True, check=True, timeout=60).stdout
    db_password = secrets.token_hex(24)
    result = kubectl(CONTEXT, "create", "-f", "-", "-o", "json", capture_output=True, input=json.dumps({
        "apiVersion": "v1", "kind": "Namespace",
        "metadata": {"name": namespace, "labels": {OWNER_LABEL: owner}},
    }))
    uid = json.loads(result.stdout)["metadata"]["uid"]
    try:
        install(namespace, [
            seal_key(namespace, key, kubeseal),
            secret(namespace, "postgres-admin", {"password": secrets.token_hex(24)}),
            secret(namespace, "auth-service-db", {"username": "auth_user", "password": db_password}),
            *data,
        ])
        kubectl(CONTEXT, "-n", namespace, "wait", "--for=condition=Synced",
                "sealedsecret/" + SIGNING_SECRET, "--timeout=90s")
        kubectl(CONTEXT, "-n", namespace, "rollout", "status", "statefulset/postgres",
                "--timeout=240s", timeout=250)

        def sql(statement):
            return kubectl(CONTEXT, "-n", namespace, "exec", "-i", "postgres-0", "--", "psql",
                           "-XqAt", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "fintech",
                           input=statement, capture_output=True).stdout.strip()

        sql(f"CREATE ROLE auth_user LOGIN PASSWORD '{db_password}'; CREATE SCHEMA auth AUTHORIZATION auth_user;")
        install(namespace, apps)
        for name in ("auth-service", "api-gateway"):
            kubectl(CONTEXT, "-n", namespace, "rollout", "status", "deployment/" + name,
                    "--timeout=240s", timeout=250)
        require(sql(HISTORY).splitlines() == ["1", "2"], "Expected Flyway V1 and V2 on the fixture database")
        with PortForward(CONTEXT, namespace, "service/api-gateway", 8080) as url:
            verify_login(urlsplit(url).port)
        print("PASS: sealed signing key, Flyway V1/V2 and Gateway JWT verified in the lab.")
    finally:
        result = kubectl(CONTEXT, "get", "namespace", namespace, "-o", "json", capture_output=True)
        metadata = json.loads(result.stdout)["metadata"]
        require(metadata["uid"] == uid and can_cleanup(namespace, metadata, owner),
                f"Cannot confirm cleanup ownership of {namespace}")
        kubectl(CONTEXT, "delete", "namespace", namespace, "--timeout=100s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--openssl", default="openssl")
    parser.add_argument("--kubeseal", default="kubeseal")
    args = parser.parse_args()
    run(json.loads(args.inventory.read_text(encoding="utf-8")), args.openssl, args.kubeseal)
