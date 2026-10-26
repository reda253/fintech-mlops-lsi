"""Explicit first-install stages for a private, cluster-bound kind release. Never deletes data."""

import argparse
import base64
import hashlib
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from check_kubernetes_manifests import PORTS, kubectl, require
from kubernetes_data_smoke import PASSWORD_VARIABLES, PortForward, secret
from kubernetes_release import OWNER, check_target, digest, load, private_path, verify_images, write_json
from frontend_smoke_test import request, verify_static
from transaction_smoke_test import wait_for_checks


ROLES = {"auth": "auth_user", "customer": "customer_user", "transaction": "transaction_user", "risk": "risk_user",
         "notification": "notification_user", "audit": "audit_user", "audit_migrator": "audit_migrator", "mlflow": "mlflow_user"}


def bootstrap_statement(source, passwords, release_id):
    require(bool(re.fullmatch(r"[a-f0-9]{32}", release_id)), "Invalid release identity")
    require(set(passwords) == set(PASSWORD_VARIABLES)
            and all(re.fullmatch(r"[a-f0-9]{48}", p) for p in passwords.values()), "Invalid generated SQL credentials")
    variables = "".join(f"\\set {key} '{passwords[key]}'\n" for key in PASSWORD_VARIABLES)
    names = ",".join("'" + value + "'" for value in ROLES.values())
    schemas = ",".join("'" + name + "'" for name in (*ROLES.keys(), "fintech_bootstrap") if name != "audit_migrator")
    return variables + f"""BEGIN;
SELECT pg_advisory_xact_lock(721294631);
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ({names}))
     OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspname IN ({schemas}))
     OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname <> 'postgres' AND left(rolname,3) <> 'pg_')
     OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') AND left(nspname,3) <> 'pg_')
     OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relkind IN ('r','p','S','v','m','f')) THEN
    RAISE EXCEPTION 'Refusing bootstrap: target service roles or schemas already exist';
  END IF;
END $$;
""" + source + f"""
CREATE SCHEMA fintech_bootstrap AUTHORIZATION postgres;
CREATE TABLE fintech_bootstrap.installation (release_id text PRIMARY KEY, credentials_hash text NOT NULL);
INSERT INTO fintech_bootstrap.installation VALUES ('{release_id}', '{digest(passwords)}');
COMMIT;
"""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def broker_request(url, username, password, path, method="GET", data=None):
    require(bool(re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}", url)), "Broker credentials may only use loopback port-forward")
    authorization = base64.b64encode((username + ":" + password).encode()).decode()
    req = Request(url + path, method=method, data=json.dumps(data).encode() if data is not None else None,
                  headers={"Authorization": "Basic " + authorization, "Content-Type": "application/json"})
    # Never send broker credentials through an environment proxy or a redirect.
    with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=15) as response:
        body = response.read()
        return json.loads(body) if body else None


def matches_password(user, password):
    if user.get("hashing_algorithm") != "rabbit_password_hashing_sha256":
        return False
    raw = base64.b64decode(user["password_hash"], validate=True)
    return len(raw) == 36 and raw[4:] == hashlib.sha256(raw[:4] + password.encode()).digest()


class Installer:
    def __init__(self, bundle):
        self.bundle, self.release, self.passwords, self.apps, self.data = load(bundle)
        check_target(self.release)
        self.context = self.release["context"]
        self.data_ns = self.release["data_namespace"]
        self.apps_ns = self.release["apps_namespace"]
        self.owner = self.release["id"]
        self.admin = "fintech_admin_" + self.owner[:12]
        self.runtime = "fintech_runtime_" + self.owner[:12]

    def get(self, kind, name, namespace):
        # Only metadata is emitted; avoid reading TLS keys or last-applied Secret annotations.
        result = kubectl(self.context, "-n", namespace, "get", kind, name, "--ignore-not-found", "-o",
                         'jsonpath={.metadata.uid}{"|"}{.metadata.labels.fintech\\.local/release}', capture_output=True)
        value = result.stdout.strip()
        return value.split("|", 1) if value and value != "|" else None

    def check_owned(self, item):
        metadata = item["metadata"]
        existing = self.get(item["kind"], metadata["name"], metadata["namespace"])
        require(not existing or len(existing) == 2 and existing[1] == self.owner,
                f"Refusing to adopt existing {item['kind']}/{metadata['name']}")
        return existing

    def create_credentials(self, items):
        for item in items:
            item["metadata"]["labels"] = {OWNER: self.owner}
        existing = [self.check_owned(item) for item in items]
        for item, present in zip(items, existing):
            if not present:
                kubectl(self.context, "create", "-f", "-", input=json.dumps(item), capture_output=True)

    def apply_public(self, items):
        # Check the whole set before the first mutation, then use create for missing identities.
        existing = [self.check_owned(item) for item in items]
        for item, present in zip(items, existing):
            kubectl(self.context, "apply" if present else "create", "-f", "-", input=json.dumps(item), capture_output=True)

    def receipt(self, stage):
        path = self.bundle / "stages.json"
        stages = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        stages[stage] = True
        write_json(path, stages)

    def sql(self, statement):
        return kubectl(self.context, "-n", self.data_ns, "exec", "-i", "postgres-0", "--", "psql", "-X", "-U", "postgres",
                       "-d", "fintech", "-v", "ON_ERROR_STOP=1", "-At", input=statement, capture_output=True).stdout.strip()

    def wait_data(self):
        for name in ("postgres", "rabbitmq"):
            kubectl(self.context, "-n", self.data_ns, "rollout", "status", "statefulset/" + name,
                    "--timeout=300s", timeout=330)

    def install_data(self):
        verify_images(self.release)
        workloads = json.loads(kubectl(self.context, "-n", self.data_ns, "get", "deployments,jobs", "-o", "json",
                                       capture_output=True).stdout)["items"]
        require(not workloads, "Unexpected data workloads exist: refusing a first install")
        sets = {name: self.get("statefulset", name, self.data_ns) for name in ("postgres", "rabbitmq")}
        pod_owners = {value[0] for value in sets.values() if value and len(value) == 2 and value[1] == self.owner}
        pods = json.loads(kubectl(self.context, "-n", self.data_ns, "get", "pods", "-o", "json", capture_output=True).stdout)["items"]
        require(all(any(ref.get("controller") and ref.get("uid") in pod_owners
                        for ref in pod["metadata"].get("ownerReferences", [])) for pod in pods),
                "Unowned data pods exist: refusing to mix workloads")
        # Retained claims survive deletion of a StatefulSet; never silently attach someone else's claim.
        claims = json.loads(kubectl(self.context, "-n", self.data_ns, "get", "pvc", "-o", "json", capture_output=True).stdout)["items"]
        require(all(c["metadata"]["name"] in {"data-postgres-0", "data-rabbitmq-0"}
                    and c["metadata"].get("labels", {}).get(OWNER) == self.owner for c in claims),
                "Unowned or unexpected PVC exists: stop and review storage, never reset it")
        for item in self.data:
            self.check_owned(item)
        self.create_credentials([
            secret(self.data_ns, "postgres-admin", {"password": self.passwords["postgres_admin"]}),
            secret(self.data_ns, "rabbitmq-credentials", {"username": self.admin, "password": self.passwords["rabbitmq_admin"]}),
        ])
        self.apply_public(self.data)
        self.wait_data()
        self.receipt("data")
        print("Data tier ready. No service schema or application credentials initialized yet.", flush=True)

    def bootstrap_database(self):
        passwords = {key: self.passwords[key] for key in PASSWORD_VARIABLES}
        exists = self.sql("SELECT to_regclass('fintech_bootstrap.installation') IS NOT NULL;") == "t"
        if exists:
            marker = self.sql("SELECT release_id || ':' || credentials_hash FROM fintech_bootstrap.installation;")
            require(marker == self.owner + ":" + digest(passwords), "Database belongs to another bootstrap or credential set")
        else:
            source = (self.bundle / "source/deploy/sql/00_schemas_users.sql").read_text(encoding="utf-8")
            self.sql(bootstrap_statement(source, passwords, self.owner))
        # Verify ownership without reading password hashes from PostgreSQL.
        owners = json.loads(self.sql("SELECT json_object_agg(nspname,pg_get_userbyid(nspowner)) FROM pg_namespace "
                                     "WHERE nspname IN ('auth','customer','transaction','risk','notification','audit','mlflow');"))
        expected = {key: value for key, value in ROLES.items() if key not in {"audit", "audit_migrator"}} | {"audit": "audit_migrator"}
        require(owners == expected, "Service schema ownership changed: no automatic repair attempted")

    def bootstrap_broker(self):
        with PortForward(self.context, self.data_ns, "pod/rabbitmq-0", 15672) as url:
            def api(path, method="GET", data=None):
                return broker_request(url, self.admin, self.passwords["rabbitmq_admin"], path, method, data)
            deadline = time.monotonic() + 30
            while True:
                try:
                    api("/api/whoami")
                    break
                except HTTPError:
                    raise
                except (URLError, OSError):
                    require(time.monotonic() < deadline, "Broker management API did not become ready")
                    time.sleep(1)
            path = "/api/users/" + self.runtime
            try:
                user = api(path)
            except HTTPError as error:
                if error.code != 404:
                    raise
                api(path, "PUT", {"password": self.passwords["rabbitmq_runtime"], "tags": "", "hashing_algorithm": "rabbit_password_hashing_sha256"})
                user = api(path)
            require(user.get("tags") == [] and matches_password(user, self.passwords["rabbitmq_runtime"]),
                    "Existing RabbitMQ runtime user differs; refusing to overwrite credentials or tags")
            api("/api/permissions/%2F/" + self.runtime, "PUT", {"configure": ".*", "write": ".*", "read": ".*"})
            # Tagless runtime users must not be able to administer the broker.
            try:
                broker_request(url, self.runtime, self.passwords["rabbitmq_runtime"], "/api/users")
            except HTTPError as error:
                require(error.code in {401, 403}, "Unexpected runtime management response")
            else:
                raise ValueError("Runtime RabbitMQ account can access administration")

    def bootstrap(self):
        items = [secret(self.apps_ns, name + "-service-db", {"username": ROLES[name], "password": self.passwords[name + "_pwd"]})
                 for name in ("auth", "customer", "transaction", "risk", "notification", "audit")]
        items += [secret(self.apps_ns, "audit-migrator-db", {"username": "audit_migrator", "password": self.passwords["audit_migrator_pwd"]}),
                  secret(self.apps_ns, "rabbitmq-credentials", {"username": self.runtime, "password": self.passwords["rabbitmq_runtime"]})]
        for item in items:
            self.check_owned(item)
        self.wait_data()
        self.bootstrap_database()
        self.bootstrap_broker()
        self.create_credentials(items)
        self.receipt("bootstrap")
        print("Schema owners and tagless RabbitMQ runtime user ready; application secrets created without exporting values.", flush=True)

    def install_apps(self, skip_ingress=False):
        verify_images(self.release)
        marker = self.sql("SELECT release_id FROM fintech_bootstrap.installation;")
        require(marker == self.owner, "Bootstrap must complete before application deployment")
        path = self.bundle / "stages.json"
        require(path.exists() and json.loads(path.read_text(encoding="utf-8")).get("bootstrap"), "Complete the bootstrap stage first")
        if skip_ingress:
            require((self.data_ns, self.apps_ns) != ("data", "fintech"), "Ingress can only be skipped in private tests")
        else:
            require(self.get("secret", "fintech-local-tls", self.apps_ns), "Provision the reviewed TLS certificate first")
        items = [item for item in self.apps if not (skip_ingress and item["kind"] == "Ingress")]
        self.apply_public(items)
        for name in PORTS:
            kubectl(self.context, "-n", self.apps_ns, "rollout", "status", "deployment/" + name, "--timeout=300s", timeout=330)
        self.receipt("apps")
        print("Eight Deployments ready. This does not prove JWT login, business processing or ML inference.", flush=True)

    def verify(self):
        verify_images(self.release)
        passwords = {key: self.passwords[key] for key in PASSWORD_VARIABLES}
        marker = self.sql("SELECT release_id || ':' || credentials_hash FROM fintech_bootstrap.installation;")
        require(marker == self.owner + ":" + digest(passwords), "Database marker or SQL credentials differ")
        expected = {item["metadata"]["name"]: item for item in self.apps if item["kind"] == "Deployment"}
        for name, port in PORTS.items():
            current = json.loads(kubectl(self.context, "-n", self.apps_ns, "get", "deployment", name, "-o", "json", capture_output=True).stdout)
            require(current["metadata"].get("labels", {}).get(OWNER) == self.owner, "Unowned application Deployment")
            require(current["spec"]["template"]["spec"]["containers"][0]["image"] == f"fintech-{name}:{self.release['commit']}",
                    "Application image differs from the release")
            require(current["status"].get("availableReplicas", 0) >= expected[name]["spec"]["replicas"], "Missing ready replicas")
            with PortForward(self.context, self.apps_ns, "deployment/" + name, port) as url:
                if name == "frontend":
                    verify_static(url)
                    require(request(url, "/api/v1/transactions")[0] == 401, "Frontend did not proxy real Gateway rejection")
                elif name == "api-gateway":
                    require(request(url, "/actuator/health/readiness")[0] == 200, "Gateway readiness failed")
                    require(request(url, "/api/v1/transactions")[0] == 401, "Gateway accepted anonymous access")
                else:
                    wait_for_checks(url, timeout=30)
        for schema in ("auth", "customer", "transaction", "risk", "notification", "audit"):
            require("1" in self.sql(f"SELECT version FROM {schema}.flyway_schema_history WHERE success;").splitlines(),
                    f"Missing successful Flyway V1: {schema}")
        permissions = self.sql("SELECT has_table_privilege('audit_user','audit.audit_events','INSERT') "
                               "AND has_table_privilege('audit_user','audit.audit_events','SELECT') "
                               "AND NOT has_table_privilege('audit_user','audit.audit_events','UPDATE') "
                               "AND NOT has_table_privilege('audit_user','audit.audit_events','DELETE') "
                               "AND NOT has_table_privilege('audit_user','audit.audit_events','TRUNCATE') "
                               "AND NOT has_schema_privilege('transaction_user','auth','USAGE');")
        require(permissions == "t", "Audit append-only or schema isolation contract violated")
        print("Read-only verification passed: eight apps, six migrations, probes, anonymous rejection and SQL privilege checks.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("data", "bootstrap", "apps", "verify"))
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--confirm-first-install", action="store_true")
    args = parser.parse_args()
    require(args.stage == "verify" or args.confirm_first_install,
            "Explicit --confirm-first-install is required; this command changes cluster resources")
    bundle = private_path(args.bundle)
    lock = bundle / ".operation.lock"
    with open(lock, "x", encoding="utf-8") as output:
        output.write("Do not remove while a release operation is running.\n")
    try:
        installer = Installer(bundle)
        {"data": installer.install_data, "bootstrap": installer.bootstrap, "apps": installer.install_apps, "verify": installer.verify}[args.stage]()
    finally:
        lock.unlink()


if __name__ == "__main__":
    main()
