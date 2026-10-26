"""Validate the release installer against all eight apps in disposable namespaces, never shared data."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import uuid

from check_kubernetes_manifests import kubectl, require
from kubernetes_kind_smoke import OWNER_LABEL, PREFIX, can_cleanup
from kubernetes_release import build, digest, load, prepare, write_json
from kubernetes_shared_deploy import Installer, bootstrap_statement


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--skip-image-load", action="store_true", help="Repeated local tests only, with exact images already loaded")
    args = parser.parse_args()
    context = "kind-" + args.cluster
    owner = uuid.uuid4().hex
    namespaces = [PREFIX + uuid.uuid4().hex[:12] for _ in range(2)]
    created = []
    try:
        for namespace in namespaces:
            kubectl(context, "create", "-f", "-", input=json.dumps({"apiVersion": "v1", "kind": "Namespace",
                    "metadata": {"name": namespace, "labels": {OWNER_LABEL: owner}}}))
            created.append(namespace)
        with tempfile.TemporaryDirectory(prefix="fintech-shared-test-") as temporary:
            bundle = prepare(Path(temporary) / "release", context, args.commit, *namespaces)
            build(bundle)
            _, release, _, apps, data = load(bundle)
            nodes = json.loads(kubectl(context, "get", "nodes", "-o", "json", capture_output=True).stdout)["items"]
            candidates = [n for n in nodes if any(c["type"] == "Ready" and c["status"] == "True" for c in n["status"]["conditions"])]
            require(candidates, "No ready test nodes")
            workers = [n for n in candidates if "node-role.kubernetes.io/control-plane" not in n["metadata"]["labels"]]
            node = (workers or candidates)[0]["metadata"]["name"]
            for item in data:
                if item["kind"] == "StatefulSet":
                    item["spec"]["template"]["spec"]["nodeSelector"] = {"kubernetes.io/hostname": node}
            # Only this disposable fixture reduces replicas to fit small CI runners.
            for item in apps:
                if item["kind"] == "Deployment":
                    item["spec"]["replicas"] = 1
            release.update(data_hash=digest(data), apps_hash=digest(apps))
            write_json(bundle / "data.json", data)
            write_json(bundle / "apps.json", apps)
            write_json(bundle / "release.json", release)
            if not args.skip_image_load:
                subprocess.run(["kind", "load", "docker-image", "--name", args.cluster,
                                *(f"fintech-{m}:{release['commit']}" for m in release["images"])], check=True, timeout=900)
            installer = Installer(bundle)
            installer.install_data()
            # This table belongs only to the empty disposable test database.
            installer.sql("CREATE TABLE public.release_guard_probe (id integer);")
            try:
                installer.bootstrap_database()
            except subprocess.CalledProcessError:
                pass
            else:
                raise AssertionError("Pre-existing public data was not refused")
            require(installer.sql("SELECT count(*) FROM pg_roles WHERE rolname='transaction_user';") == "0",
                    "Failed first-install guard must not leave partially created service roles")
            installer.sql("DROP TABLE public.release_guard_probe;")
            installer.bootstrap()
            installer.bootstrap()  # Restarting the same bootstrap must not reset stored accounts.
            wrong_passwords = dict(installer.passwords)
            installer.passwords["auth_pwd"] = "0" * 48
            try:
                installer.bootstrap_database()
            except ValueError:
                pass
            else:
                raise AssertionError("Changed SQL credentials were accepted")
            installer.passwords = wrong_passwords
            schema_passwords = {name: installer.passwords[name] for name in (
                "auth_pwd", "customer_pwd", "transaction_pwd", "risk_pwd", "notification_pwd", "audit_pwd", "audit_migrator_pwd", "mlflow_pwd")}
            try:
                installer.sql(bootstrap_statement((bundle / "source/deploy/sql/00_schemas_users.sql").read_text(encoding="utf-8"),
                                                  schema_passwords, uuid.uuid4().hex))
            except subprocess.CalledProcessError:
                pass
            else:
                raise AssertionError("Existing schemas were reinitialized")
            installer.install_apps(skip_ingress=True)
            installer.verify()
            print("Shared installer smoke passed: eight apps, six migrations, separate broker runtime user, repeat-safe SQL bootstrap and schema-reuse refusal.", flush=True)
    except Exception:
        for namespace in created:
            kubectl(context, "-n", namespace, "get", "pods,pvc", "-o", "wide")
            kubectl(context, "-n", namespace, "get", "events", "--sort-by=.metadata.creationTimestamp")
        raise
    finally:
        for namespace in reversed(created):
            metadata = json.loads(kubectl(context, "get", "namespace", namespace, "-o", "json", capture_output=True).stdout)["metadata"]
            require(can_cleanup(namespace, metadata, owner), "Refusing cleanup of an unowned namespace")
            kubectl(context, "delete", "namespace", namespace, "--wait=true", "--timeout=110s")


if __name__ == "__main__":
    main()
