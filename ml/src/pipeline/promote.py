"""Automated model promotion via GitHub Pull Request (Decision D20, §5.5).

Usage (called by run.py after quality gates pass):
    python -m ml.src.pipeline.promote \
        --run-id <mlflow_run_id> \
        --model-version 3 \
        --metrics '{"pr_auc": 0.91, "roc_auc": 0.95, "review_rate": 0.014}' \
        --auto-merge

Environment variables consumed:
    GITHUB_TOKEN        Personal access token or GitHub App installation token.
    GITHUB_REPOSITORY   "owner/repo" (e.g. "reda253/fintech-mlops-lsi").
    MLFLOW_TRACKING_URI MLflow server URI (default: http://localhost:5000).
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests
import yaml

logger = logging.getLogger(__name__)

CONFIGMAP_PATH = "deploy/k8s/ml-service/configmap.yaml"
BRANCH_PREFIX = "promote/model-v"
GH_API = "https://api.github.com"


# --------------------------------------------------------------------------- #
#  ConfigMap patching                                                         #
# --------------------------------------------------------------------------- #


def patch_configmap(configmap_path: Path, new_version: str) -> str:
    """Read the ConfigMap YAML and update MODEL_URI to the new version.

    Returns the old version string (or '' if not set).
    """
    text = configmap_path.read_text(encoding="utf-8")
    docs = list(yaml.safe_load_all(text))
    configmap = next(
        (d for d in docs if isinstance(d, dict) and d.get("kind") == "ConfigMap"), None
    )
    if configmap is None:
        raise ValueError(f"No ConfigMap document found in {configmap_path}")

    data: dict[str, str] = configmap.setdefault("data", {})
    old_uri = data.get("MODEL_URI", "")

    # Parse old version number for logging
    old_version = ""
    m = re.search(r"/(\d+)$", old_uri)
    if m:
        old_version = m.group(1)

    data["MODEL_URI"] = f"models:/fraud-detector/{new_version}"
    data["MODEL_MODE"] = "real"  # switch away from mock

    # Re-serialise — preserve key ordering
    new_text = yaml.dump(configmap, default_flow_style=False, sort_keys=False, allow_unicode=True)
    configmap_path.write_text(new_text, encoding="utf-8")
    return old_version


# --------------------------------------------------------------------------- #
#  GitHub API helpers                                                         #
# --------------------------------------------------------------------------- #


def gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def gh_post(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = requests.post(url, headers=gh_headers(token), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def gh_put(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = requests.put(url, headers=gh_headers(token), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def create_branch(repo: str, token: str, branch: str, base_sha: str) -> None:
    url = f"{GH_API}/repos/{repo}/git/refs"
    gh_post(url, token, {"ref": f"refs/heads/{branch}", "sha": base_sha})


def get_default_branch_sha(repo: str, token: str) -> tuple[str, str]:
    """Return (default_branch_name, head_sha)."""
    resp = requests.get(
        f"{GH_API}/repos/{repo}",
        headers=gh_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    default = resp.json()["default_branch"]
    resp2 = requests.get(
        f"{GH_API}/repos/{repo}/git/ref/heads/{default}",
        headers=gh_headers(token),
        timeout=30,
    )
    resp2.raise_for_status()
    sha = resp2.json()["object"]["sha"]
    return default, sha


def push_file_update(
    repo: str,
    token: str,
    branch: str,
    file_path: str,
    new_content: str,
    commit_message: str,
) -> str:
    """Create or update a file on the remote branch via the Contents API."""
    url = f"{GH_API}/repos/{repo}/contents/{file_path}"

    # Fetch current blob SHA on that branch
    resp = requests.get(url, headers=gh_headers(token), params={"ref": branch}, timeout=30)
    blob_sha: str | None = None
    if resp.status_code == 200:
        blob_sha = resp.json()["sha"]

    payload: dict[str, Any] = {
        "message": commit_message,
        "content": base64.b64encode(new_content.encode("utf-8")).decode("utf-8"),
        "branch": branch,
    }
    if blob_sha:
        payload["sha"] = blob_sha

    result = gh_put(url, token, payload)
    return str(result["commit"]["sha"])


def create_pull_request(
    repo: str,
    token: str,
    head: str,
    base: str,
    title: str,
    body: str,
    labels: list[str],
) -> dict[str, Any]:
    pr = gh_post(
        f"{GH_API}/repos/{repo}/pulls",
        token,
        {"title": title, "body": body, "head": head, "base": base},
    )
    pr_number = pr["number"]

    if labels:
        try:
            requests.post(
                f"{GH_API}/repos/{repo}/issues/{pr_number}/labels",
                headers=gh_headers(token),
                json={"labels": labels},
                timeout=30,
            ).raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not attach labels to PR #%d: %s", pr_number, exc)

    return pr


def enable_auto_merge(repo: str, token: str, pr_number: int) -> None:
    """Enable auto-merge (squash) on the PR via the GraphQL API."""
    # First get the PR node_id
    resp = requests.get(
        f"{GH_API}/repos/{repo}/pulls/{pr_number}",
        headers=gh_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    node_id = resp.json()["node_id"]

    mutation = """
    mutation EnableAutoMerge($pullRequestId: ID!, $mergeMethod: PullRequestMergeMethod!) {
      enablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId, mergeMethod: $mergeMethod}) {
        pullRequest { number }
      }
    }
    """
    gql_resp = requests.post(
        "https://api.github.com/graphql",
        headers=gh_headers(token),
        json={
            "query": mutation,
            "variables": {"pullRequestId": node_id, "mergeMethod": "SQUASH"},
        },
        timeout=30,
    )
    gql_resp.raise_for_status()
    data = gql_resp.json()
    if "errors" in data:
        logger.warning("Auto-merge GraphQL errors: %s", data["errors"])


# --------------------------------------------------------------------------- #
#  PR body builder                                                            #
# --------------------------------------------------------------------------- #


def build_pr_body(
    model_version: str,
    old_version: str,
    metrics: dict[str, float],
    run_id: str,
    tracking_uri: str,
) -> str:
    pr_auc_str = f"`{metrics['pr_auc']:.4f}`" if "pr_auc" in metrics else "`N/A`"
    roc_auc_str = f"`{metrics['roc_auc']:.4f}`" if "roc_auc" in metrics else "`N/A`"
    cov_str = (
        f"`{metrics['conformal_coverage']:.4f}`"
        if "conformal_coverage" in metrics
        else "`N/A`"
    )
    rev_str = (
        f"`{metrics['review_rate']:.3%}`"
        if "review_rate" in metrics
        else "`N/A`"
    )
    lat_str = (
        f"`{metrics['latency_p95_sec'] * 1000:.1f} ms`"
        if "latency_p95_sec" in metrics
        else "`N/A`"
    )

    lines = [
        f"## 🤖 Automated Model Promotion — `fraud-detector` v{model_version}",
        "",
        "This PR was opened automatically by the ML pipeline after all quality gates passed.",
        "",
        "### Quality Gate Results",
        "",
        "| Gate | Value | Threshold | Status |",
        "|------|-------|-----------|--------|",
        f"| PR-AUC | {pr_auc_str} | ≥ champion − 0.01 | ✅ |",
        f"| ROC-AUC | {roc_auc_str} | — | ℹ️ |",
        f"| Conformal coverage | {cov_str} | ≥ 0.93 | ✅ |",
        f"| Review rate | {rev_str} | ≤ 2% | ✅ |",
        f"| Latency p95 | {lat_str} | < 50 ms | ✅ |",
        "",
        "### Change",
        "",
        f"- **Before:** `MODEL_URI=models:/fraud-detector/{old_version or '(mock)'}`",
        f"- **After:** `MODEL_URI=models:/fraud-detector/{model_version}`",
        "",
        "### MLflow Run",
        "",
        f"- Run ID: `{run_id}`",
        f"- Tracking URI: `{tracking_uri}`",
        "",
        "### Rollback",
        "",
        "```bash",
        "git revert <this-merge-commit-sha>",
        "# Argo CD will roll back ml-service to the previous MODEL_URI",
        "```",
        "",
        "> ⚠️ Do not edit this PR manually. Argo CD will deploy automatically on merge.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Main promote function                                                      #
# --------------------------------------------------------------------------- #


def promote(
    model_version: str,
    run_id: str,
    metrics: dict[str, float],
    auto_merge: bool = True,
    tracking_uri: str = "http://localhost:5000",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Open a GitHub PR updating MODEL_URI in the ml-service ConfigMap.

    Args:
        model_version: Registered MLflow model version number (e.g. "3").
        run_id:        MLflow parent run ID (for linking in PR body).
        metrics:       Quality gate metrics dict from step_quality_gates().
        auto_merge:    If True, enable GitHub auto-merge on the PR.
        tracking_uri:  MLflow tracking server URI (for PR body link).
        dry_run:       If True, patch the ConfigMap locally but skip GitHub API calls.

    Returns:
        dict with keys: branch, pr_url, pr_number (0 if dry_run).
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    if not dry_run:
        if not token:
            raise RuntimeError("GITHUB_TOKEN environment variable is not set")
        if not repo:
            raise RuntimeError("GITHUB_REPOSITORY environment variable is not set")

    branch = f"{BRANCH_PREFIX}{model_version}"
    configmap_path = Path(CONFIGMAP_PATH)

    if not configmap_path.exists():
        raise FileNotFoundError(f"ConfigMap not found at: {configmap_path}")

    # 1. Patch the ConfigMap locally
    old_version = patch_configmap(configmap_path, model_version)
    new_content = configmap_path.read_text(encoding="utf-8")
    logger.info(
        "Patched %s: MODEL_URI v%s → v%s",
        CONFIGMAP_PATH,
        old_version or "(mock)",
        model_version,
    )

    if dry_run:
        logger.info("[DRY RUN] Skipping GitHub API calls. Branch: %s", branch)
        return {"branch": branch, "pr_url": "", "pr_number": 0}

    # 2. Create branch off default branch
    default_branch, head_sha = get_default_branch_sha(repo, token)
    create_branch(repo, token, branch, head_sha)
    logger.info("Created branch %s off %s (%s)", branch, default_branch, head_sha[:8])

    # 3. Push patched ConfigMap to the branch
    commit_msg = f"feat(model): promote fraud-detector to v{model_version} (D20)"
    push_file_update(repo, token, branch, CONFIGMAP_PATH, new_content, commit_msg)
    logger.info("Pushed commit to %s", branch)

    # 4. Open Pull Request
    pr_title = f"feat(model): promote fraud-detector v{model_version} [AUTO_MERGE]"
    pr_body = build_pr_body(model_version, old_version, metrics, run_id, tracking_uri)
    labels = ["AUTO_MERGE", "mlops", "model-promotion"]
    pr = create_pull_request(repo, token, branch, default_branch, pr_title, pr_body, labels)
    pr_number = pr["number"]
    pr_url = pr.get("html_url", "")
    logger.info("Opened PR #%d: %s", pr_number, pr_url)

    # 5. Enable auto-merge if requested
    if auto_merge:
        try:
            enable_auto_merge(repo, token, pr_number)
            logger.info("Auto-merge enabled on PR #%d (squash)", pr_number)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not enable auto-merge (repository may require manual setup): %s", exc
            )

    return {"branch": branch, "pr_url": pr_url, "pr_number": pr_number}


# --------------------------------------------------------------------------- #
#  CLI entry point                                                            #
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(description="Open a model-promotion PR (Decision D20)")
    parser.add_argument("--model-version", required=True, help="MLflow registered model version")
    parser.add_argument("--run-id", required=True, help="MLflow parent run ID")
    parser.add_argument(
        "--metrics",
        default="{}",
        help="JSON string of quality gate metrics",
    )
    parser.add_argument(
        "--auto-merge",
        action="store_true",
        default=os.environ.get("AUTO_MERGE", "true").lower() == "true",
        help="Enable auto-merge on the PR when CI is green",
    )
    parser.add_argument(
        "--tracking-uri",
        default=os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"),
    )
    parser.add_argument("--dry-run", action="store_true", help="Patch locally, skip GitHub API")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    metrics = json.loads(args.metrics)
    result = promote(
        model_version=args.model_version,
        run_id=args.run_id,
        metrics=metrics,
        auto_merge=args.auto_merge,
        tracking_uri=args.tracking_uri,
        dry_run=args.dry_run,
    )

    if result["pr_url"]:
        print(f"PR opened: {result['pr_url']}")
    else:
        print(f"[DRY RUN] Branch: {result['branch']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
