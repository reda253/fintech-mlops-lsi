"""Review the pinned team release against kind-fintech without applying it."""

import argparse
import json
from pathlib import Path
import re

from check_kubernetes_manifests import PORTS, kubectl, render, require, validate


CONTEXT = "kind-fintech"
SOURCE_COMMIT = "64b1d7d2161b1d6a271b5a5c0b798df95f74c2cb"
REPOSITORY = "reda253/fintech-mlops-lsi"
OVERLAY = "deploy/overlays/team-release"
RESOURCE_KINDS = "deployment,service,ingress,configmap"


def image_pins(items, inventory):
    require(inventory.get("schema") == 1 and inventory.get("platform") == "linux/amd64"
            and inventory.get("repository") == REPOSITORY and inventory.get("commit") == SOURCE_COMMIT,
            "Expected the reviewed 64b1d7d GHCR inventory")
    deployments = {item["metadata"]["name"]: item for item in items if item["kind"] == "Deployment"}
    require(set(deployments) == set(PORTS), "Unexpected application deployment set")
    for name, item in deployments.items():
        expected = inventory.get("images", {}).get(name, "")
        prefix = f"ghcr.io/{REPOSITORY}/{name}@sha256:"
        require(isinstance(expected, str) and re.fullmatch(re.escape(prefix) + r"[a-f0-9]{64}", expected),
                f"{name}: missing or invalid registry digest")
        require(image(item) == expected, f"{name}: rendered image differs from reviewed digest")


def image(item):
    return item["spec"]["template"]["spec"]["containers"][0]["image"]


def identity(item):
    return item["kind"], item["metadata"]["name"]


def live_summary(desired, live):
    lookup = {identity(item): item for item in live}
    result = []
    for item in desired:
        key = identity(item)
        kind, name = key
        actual = lookup.get(key)
        if actual is None:
            require(kind == "ConfigMap", f"{kind}/{name}: expected existing resource is missing")
            result.append(f"{kind}/{name}: create")
            continue
        metadata = actual["metadata"]
        require(not metadata.get("annotations", {}).get("argocd.argoproj.io/tracking-id"),
                f"{kind}/{name}: already tracked; inspect ownership before adoption")
        require(not metadata.get("ownerReferences"), f"{kind}/{name}: already has an owner reference")
        if kind in {"Deployment", "Service"}:
            require(item["spec"]["selector"] == actual["spec"]["selector"], f"{kind}/{name}: selector differs")
        if kind == "Deployment":
            require(item["spec"]["replicas"] == actual["spec"]["replicas"], f"{kind}/{name}: replica count differs")
            action = "replace image" if image(item) != image(actual) else "image already matches"
        else:
            action = "review existing resource"
        result.append(f"{kind}/{name}: {action}")
    unmanaged = sorted(set(lookup) - {identity(item) for item in desired})
    result.extend(f"{kind}/{name}: outside candidate" for kind, name in unmanaged)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    candidate = render(CONTEXT, OVERLAY)
    validate(candidate, team_auth=True)
    image_pins(candidate, inventory)
    result = kubectl(CONTEXT, "-n", "fintech", "get", RESOURCE_KINDS, "-o", "json", capture_output=True)
    print("\n".join(live_summary(candidate, json.loads(result.stdout)["items"])))
    print("Read-only structural check passed. Review the full diff and prerequisites before any sync.")


if __name__ == "__main__":
    main()
