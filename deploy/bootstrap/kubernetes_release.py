"""Prepare a private, cluster-bound local kind release from a committed Git snapshot."""

import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tarfile
import tempfile
import time
import uuid

from check_kubernetes_data import validate_data
from check_kubernetes_manifests import ROOT, PORTS, kubectl, render, require, validate
from kubernetes_data_smoke import PASSWORD_VARIABLES


OWNER = "fintech.local/release"
REVISION = "org.opencontainers.image.revision"
MODULES = (*PORTS, "postgres")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def private_path(path):
    path = Path(path).expanduser().absolute()
    for candidate in (path, path.resolve()):
        require(candidate != ROOT and ROOT not in candidate.parents, "Release credentials must stay outside the repository")
        require(not any((parent / ".git").exists() for parent in (candidate, *candidate.parents)),
                "Do not create a private release inside any Git checkout")
    require(not path.is_symlink(), "Release directory cannot be a symlink")
    return path.resolve()


def protect_directory(path):
    if os.name == "nt":
        identity = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True)
        sid = next(csv.reader(identity.splitlines()))[1]
        require(bool(re.fullmatch(r"S-1-[0-9-]+", sid)), "Cannot determine Windows user SID")
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F",
                        "*S-1-5-18:(OI)(CI)F"], check=True, capture_output=True)
    else:
        path.chmod(0o700)


def write_json(path, value):
    temporary = path.with_suffix(".new")
    with open(temporary, "x", encoding="utf-8", opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
        json.dump(value, output, indent=2)
        output.write("\n")
    os.replace(temporary, path)


def namespace_uid(context, namespace):
    return kubectl(context, "get", "namespace", namespace, "-o", "jsonpath={.metadata.uid}", capture_output=True).stdout.strip()


def check_namespaces(data, apps):
    if (data, apps) == ("data", "fintech"):
        return
    require(data != apps and all(re.fullmatch(r"fintech-smoke-[a-f0-9]{12}", name) for name in (data, apps)),
            "Use the shared data/fintech pair or two private smoke namespaces")


def pin_manifests(apps, data, commit, owner, data_namespace="data", apps_namespace="fintech"):
    require(bool(re.fullmatch(r"[a-f0-9]{40}", commit)), "Expected full Git commit SHA")
    require(bool(re.fullmatch(r"[a-f0-9]{32}", owner)), "Invalid release identity")
    check_namespaces(data_namespace, apps_namespace)
    apps, data = copy.deepcopy(apps), copy.deepcopy(data)
    validate(apps, allow_placeholder=True)
    validate_data(data, allow_placeholder=True)
    for item in apps + data:
        if item["kind"] in {"Deployment", "StatefulSet"}:
            name = item["metadata"]["name"]
            if name != "rabbitmq":
                item["spec"]["template"]["spec"]["containers"][0]["image"] = f"fintech-{name}:{commit}"
    validate(apps)
    validate_data(data)
    for items, namespace in ((apps, apps_namespace), (data, data_namespace)):
        for item in items:
            item["metadata"]["namespace"] = namespace
            item["metadata"].setdefault("labels", {})[OWNER] = owner
            if item["kind"] == "ConfigMap":
                item["data"] = {key: value.replace(".fintech.svc.cluster.local", f".{apps_namespace}.svc.cluster.local")
                                .replace(".data.svc.cluster.local", f".{data_namespace}.svc.cluster.local")
                                for key, value in item["data"].items()}
            if item["kind"] == "StatefulSet":
                item["spec"]["volumeClaimTemplates"][0]["metadata"]["labels"] = {OWNER: owner}
    return apps, data


def prepare(bundle, context, commit, data_namespace="data", apps_namespace="fintech"):
    require(bool(re.fullmatch(r"kind-[a-z0-9-]+", context)), "An explicit local kind context is required")
    check_namespaces(data_namespace, apps_namespace)
    bundle = private_path(bundle)
    require(not bundle.exists(), "Bundle already exists: never regenerate credentials for an existing release")
    commit = subprocess.check_output(["git", "rev-parse", "--verify", "--end-of-options", commit + "^{commit}"], cwd=ROOT, text=True).strip()
    require(bool(re.fullmatch(r"[a-f0-9]{40}", commit)), "Expected committed SHA-1 Git object")
    identity = {"context": context, "cluster_uid": namespace_uid(context, "kube-system"),
                "data_namespace": data_namespace, "apps_namespace": apps_namespace,
                "data_uid": namespace_uid(context, data_namespace), "apps_uid": namespace_uid(context, apps_namespace)}
    bundle.mkdir(parents=True, mode=0o700)
    protect_directory(bundle)
    source = bundle / "source"
    source.mkdir()
    with tempfile.TemporaryFile() as archive:
        subprocess.run(["git", "archive", "--format=tar", commit], cwd=ROOT, stdout=archive, check=True)
        archive.seek(0)
        with tarfile.open(fileobj=archive) as files:
            files.extractall(source, filter="data")
    owner = uuid.uuid4().hex
    apps, data = pin_manifests(render(context, str(source / "deploy/overlays/demo")),
                               render(context, str(source / "deploy/k8s/data")), commit, owner,
                               data_namespace, apps_namespace)
    passwords = {key: secrets.token_hex(24) for key in (*PASSWORD_VARIABLES, "postgres_admin", "rabbitmq_admin", "rabbitmq_runtime")}
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for password in passwords.values():
            print("::add-mask::" + password, flush=True)
    write_json(bundle / "credentials.json", passwords)
    write_json(bundle / "apps.json", apps)
    write_json(bundle / "data.json", data)
    sql = (source / "deploy/sql/00_schemas_users.sql").read_text(encoding="utf-8")
    release = identity | {"version": 1, "id": owner, "commit": commit, "apps_hash": digest(apps), "data_hash": digest(data),
                          "credentials_hash": digest(passwords), "sql_hash": hashlib.sha256(sql.encode()).hexdigest(), "images": {}}
    write_json(bundle / "release.json", release)
    print(f"Private release prepared for {context}; commit {commit}. No cluster resources changed.", flush=True)
    return bundle


def load(bundle):
    bundle = private_path(bundle)
    release = json.loads((bundle / "release.json").read_text(encoding="utf-8"))
    passwords = json.loads((bundle / "credentials.json").read_text(encoding="utf-8"))
    apps = json.loads((bundle / "apps.json").read_text(encoding="utf-8"))
    data = json.loads((bundle / "data.json").read_text(encoding="utf-8"))
    require(release["version"] == 1 and re.fullmatch(r"[a-f0-9]{40}", release["commit"]), "Invalid release version or commit")
    require(digest(apps) == release["apps_hash"] and digest(data) == release["data_hash"]
            and digest(passwords) == release["credentials_hash"], "Bundle changed: do not edit release files or rotate credentials in place")
    require(set(passwords) == set((*PASSWORD_VARIABLES, "postgres_admin", "rabbitmq_admin", "rabbitmq_runtime"))
            and all(re.fullmatch(r"[a-f0-9]{48}", p) for p in passwords.values()), "Invalid private credentials")
    sql = (bundle / "source/deploy/sql/00_schemas_users.sql").read_text(encoding="utf-8")
    require(hashlib.sha256(sql.encode()).hexdigest() == release["sql_hash"], "Bootstrap SQL snapshot changed")
    return bundle, release, passwords, apps, data


def check_target(release):
    context = release["context"]
    require(namespace_uid(context, "kube-system") == release["cluster_uid"], "Cluster was recreated or context points elsewhere")
    for name, key in ((release["data_namespace"], "data_uid"), (release["apps_namespace"], "apps_uid")):
        require(namespace_uid(context, name) == release[key], "Namespace identity changed: refusing credential reuse")


def inspect_image(image):
    result = subprocess.run(["docker", "image", "inspect", image], text=True, capture_output=True)
    return json.loads(result.stdout)[0] if result.returncode == 0 else None


def docker_build(arguments):
    for attempt in range(3):
        result = subprocess.run(arguments, text=True, encoding="utf-8", capture_output=True)
        output = result.stdout + result.stderr
        if result.returncode == 0:
            print(output, end="", flush=True)
            return
        network_error = any(message in output.lower() for message in (
            "no such host", "tls handshake timeout", "i/o timeout", "connection reset by peer"))
        if network_error and attempt < 2:
            print("Transient registry network failure; retrying the same build.", flush=True)
            time.sleep(5 * (attempt + 1))
            continue
        print(output, end="", flush=True)
        raise subprocess.CalledProcessError(result.returncode, arguments)


def verify_images(release):
    require(set(release["images"]) == set(MODULES), "Build all nine release images first")
    for module in MODULES:
        image = f"fintech-{module}:{release['commit']}"
        actual = inspect_image(image)
        require(actual and actual["Id"] == release["images"][module]
                and (actual["Config"].get("Labels") or {}).get(REVISION) == release["commit"],
                f"Image missing or replaced since build: {image}")


def build(bundle):
    bundle, release, _, _, _ = load(bundle)
    source = bundle / "source"
    # Verify the snapshot has not been edited before assigning its commit label.
    with tempfile.TemporaryDirectory(prefix="fintech-release-source-") as temporary:
        index = Path(temporary) / "index"
        git_directory = subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True).strip()
        env = os.environ.copy() | {"GIT_INDEX_FILE": str(index)}
        subprocess.run(["git", "--git-dir", git_directory, "--work-tree", str(source), "read-tree", release["commit"]], cwd=source, env=env, check=True)
        subprocess.run(["git", "--git-dir", git_directory, "--work-tree", str(source), "diff", "--exit-code", "--", "."],
                       cwd=source, env=env, check=True, capture_output=True)
        untracked = subprocess.check_output(["git", "--git-dir", git_directory, "--work-tree", str(source),
                                             "ls-files", "--others"], cwd=source, env=env)
        require(not untracked, "Unexpected files in the committed build snapshot")
    for module in MODULES:
        image = f"fintech-{module}:{release['commit']}"
        existing = inspect_image(image)
        if existing is not None:
            require((existing["Config"].get("Labels") or {}).get(REVISION) == release["commit"],
                    "Existing image has no matching source label; choose another reviewed commit instead of overwriting it")
        else:
            context = source / ("frontend" if module == "frontend" else "deploy/images/postgres" if module == "postgres" else "services")
            dockerfile = context / ("Dockerfile" if module in {"frontend", "postgres"} else module + "/Dockerfile")
            print("Building " + image, flush=True)
            docker_build(["docker", "build", "--label", REVISION + "=" + release["commit"],
                          "-f", str(dockerfile), "-t", image, str(context)])
        release["images"][module] = inspect_image(image)["Id"]
        write_json(bundle / "release.json", release)
    verify_images(release)
    print("Nine images built from the committed snapshot; nothing deployed.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "build", "plan", "load-images"))
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--context")
    parser.add_argument("--commit", default="HEAD")
    args = parser.parse_args()
    if args.command == "prepare":
        require(args.context, "prepare requires --context")
        prepare(args.bundle, args.context, args.commit)
        return
    bundle, release, _, apps, data = load(args.bundle)
    if args.command == "build":
        build(bundle)
    else:
        check_target(release)
        verify_images(release)
        if args.command == "load-images":
            subprocess.run(["kind", "load", "docker-image", "--name", release["context"].removeprefix("kind-"),
                            *(f"fintech-{m}:{release['commit']}" for m in MODULES)], check=True, timeout=900)
        else:
            for name, items in (("data", data), ("apps", apps)):
                kubectl(release["context"], "apply", "--server-side", "--dry-run=server", "-f", "-",
                        input=json.dumps({"apiVersion": "v1", "kind": "List", "items": items}))
            print("Release image IDs, namespace identities and server-side dry-run verified. No resources changed.")


if __name__ == "__main__":
    main()
