"""Validate the separate data tier without applying it or reading credentials."""

import argparse
import copy
import json
import re

from check_kubernetes_manifests import kubectl, render, require


def validate_data(items, allow_placeholder=False):
    require(len(items) == 7, "Expected two StatefulSets, four Services and one ConfigMap")
    identities = [(item["kind"], item["metadata"]["name"]) for item in items]
    require(len(identities) == len(set(identities)), "Duplicate data resource identity")
    require(all(item["metadata"].get("namespace") == "data" for item in items), "Unexpected data namespace")
    require(all(item["kind"] in {"StatefulSet", "Service", "ConfigMap"} for item in items),
            "No plaintext Secrets, bootstrap Jobs or unrelated workloads allowed")
    sets = {i["metadata"]["name"]: i for i in items if i["kind"] == "StatefulSet"}
    require(set(sets) == {"postgres", "rabbitmq"}, "Expected postgres and rabbitmq StatefulSets")
    configs = {i["metadata"]["name"] for i in items if i["kind"] == "ConfigMap"}
    for name, uid, gid, size in (("postgres", 70, 70, "5Gi"), ("rabbitmq", 100, 101, "1Gi")):
        spec = sets[name]["spec"]
        require(spec["replicas"] == 1 and spec["serviceName"] == name + "-headless", "Single stable data identity required")
        require(spec["persistentVolumeClaimRetentionPolicy"] == {"whenDeleted": "Retain", "whenScaled": "Retain"},
                "PVCs must be retained on scale-down and StatefulSet deletion")
        claim = spec["volumeClaimTemplates"]
        require(len(claim) == 1 and claim[0]["metadata"]["name"] == "data", "Expected one data claim template")
        require(claim[0]["spec"] == {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": size}}},
                "Use the default StorageClass and the documented PVC budget")
        pod = spec["template"]["spec"]
        require(pod["nodeSelector"] == {"kubernetes.io/hostname": "fintech-worker"}, "Data must stay on the designated worker")
        require(pod["automountServiceAccountToken"] is False, "Data pods must not mount API tokens")
        security = pod["securityContext"]
        require(security["runAsNonRoot"] and security["runAsUser"] == uid and security["runAsGroup"] == gid
                and security["fsGroup"] == gid and security["fsGroupChangePolicy"] == "OnRootMismatch"
                and security["seccompProfile"]["type"] == "RuntimeDefault", "Incorrect data pod security")
        require(len(pod["containers"]) == 1 and not pod.get("initContainers"), "Unexpected data sidecars or privileged init")
        app = pod["containers"][0]
        if name == "postgres":
            pinned = re.fullmatch(r"fintech-postgres:(?:[0-9a-f]{40}|[0-9a-f]{64})|fintech-postgres@sha256:[0-9a-f]{64}", app["image"])
            require(pinned or (allow_placeholder and app["image"] == "fintech-postgres:REPLACE_WITH_COMMIT_SHA"),
                    "PostgreSQL image must use a reviewed commit SHA or digest")
        else:
            require(re.fullmatch(r"rabbitmq:4\.3\.6-management-alpine@sha256:[0-9a-f]{64}", app["image"]),
                    "RabbitMQ image must be digest pinned")
        security = app["securityContext"]
        require(security["readOnlyRootFilesystem"] and security["allowPrivilegeEscalation"] is False
                and security["capabilities"]["drop"] == ["ALL"], "Unsafe data container security")
        require(not any("hostPath" in v for v in pod.get("volumes", [])), "No shared hostPath data directories")
        for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
            if name == "postgres":
                require(app.get(probe, {}).get("exec", {}).get("command") == ["pg_isready", "-U", "postgres", "-d", "fintech"],
                        "PostgreSQL must probe its local server")
            else:
                require(app.get(probe, {}).get("tcpSocket") == {"port": "amqp"}, "RabbitMQ must probe its local AMQP listener")
        require(bool(app["resources"].get("requests")) and bool(app["resources"].get("limits")), "Data resources must be bounded")
        env = {e["name"]: e for e in app["env"]}
        if name == "postgres":
            require("POSTGRES_PASSWORD" not in env and env["POSTGRES_PASSWORD_FILE"]["value"] == "/run/secrets/postgres/password",
                    "PostgreSQL admin password must use its mounted Secret file")
            volume = next(v for v in pod["volumes"] if v["name"] == "postgres-admin")
            require(volume["secret"]["secretName"] == "postgres-admin", "Incorrect PostgreSQL admin Secret")
        else:
            for env_name, key in (("RABBITMQ_DEFAULT_USER", "username"), ("RABBITMQ_DEFAULT_PASS", "password")):
                require(env[env_name].get("valueFrom", {}).get("secretKeyRef") == {"name": "rabbitmq-credentials", "key": key},
                        "RabbitMQ must use Secret references, never inline credentials")
            require(next(v for v in pod["volumes"] if v["name"] == "config")["configMap"]["name"] in configs,
                    "RabbitMQ ConfigMap hash reference missing")
    services = [i for i in items if i["kind"] == "Service"]
    require({s["metadata"]["name"] for s in services} == {"postgres", "postgres-headless", "rabbitmq", "rabbitmq-headless"},
            "Missing internal data Services")
    for service in services:
        spec = service["spec"]
        require(spec.get("type", "ClusterIP") == "ClusterIP" and not spec.get("externalIPs"), "Do not expose data outside the cluster")
        name = service["metadata"]["name"].removesuffix("-headless")
        require(spec["selector"] == {"app": name}, "Incorrect data Service selector")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--allow-placeholder", action="store_true", help="Schema checks only, not shared deployment readiness")
    args = parser.parse_args()
    items = render(args.context, "deploy/k8s/data")
    validate_data(items, args.allow_placeholder)
    for label, mutate in (
        ("PVC deletion", lambda s: s["spec"]["persistentVolumeClaimRetentionPolicy"].update(whenScaled="Delete")),
        ("root", lambda s: s["spec"]["template"]["spec"]["securityContext"].update(runAsUser=0)),
        ("floating image", lambda s: s["spec"]["template"]["spec"]["containers"][0].update(image="postgres:latest")),
    ):
        changed = copy.deepcopy(items)
        mutate(next(i for i in changed if i["kind"] == "StatefulSet"))
        try:
            validate_data(changed, allow_placeholder=True)
        except ValueError:
            continue
        raise AssertionError("Data policy accepted unsafe mutation: " + label)
    kubectl(args.context, "apply", "--server-side", "--dry-run=server", "-f", "-",
            input=json.dumps({"apiVersion": "v1", "kind": "List", "items": items}))
    print("Data schema/policy validation passed; three unsafe mutations rejected; nothing changed.")


if __name__ == "__main__":
    main()
