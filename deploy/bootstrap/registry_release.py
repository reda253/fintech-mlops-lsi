"""Describe and verify a complete GHCR publication; never deploy to Kubernetes."""

import argparse
import json
from pathlib import Path
import re
import subprocess


JAVA = ("api-gateway", "auth-service", "customer-service", "transaction-service",
        "risk-service", "notification-service", "audit-service")
MODULES = (*JAVA, "frontend", "ml-service", "simulator", "postgres")
REVISION = "org.opencontainers.image.revision"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def targets(repository, commit, run_id, attempt):
    require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repository)),
            "Expected GitHub owner/repository")
    require(bool(re.fullmatch(r"[a-f0-9]{40}", commit)), "Expected full commit SHA")
    require(all(re.fullmatch(r"[1-9][0-9]*", value) for value in (run_id, attempt)),
            "Expected positive run ID and attempt")
    prefix = "ghcr.io/" + repository.lower()
    tag = f"{commit}-{run_id}-{attempt}"
    result = []
    for module in MODULES:
        context = "services" if module in JAVA else "deploy/images/postgres" if module == "postgres" else module
        dockerfile = f"services/{module}/Dockerfile" if module in JAVA else f"{context}/Dockerfile"
        result.append({"module": module, "context": context, "dockerfile": dockerfile,
                       "image": f"{prefix}/{module}:{tag}"})
    return result


def receipt(repository, commit, run_id, attempt, module, inspected):
    expected = {item["module"]: item for item in targets(repository, commit, run_id, attempt)}
    require(module in expected, "Unknown publication module")
    image = expected[module]["image"]
    require((inspected.get("Config", {}).get("Labels") or {}).get(REVISION) == commit,
            "Image source revision differs from checkout")
    prefix = image.split(":")[0] + "@"
    matches = {value for value in inspected.get("RepoDigests", [])
               if value.startswith(prefix) and re.fullmatch(re.escape(prefix) + r"sha256:[a-f0-9]{64}", value)}
    require(len(matches) == 1, "Expected exactly one pushed GHCR digest for this image")
    return {"schema": 1, "repository": repository.lower(), "commit": commit,
            "run_id": run_id, "attempt": attempt, "module": module,
            "tag": image, "image": matches.pop()}


def inventory(repository, commit, run_id, attempt, receipts):
    expected = {item["module"]: item for item in targets(repository, commit, run_id, attempt)}
    require(len(receipts) == len(expected), "All eleven publication receipts are required")
    images = {}
    fields = {"schema", "repository", "commit", "run_id", "attempt", "module", "tag", "image"}
    for item in receipts:
        require(isinstance(item, dict) and set(item) == fields, "Invalid receipt fields")
        module = item["module"]
        require(module in expected and module not in images, "Duplicate or unknown image module")
        require(item["schema"] == 1 and item["repository"] == repository.lower()
                and item["commit"] == commit and item["run_id"] == run_id
                and item["attempt"] == attempt, "Mixed source or publication runs")
        require(item["tag"] == expected[module]["image"], "Unexpected image tag")
        prefix = expected[module]["image"].split(":")[0] + "@sha256:"
        require(isinstance(item["image"], str)
                and re.fullmatch(re.escape(prefix) + r"[a-f0-9]{64}", item["image"]),
                "Expected exact GHCR repository and immutable digest")
        images[module] = item["image"]
    return {"schema": 1, "repository": repository.lower(), "commit": commit,
            "run_id": run_id, "attempt": attempt, "platform": "linux/amd64",
            "images": dict(sorted(images.items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("matrix", "receipt", "inventory"))
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--module")
    parser.add_argument("--receipts")
    args = parser.parse_args()
    identity = (args.repository, args.commit, args.run_id, args.attempt)
    entries = targets(*identity)
    if args.command == "matrix":
        result = {"include": entries}
    elif args.command == "receipt":
        entry = next((item for item in entries if item["module"] == args.module), None)
        require(entry is not None, "receipt requires a known --module")
        inspected = subprocess.check_output(["docker", "image", "inspect", entry["image"]], text=True)
        result = receipt(*identity, args.module, json.loads(inspected)[0])
    else:
        require(args.receipts, "inventory requires --receipts")
        files = sorted(Path(args.receipts).glob("receipt-*.json"))
        require(len(files) == len(MODULES), "All eleven receipt files are required")
        result = inventory(*identity, [json.loads(path.read_text(encoding="utf-8")) for path in files])
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
