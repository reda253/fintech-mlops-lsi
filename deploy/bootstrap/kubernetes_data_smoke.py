"""Exercise PostgreSQL/RabbitMQ persistence and Transaction in two private kind namespaces."""

import argparse
import base64
import copy
import json
import os
import re
import secrets
import subprocess
import time
import uuid
from urllib.request import Request, urlopen

from check_kubernetes_data import validate_data
from check_kubernetes_manifests import ROOT, kubectl, render, require, validate
from kubernetes_kind_smoke import can_cleanup, forwarded_url, OWNER_LABEL, PREFIX
from transaction_smoke_test import assert_stays_ready, wait_for_checks


PASSWORD_VARIABLES = ("auth_pwd", "customer_pwd", "transaction_pwd", "risk_pwd", "notification_pwd",
                      "audit_pwd", "audit_migrator_pwd", "mlflow_pwd")


def bootstrap_sql(passwords):
    require(set(passwords) == set(PASSWORD_VARIABLES), "Expected exactly the schema bootstrap password variables")
    require(all(re.fullmatch(r"[a-f0-9]{48}", value) for value in passwords.values()), "Only generated hex credentials accepted")
    variables = "".join(f"\\set {name} '{passwords[name]}'\n" for name in PASSWORD_VARIABLES)
    return variables + (ROOT / "deploy/sql/00_schemas_users.sql").read_text(encoding="utf-8")


def secret(namespace, name, values):
    return {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": namespace},
            "type": "Opaque", "stringData": values}


def transaction_resources(items, apps_namespace, data_namespace, image):
    require(bool(re.fullmatch(PREFIX + r"[a-f0-9]{12}", apps_namespace)), "Unsafe application namespace")
    require(bool(re.fullmatch(PREFIX + r"[a-f0-9]{12}", data_namespace)) and data_namespace != apps_namespace,
            "Data test must use a separate private namespace")
    selected = copy.deepcopy([i for i in items if i["kind"] in {"Deployment", "Service", "ConfigMap"}
                              and (i["metadata"]["name"] == "transaction-service"
                                   or i["metadata"]["name"].startswith("transaction-service-config-"))])
    require(len(selected) == 3, "Expected only Transaction deployment, service and config")
    for item in selected:
        item["metadata"]["namespace"] = apps_namespace
        if item["kind"] == "Deployment":
            item["spec"]["replicas"] = 1
            item["spec"]["template"]["spec"]["containers"][0]["image"] = image
        if item["kind"] == "ConfigMap":
            item["data"].update(
                DB_URL=f"jdbc:postgresql://postgres.{data_namespace}.svc.cluster.local:5432/fintech",
                RABBITMQ_HOST=f"rabbitmq.{data_namespace}.svc.cluster.local",
                SPRING_DATASOURCE_HIKARI_CONNECTION_TIMEOUT="2000",
                SPRING_RABBITMQ_CONNECTION_TIMEOUT="2s",
            )
    return selected


class PortForward:
    def __init__(self, context, namespace, target, port):
        self.command = ["kubectl", "--context", context, "-n", namespace, "port-forward", target,
                        f":{port}", "--address", "127.0.0.1"]

    def __enter__(self):
        self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            return forwarded_url(self.process)
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        self.process.stdout.close()


def rabbit_request(url, password, path, method, data=None):
    authorization = base64.b64encode(("transaction_ci:" + password).encode()).decode()
    req = Request(url + path, method=method,
                  data=json.dumps(data).encode() if data is not None else None,
                  headers={"Authorization": "Basic " + authorization, "Content-Type": "application/json"})
    with urlopen(req, timeout=10) as response:
        body = response.read()
        return json.loads(body) if body else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--transaction-image", required=True)
    parser.add_argument("--postgres-image", required=True, help="Derived non-root image built from deploy/images/postgres")
    parser.add_argument("--skip-image-load", action="store_true", help="Only when both exact images are already loaded on every kind node")
    args = parser.parse_args()
    context = "kind-" + args.cluster
    applications = render(context)
    validate(applications, allow_placeholder=True)
    data_items = render(context, "deploy/k8s/data")
    validate_data(data_items, allow_placeholder=True)
    nodes = json.loads(kubectl(context, "get", "nodes", "-o", "json", capture_output=True).stdout)["items"]
    ready = [n for n in nodes if any(c["type"] == "Ready" and c["status"] == "True" for c in n["status"]["conditions"])]
    workers = [n for n in ready if "node-role.kubernetes.io/control-plane" not in n["metadata"]["labels"]]
    require(bool(ready), "No ready kind nodes")
    node = (workers or ready)[0]["metadata"]["name"]
    data_namespace, apps_namespace = [PREFIX + uuid.uuid4().hex[:12] for _ in range(2)]
    owner = uuid.uuid4().hex
    credentials = {name: secrets.token_hex(24) for name in (*PASSWORD_VARIABLES, "postgres_admin", "rabbitmq")}
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for password in credentials.values():
            print("::add-mask::" + password, flush=True)
    selected = transaction_resources(applications, apps_namespace, data_namespace, args.transaction_image)
    data_items = copy.deepcopy(data_items)
    for item in data_items:
        item["metadata"]["namespace"] = data_namespace
        if item["kind"] == "StatefulSet":
            pod = item["spec"]["template"]["spec"]
            pod["nodeSelector"]["kubernetes.io/hostname"] = node
            if item["metadata"]["name"] == "postgres":
                pod["containers"][0]["image"] = args.postgres_image
    # Official multi-platform images are pulled by kubelet using their reviewed
    # digests. Docker Desktop archives may omit other platforms still in an index.
    if not args.skip_image_load:
        for image in (args.transaction_image, args.postgres_image):
            subprocess.run(["kind", "load", "docker-image", "--name", args.cluster, image],
                           cwd=ROOT, check=True, timeout=240)
    created = []

    def apply(items):
        kubectl(context, "apply", "-f", "-", capture_output=True,
                input=json.dumps({"apiVersion": "v1", "kind": "List", "items": items}))

    def sql(statement):
        # Credentials are sent through stdin, never argv, config dumps or log output.
        return kubectl(context, "-n", data_namespace, "exec", "-i", "postgres-0", "--", "psql", "-X",
                       "-U", "postgres", "-d", "fintech", "-v", "ON_ERROR_STOP=1", "-At",
                       input=statement, capture_output=True).stdout.strip()

    def ready_pod(name):
        deadline = time.monotonic() + 30
        while True:
            try:
                kubectl(context, "-n", data_namespace, "get", "pod", name + "-0", capture_output=True)
                break
            except subprocess.CalledProcessError:
                require(time.monotonic() < deadline, "StatefulSet did not create its pod")
                time.sleep(1)
        kubectl(context, "-n", data_namespace, "wait", "--for=condition=Ready", "pod/" + name + "-0",
                "--timeout=300s", timeout=330)

    def scale(name, replicas):
        kubectl(context, "-n", data_namespace, "scale", "statefulset/" + name, "--replicas=" + str(replicas))
        if replicas == 0:
            kubectl(context, "-n", data_namespace, "wait", "--for=delete", "pod/" + name + "-0", "--timeout=110s")
        else:
            ready_pod(name)

    def claim_ids():
        claims = json.loads(kubectl(context, "-n", data_namespace, "get", "pvc", "-o", "json", capture_output=True).stdout)["items"]
        require({c["metadata"]["name"] for c in claims} == {"data-postgres-0", "data-rabbitmq-0"}, "Unexpected smoke PVC set")
        return {c["metadata"]["name"]: c["metadata"]["uid"] for c in claims}

    try:
        for namespace in (data_namespace, apps_namespace):
            kubectl(context, "create", "-f", "-", input=json.dumps({"apiVersion": "v1", "kind": "Namespace",
                    "metadata": {"name": namespace, "labels": {OWNER_LABEL: owner}}}))
            created.append(namespace)
        apply([secret(data_namespace, "postgres-admin", {"password": credentials["postgres_admin"]}),
               secret(data_namespace, "rabbitmq-credentials", {"username": "transaction_ci", "password": credentials["rabbitmq"]}),
               secret(apps_namespace, "transaction-service-db", {"username": "transaction_user", "password": credentials["transaction_pwd"]}),
               secret(apps_namespace, "rabbitmq-credentials", {"username": "transaction_ci", "password": credentials["rabbitmq"]})])
        apply(data_items)
        for name in ("postgres", "rabbitmq"):
            ready_pod(name)
        initial_claims = claim_ids()
        require(sql("SELECT count(*) FROM pg_roles WHERE rolname='transaction_user';") == "0", "Refusing bootstrap on an initialized database")
        sql(bootstrap_sql({key: credentials[key] for key in PASSWORD_VARIABLES}))
        sql("SET ROLE audit_migrator; CREATE TABLE audit.ci_permissions (id integer PRIMARY KEY); RESET ROLE;\n"
            "CREATE TABLE public.ci_persistence (marker text PRIMARY KEY); INSERT INTO public.ci_persistence VALUES ('retained');")
        privileges = sql("SELECT has_table_privilege('audit_user','audit.ci_permissions','INSERT') "
                         "AND has_table_privilege('audit_user','audit.ci_permissions','SELECT') "
                         "AND NOT has_table_privilege('audit_user','audit.ci_permissions','UPDATE') "
                         "AND NOT has_table_privilege('audit_user','audit.ci_permissions','DELETE') "
                         "AND NOT has_schema_privilege('transaction_user','auth','USAGE');")
        require(privileges == "t", "Audit append-only or schema isolation grants violated")
        apply(selected)
        kubectl(context, "-n", apps_namespace, "rollout", "status", "deployment/transaction-service", "--timeout=110s")
        versions = sql("SELECT version FROM transaction.flyway_schema_history WHERE success ORDER BY installed_rank;").splitlines()
        require("1" in versions, "Flyway V1 not applied")
        uid = kubectl(context, "-n", apps_namespace, "exec", "deployment/transaction-service", "--", "id", "-u", capture_output=True).stdout.strip()
        require(uid == "10001", "Transaction must run as UID 10001")
        with PortForward(context, data_namespace, "pod/rabbitmq-0", 15672) as url:
            rabbit_request(url, credentials["rabbitmq"], "/api/queues/%2F/ci.persistence", "PUT", {"durable": True})
            published = rabbit_request(url, credentials["rabbitmq"], "/api/exchanges/%2F/amq.default/publish", "POST",
                                       {"properties": {"delivery_mode": 2}, "routing_key": "ci.persistence", "payload": owner, "payload_encoding": "string"})
            require(published.get("routed") is True, "Persistent RabbitMQ message was not routed")
        with PortForward(context, apps_namespace, "deployment/transaction-service", 8083) as url:
            wait_for_checks(url)
            print("Testing RabbitMQ outage: readiness must remain UP", flush=True)
            scale("rabbitmq", 0)
            assert_stays_ready(url, duration=20)
            scale("rabbitmq", 1)
            wait_for_checks(url)
            print("Testing PostgreSQL outage: liveness UP, readiness DOWN, then recovery", flush=True)
            scale("postgres", 0)
            wait_for_checks(url, "DOWN", timeout=90)
            scale("postgres", 1)
            wait_for_checks(url, "UP", timeout=110)
        require(claim_ids() == initial_claims, "Data pods must reuse the same PVC identities")
        require(sql("SELECT marker FROM public.ci_persistence;") == "retained", "PostgreSQL row did not survive pod recreation")
        with PortForward(context, data_namespace, "pod/rabbitmq-0", 15672) as url:
            messages = rabbit_request(url, credentials["rabbitmq"], "/api/queues/%2F/ci.persistence/get", "POST",
                                      {"count": 1, "ackmode": "ack_requeue_false", "encoding": "auto"})
            require(len(messages) == 1 and messages[0]["payload"] == owner, "Durable message did not survive RabbitMQ pod recreation")
        print("Data integration passed: schema grants, Flyway, UID, auth, outages, same PVCs, retained SQL row and durable message.")
    except Exception:
        for namespace in created:
            kubectl(context, "-n", namespace, "get", "pods,pvc", "-o", "wide")
            kubectl(context, "-n", namespace, "get", "events", "--sort-by=.metadata.creationTimestamp")
        raise
    finally:
        # Namespace deletion intentionally removes only this run's disposable PVCs.
        for namespace in reversed(created):
            metadata = json.loads(kubectl(context, "get", "namespace", namespace, "-o", "json", capture_output=True).stdout)["metadata"]
            require(can_cleanup(namespace, metadata, owner), "Refusing cleanup of an unowned namespace")
            kubectl(context, "delete", "namespace", namespace, "--wait=true", "--timeout=110s")


if __name__ == "__main__":
    main()
