"""Render Kustomize and check the application tier without reading Secrets."""

import argparse
import copy
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
PORTS = {"api-gateway": 8080, "auth-service": 8081, "customer-service": 8082,
         "transaction-service": 8083, "risk-service": 8084,
         "notification-service": 8085, "audit-service": 8086, "frontend": 8080}
REPLICAS = dict(zip(PORTS, (2, 1, 1, 2, 2, 1, 1, 2)))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def kubectl(context, *args, **kwargs):
    return subprocess.run(["kubectl", "--context", context, *args], cwd=ROOT,
                          text=True, check=True, timeout=120, **kwargs)


def render(context):
    rendered = subprocess.run(["kubectl", "kustomize", "deploy/overlays/demo"], cwd=ROOT,
                              text=True, check=True, capture_output=True, timeout=30).stdout
    result = kubectl(context, "create", "--dry-run=client", "--validate=true", "-f", "-", "-o", "json",
                     input=rendered, capture_output=True)
    return decode_objects(result.stdout)


def decode_objects(output):
    # kubectl can emit consecutive JSON documents instead of a single List.
    decoder = json.JSONDecoder()
    items = []
    remaining = output.lstrip()
    while remaining:
        document, end = decoder.raw_decode(remaining)
        items.extend(document["items"] if document.get("kind") == "List" else [document])
        remaining = remaining[end:].lstrip()
    return items


def validate(items, allow_placeholder=False):
    keys = [(item["kind"], item["metadata"]["name"]) for item in items]
    require(len(keys) == len(set(keys)), "Duplicate resource identity")
    require(all(item["metadata"].get("namespace") == "fintech" for item in items), "Unexpected namespace")
    require(all(item["kind"] in {"Deployment", "Service", "ConfigMap", "Ingress"} for item in items),
            "Only application resources may be included (no Secrets or data stores)")
    index = {kind: {item["metadata"]["name"]: item for item in items if item["kind"] == kind}
             for kind in ("Deployment", "Service", "ConfigMap", "Ingress")}
    require(set(index["Deployment"]) == set(PORTS), "Expected eight Deployments")
    require(set(index["Service"]) == set(PORTS), "Expected eight ClusterIP Services")
    require(len(index["ConfigMap"]) == 8, "Expected eight generated ConfigMaps")
    require(set(index["Ingress"]) == {"fintech"}, "Expected one fintech Ingress")
    for name, port in PORTS.items():
        deployment = index["Deployment"][name]["spec"]
        pod = deployment["template"]["spec"]
        require(deployment["replicas"] == REPLICAS[name], f"{name}: minimum replicas changed")
        require(deployment["strategy"]["rollingUpdate"] == {"maxSurge": 1, "maxUnavailable": 0},
                f"{name}: unsafe rolling update")
        require(deployment["progressDeadlineSeconds"] > 150 + deployment["minReadySeconds"],
                f"{name}: progress deadline must allow startup")
        labels = deployment["template"]["metadata"]["labels"]
        require(deployment["selector"]["matchLabels"] == {"app": name} == labels, f"{name}: selector mismatch")
        require(pod["automountServiceAccountToken"] is False, f"{name}: service account token mounted")
        security = pod["securityContext"]
        require(security["runAsNonRoot"] and security["runAsUser"] == security["runAsGroup"] == 10001,
                f"{name}: expected non-root UID/GID")
        require(security["seccompProfile"]["type"] == "RuntimeDefault", f"{name}: missing seccomp")
        require(len(pod["containers"]) == 1 and not pod.get("initContainers"), f"{name}: unexpected containers")
        app = pod["containers"][0]
        require(app["ports"] == [{"name": "http", "containerPort": port}], f"{name}: incorrect port")
        image = app["image"]
        pinned = bool(re.search(r":(?:[a-f0-9]{40}|[a-f0-9]{64})$|@sha256:[a-f0-9]{64}$", image))
        require(pinned or (allow_placeholder and image == f"fintech-{name}:REPLACE_WITH_COMMIT_SHA"),
                f"{name}: image must use a full commit SHA or digest, not latest/dev")
        require(app["imagePullPolicy"] == "IfNotPresent", f"{name}: image pull policy changed")
        security = app["securityContext"]
        require(security["readOnlyRootFilesystem"] and security["allowPrivilegeEscalation"] is False
                and security["capabilities"]["drop"] == ["ALL"], f"{name}: unsafe container security")
        fe = name == "frontend"
        expected = {"requests": {"cpu": "50m" if fe else "200m", "memory": "64Mi" if fe else "384Mi"},
                    "limits": {"cpu": "200m" if fe else "1000m", "memory": "128Mi" if fe else "512Mi"}}
        require(app["resources"] == expected, f"{name}: resource budget changed")
        for probe in ("startupProbe", "livenessProbe", "readinessProbe"):
            path = "/healthz" if fe else "/actuator/health/" + ("readiness" if probe == "readinessProbe" else "liveness")
            require(app[probe]["httpGet"] == {"path": path, "port": "http"}, f"{name}: unsafe {probe}")
        require(pod["volumes"] == [{"name": "tmp", "emptyDir": {"medium": "Memory", "sizeLimit": "64Mi" if fe else "128Mi"}}],
                f"{name}: only bounded temporary storage is allowed")
        require(app["volumeMounts"] == [{"name": "tmp", "mountPath": "/tmp"}], f"{name}: incorrect tmp mount")
        service = index["Service"][name]["spec"]
        require(service["type"] == "ClusterIP" and service["selector"] == labels, f"{name}: unsafe Service")
        require(service["ports"] == [{"name": "http", "port": port, "targetPort": "http"}], f"{name}: Service port mismatch")
        config_name = app["envFrom"][0]["configMapRef"]["name"]
        require(config_name.startswith(name + "-config-") and config_name in index["ConfigMap"],
                f"{name}: ConfigMap hash/reference missing")
        config = index["ConfigMap"][config_name]["data"]
        require(not any(re.search("PASSWORD|TOKEN|PRIVATE_KEY|HMAC", key) for key in config), f"{name}: secret in ConfigMap")
        if not fe:
            readiness = "readinessState" if name == "api-gateway" else "readinessState,db"
            require(config["MANAGEMENT_ENDPOINT_HEALTH_GROUP_READINESS_INCLUDE"] == readiness,
                    f"{name}: readiness must not include RabbitMQ or downstream services")
            require(config["MANAGEMENT_ENDPOINT_HEALTH_GROUP_LIVENESS_INCLUDE"] == "livenessState",
                    f"{name}: liveness must not depend on infrastructure")
            require(config["JWKS_URI"] == "http://auth-service.fintech.svc.cluster.local:8081/.well-known/jwks.json",
                    f"{name}: incorrect JWKS namespace or URL")
            if name != "api-gateway":
                require(config["DB_URL"] == "jdbc:postgresql://postgres.data.svc.cluster.local:5432/fintech",
                        f"{name}: incorrect PostgreSQL namespace or URL")
                if name != "customer-service":
                    require(config["RABBITMQ_HOST"] == "rabbitmq.data.svc.cluster.local", f"{name}: incorrect broker DNS")
        else:
            require(config["GATEWAY_UPSTREAM"] == "http://api-gateway.fintech.svc.cluster.local:8080",
                    "Frontend must resolve the Gateway by its Kubernetes FQDN")
        expected_secrets = {}
        if name not in ("frontend", "api-gateway"):
            expected_secrets |= {"DB_USER": (name + "-db", "username"), "DB_PASSWORD": (name + "-db", "password")}
            if name != "customer-service":
                expected_secrets |= {"RABBITMQ_USER": ("rabbitmq-credentials", "username"),
                                     "RABBITMQ_PASSWORD": ("rabbitmq-credentials", "password")}
            if name == "audit-service":
                expected_secrets |= {"FLYWAY_USER": ("audit-migrator-db", "username"),
                                     "FLYWAY_PASSWORD": ("audit-migrator-db", "password")}
        actual_secrets = {}
        for env in app.get("env", []):
            require("value" not in env and "secretKeyRef" in env.get("valueFrom", {}), f"{name}: inline credential")
            ref = env["valueFrom"]["secretKeyRef"]
            require(not ref.get("optional"), f"{name}: credentials must fail closed")
            actual_secrets[env["name"]] = (ref["name"], ref["key"])
        require(actual_secrets == expected_secrets, f"{name}: incorrect credential ownership")
    ingress = index["Ingress"]["fintech"]["spec"]
    require(ingress["ingressClassName"] == "traefik" and ingress["tls"] == [
        {"hosts": ["fintech.local"], "secretName": "fintech-local-tls"}], "Ingress must use Traefik TLS")
    require(len(ingress["rules"]) == 1 and ingress["rules"][0]["host"] == "fintech.local", "Unexpected public host")
    paths = ingress["rules"][0]["http"]["paths"]
    require(len(paths) == 2 and {p["path"]: p["backend"]["service"]["name"] for p in paths}
            == {"/": "frontend", "/api": "api-gateway"}, "Only frontend and Gateway may be exposed")
    require(all(p["pathType"] == "Prefix" and p["backend"]["service"]["port"] == {"name": "http"} for p in paths),
            "Ingress must preserve API paths and use named ports")


def exercise_rejections(items):
    """Mutation-test the guard against the real Kustomize output, not a hand-built fixture."""
    mutations = {
        "root user": lambda docs: docs["pod"]["securityContext"].update(runAsUser=0),
        "writable filesystem": lambda docs: docs["app"]["securityContext"].update(readOnlyRootFilesystem=False),
        "latest image": lambda docs: docs["app"].update(image="fintech-transaction-service:latest"),
        "service exposure": lambda docs: docs["service"]["spec"].update(type="NodePort"),
        "broker readiness": lambda docs: docs["config"]["data"].update(
            MANAGEMENT_ENDPOINT_HEALTH_GROUP_READINESS_INCLUDE="readinessState,db,rabbit"),
        "secret in config": lambda docs: docs["config"]["data"].update(DB_PASSWORD="not-a-real-password"),
        "schema credential mixup": lambda docs: docs["app"]["env"][0]["valueFrom"]["secretKeyRef"].update(name="audit-migrator-db"),
        "bad service selector": lambda docs: docs["service"]["spec"].update(selector={"app": "audit-service"}),
    }
    for label, mutate in mutations.items():
        changed = copy.deepcopy(items)
        deployment = next(i for i in changed if i["kind"] == "Deployment" and i["metadata"]["name"] == "transaction-service")
        pod = deployment["spec"]["template"]["spec"]
        app = pod["containers"][0]
        config_name = app["envFrom"][0]["configMapRef"]["name"]
        config = next(i for i in changed if i["kind"] == "ConfigMap" and i["metadata"]["name"] == config_name)
        service = next(i for i in changed if i["kind"] == "Service" and i["metadata"]["name"] == "transaction-service")
        mutate({"pod": pod, "app": app, "config": config, "service": service})
        try:
            validate(changed, allow_placeholder=True)
        except ValueError:
            continue
        raise AssertionError("Policy accepted unsafe mutation: " + label)
    print(f"Rejected {len(mutations)} unsafe mutations of the rendered manifests.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--allow-placeholder", action="store_true", help="Validation only, not deployment readiness")
    args = parser.parse_args()
    items = render(args.context)
    validate(items, args.allow_placeholder)
    exercise_rejections(items)
    kubectl(args.context, "apply", "--server-side", "--dry-run=server", "-f", "-",
            input=json.dumps({"apiVersion": "v1", "kind": "List", "items": items}))
    print("Application policy and server-side schema checks passed; no resources changed.")


if __name__ == "__main__":
    main()
