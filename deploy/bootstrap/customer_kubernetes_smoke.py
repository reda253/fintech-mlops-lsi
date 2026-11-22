"""Exercise Customer seeding with a synthetic CSV in the disposable GitOps lab."""

import argparse
import copy
import csv
import hashlib
import hmac
from io import StringIO
import json
from pathlib import Path
import secrets
import subprocess
from urllib.parse import urlsplit

from auth_kubernetes_smoke import CONTEXT, NODE, install, run, seal_secret, team_profile
from auth_upgrade_smoke import image_revision, request
from check_kubernetes_manifests import kubectl, render, require
from kubernetes_data_smoke import PortForward, secret


SOURCE_COMMIT = "9a51fcfb3568c7657a0e3cc325c7fa11509b6279"
CUSTOMER_IMAGE = "fintech-customer-service:" + SOURCE_COMMIT
# Synthetic 11-digit fixtures; never use a real dataset here.
CARDS = ("10000000001", "10000000002")
COLUMNS = ("cc_num", "first", "last", "gender", "street", "city", "state",
           "zip", "lat", "long", "city_pop", "job", "dob")


def synthetic_files():
    def csv_text(cards):
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(COLUMNS)
        for card in cards:
            writer.writerow((card, "Fixture", "Customer", "F", "Test street", "Test city",
                             "CA", "90001", "34.0", "-118.0", "100", "Testing, only", "1990-01-01"))
        return output.getvalue()
    return {"fraudTrain.csv": csv_text(CARDS[:1]), "fraudTest.csv": csv_text(CARDS)}


def customer_resources(items, namespace):
    selected = copy.deepcopy([item for item in items if item["metadata"]["name"] == "customer-service"
                              or item["metadata"]["name"].startswith("customer-service-config-")])
    require(len(selected) == 3, "Expected only Customer deployment, service and configuration")
    for item in selected:
        item["metadata"]["namespace"] = namespace
        if item["kind"] == "ConfigMap":
            item["data"].update(
                DB_URL=f"jdbc:postgresql://postgres.{namespace}.svc.cluster.local:5432/fintech",
                JWKS_URI=f"http://auth-service.{namespace}.svc.cluster.local:8081/.well-known/jwks.json",
                CUSTOMER_SEED_PATH="/data/sparkov/fraudTrain.csv,/data/sparkov/fraudTest.csv",
            )
        elif item["kind"] == "Deployment":
            item["spec"]["replicas"] = 1
            pod = item["spec"]["template"]["spec"]
            container = pod["containers"][0]
            container.update(image=CUSTOMER_IMAGE, imagePullPolicy="Never")
            container["volumeMounts"].append({"name": "seed", "mountPath": "/data/sparkov", "readOnly": True})
            pod["volumes"].append({"name": "seed", "configMap": {"name": "customer-seed-fixture", "defaultMode": 292}})
    return selected


def verify_api(port, token):
    path = "/internal/customers/lookup"
    require(request(port, path, {"cardNumber": CARDS[0]})[0] == 401, "Anonymous lookup must fail")
    code, found = request(port, path, {"cardNumber": CARDS[0]}, token=token)
    require(code == 200 and isinstance(found, dict) and found.get("cardLast4") == CARDS[0][-4:]
            and set(found) == {"customerId", "cardLast4"}, "Unexpected lookup result")
    customer_id = found["customerId"]
    code, profile = request(port, "/api/v1/customers/" + customer_id, token=token)
    require(code == 200 and profile.get("job") == "Testing, only" and profile.get("dob") == "1990-01-01"
            and not any(card in json.dumps(profile) for card in CARDS), "Unexpected public Customer response")
    require(request(port, path, {"cardNumber": "1"}, token=token)[0] == 400, "Invalid card must fail")
    require(request(port, path, {"cardNumber": "10000000003"}, token=token)[0] == 404, "Unknown card must fail")
    return customer_id


def run_customer(inventory, openssl, kubeseal):
    nodes = json.loads(kubectl(CONTEXT, "get", "nodes", "-o", "json", capture_output=True).stdout)
    require([item["metadata"]["name"] for item in nodes["items"]] == [NODE], "Expected only the lab node")
    require(image_revision(CUSTOMER_IMAGE) == SOURCE_COMMIT, "Expected reviewed local Customer image")
    subprocess.run(["kind", "load", "docker-image", "--name", "fintech-gitops-lab", CUSTOMER_IMAGE],
                   check=True, timeout=240)

    def check(namespace, username, initial, sql):
        password, key = secrets.token_hex(24), secrets.token_hex(32)
        sql(f"CREATE ROLE customer_user LOGIN PASSWORD '{password}'; "
            "CREATE SCHEMA customer AUTHORIZATION customer_user;")
        resources = customer_resources(render(CONTEXT, "deploy/overlays/team"), namespace)
        install(namespace, [
            seal_secret(namespace, "customer-hmac", {"key": key}, kubeseal),
            secret(namespace, "customer-service-db", {"username": "customer_user", "password": password}),
            {"apiVersion": "v1", "kind": "ConfigMap",
             "metadata": {"name": "customer-seed-fixture", "namespace": namespace}, "data": synthetic_files()},
            *resources,
        ])
        kubectl(CONTEXT, "-n", namespace, "wait", "--for=condition=Synced",
                "sealedsecret/customer-hmac", "--timeout=90s")
        kubectl(CONTEXT, "-n", namespace, "rollout", "status", "deployment/customer-service",
                "--timeout=240s", timeout=250)

        def verify_database():
            stored = sql("SELECT coalesce(json_agg(row_to_json(c)), '[]') FROM customer.customers c;")
            rows = json.loads(stored)
            require(len(rows) == 2 and not any(card in stored for card in CARDS),
                    "Seed duplicates or raw card in Customer table")
            expected = {hmac.new(key.encode(), card.encode(), hashlib.sha256).hexdigest() for card in CARDS}
            require({row["card_fingerprint"] for row in rows} == expected, "Unexpected HMAC fingerprints")
            return {row["id"] for row in rows}

        ids = verify_database()
        with PortForward(CONTEXT, namespace, "service/api-gateway", 8080) as url:
            token, _ = team_profile(urlsplit(url).port, username, initial)
        with PortForward(CONTEXT, namespace, "service/customer-service", 8082) as url:
            customer_id = verify_api(urlsplit(url).port, token)
        kubectl(CONTEXT, "-n", namespace, "rollout", "restart", "deployment/customer-service")
        kubectl(CONTEXT, "-n", namespace, "rollout", "status", "deployment/customer-service",
                "--timeout=240s", timeout=250)
        require(verify_database() == ids, "Restart changed seeded Customer identities")
        with PortForward(CONTEXT, namespace, "service/customer-service", 8082) as url:
            require(verify_api(urlsplit(url).port, token) == customer_id, "Lookup changed after restart")
        print("PASS: synthetic CSV deduplicated, HMAC-only storage and authenticated lookup survive restart.",
              flush=True)

    run(inventory, openssl, kubeseal, team=True, extra_check=check)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--openssl", default="openssl")
    parser.add_argument("--kubeseal", default="kubeseal")
    args = parser.parse_args()
    run_customer(json.loads(args.inventory.read_text(encoding="utf-8")), args.openssl, args.kubeseal)
