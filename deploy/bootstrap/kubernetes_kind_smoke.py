"""Run the real frontend/Gateway in a disposable namespace on an existing kind cluster."""

import argparse
import copy
import json
import queue
import re
import subprocess
import threading
import time
import uuid

from check_kubernetes_manifests import ROOT, kubectl, render, require, validate
from frontend_smoke_test import request, verify_static


PREFIX = "fintech-smoke-"
OWNER_LABEL = "fintech.local/smoke-owner"


def smoke_resources(items, namespace, frontend_image, gateway_image):
    require(bool(re.fullmatch(PREFIX + r"[a-f0-9]{12}", namespace)), "Unsafe smoke namespace")
    selected = copy.deepcopy([item for item in items if item["kind"] in {"Deployment", "Service", "ConfigMap"}
                              and (item["metadata"]["name"] in {"frontend", "api-gateway"}
                                   or item["metadata"]["name"].startswith(("frontend-config-", "api-gateway-config-")))])
    require(len(selected) == 6, "Expected only two application workloads and their configs/services")
    for item in selected:
        item["metadata"]["namespace"] = namespace
        if item["kind"] == "Deployment":
            item["spec"]["replicas"] = 1
            item["spec"]["template"]["spec"]["containers"][0]["image"] = (
                frontend_image if item["metadata"]["name"] == "frontend" else gateway_image)
        if item["kind"] == "ConfigMap" and item["metadata"]["name"].startswith("frontend-config-"):
            item["data"]["GATEWAY_UPSTREAM"] = f"http://api-gateway.{namespace}.svc.cluster.local:8080"
    return selected


def can_cleanup(namespace, metadata, owner):
    return bool(re.fullmatch(PREFIX + r"[a-f0-9]{12}", namespace)
                and metadata.get("name") == namespace
                and metadata.get("labels", {}).get(OWNER_LABEL) == owner)


def forwarded_url(process):
    lines = queue.Queue()

    def read():
        for line in process.stdout:
            lines.put(line)

    threading.Thread(target=read, daemon=True).start()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=1)
        except queue.Empty:
            if process.poll() is not None:
                break
            continue
        match = re.search(r"Forwarding from 127\.0\.0\.1:([0-9]+)", line)
        if match:
            return "http://127.0.0.1:" + match[1]
    raise RuntimeError("kubectl port-forward did not become ready")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", required=True, help="kind cluster name; context is derived, never implicit")
    parser.add_argument("--frontend-image", required=True)
    parser.add_argument("--gateway-image", required=True)
    args = parser.parse_args()
    context = "kind-" + args.cluster
    items = render(context)
    validate(items, allow_placeholder=True)
    namespace = PREFIX + uuid.uuid4().hex[:12]
    owner = uuid.uuid4().hex
    selected = smoke_resources(items, namespace, args.frontend_image, args.gateway_image)
    for image in (args.frontend_image, args.gateway_image):
        subprocess.run(["kind", "load", "docker-image", "--name", args.cluster, image],
                       cwd=ROOT, check=True, timeout=240)
    created = False
    forward = None
    try:
        # create (not apply) refuses to adopt an existing namespace.
        kubectl(context, "create", "-f", "-", input=json.dumps({
            "apiVersion": "v1", "kind": "Namespace",
            "metadata": {"name": namespace, "labels": {OWNER_LABEL: owner}}}))
        created = True
        kubectl(context, "apply", "-f", "-", input=json.dumps({"apiVersion": "v1", "kind": "List", "items": selected}))
        for name in ("api-gateway", "frontend"):
            kubectl(context, "-n", namespace, "rollout", "status", "deployment/" + name, "--timeout=110s")
            result = kubectl(context, "-n", namespace, "exec", "deployment/" + name, "--", "id", "-u", capture_output=True)
            require(result.stdout.strip() == "10001", "Expected unprivileged runtime")
        forward = subprocess.Popen(["kubectl", "--context", context, "-n", namespace, "port-forward",
                                    "service/frontend", ":8080", "--address", "127.0.0.1"],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        url = forwarded_url(forward)
        verify_static(url)
        require(request(url, "/healthz")[0] == 200, "Frontend health failed")
        status, headers, _ = request(url, "/api/v1/transactions")
        require(status == 401 and "Bearer" in headers.get("WWW-Authenticate", ""),
                f"Expected real Gateway Bearer rejection through CoreDNS/nginx, got HTTP {status}")
        print("kind smoke passed: static assets, SPA, CoreDNS proxy, Gateway 401, UID 10001.")
    except Exception:
        if created:
            kubectl(context, "-n", namespace, "get", "pods", "-o", "wide")
            kubectl(context, "-n", namespace, "get", "events", "--sort-by=.metadata.creationTimestamp")
        raise
    finally:
        if forward is not None:
            forward.terminate()
            try:
                forward.wait(timeout=10)
            except subprocess.TimeoutExpired:
                forward.kill()
                forward.wait(timeout=10)
        if created:
            metadata = json.loads(kubectl(context, "get", "namespace", namespace, "-o", "json", capture_output=True).stdout)["metadata"]
            require(can_cleanup(namespace, metadata, owner), "Refusing to delete a namespace not owned by this run")
            kubectl(context, "delete", "namespace", namespace, "--wait=true", "--timeout=90s")


if __name__ == "__main__":
    main()
