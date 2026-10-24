"""Tests for ml.src.pipeline.promote (Decision D20, §5.5).

All tests are fully offline — the GitHub API is mocked with unittest.mock.
No GITHUB_TOKEN or network access is required in CI.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from ml.src.pipeline.promote import (
    build_pr_body,
    enable_auto_merge,
    patch_configmap,
)

CONFIGMAP_YAML = """\
apiVersion: v1
kind: ConfigMap
metadata:
  name: ml-service-config
  namespace: ml
data:
  MODEL_MODE: "mock"
  MODEL_URI: ""
  MLFLOW_TRACKING_URI: "http://mlflow.ml.svc.cluster.local:5000"
  MODEL_CACHE_DIR: "/tmp/model-cache"
"""


@pytest.fixture
def tmp_configmap(tmp_path: Path) -> Path:
    """Write a ConfigMap file to a temp dir and return its path."""
    cm = tmp_path / "configmap.yaml"
    cm.write_text(CONFIGMAP_YAML, encoding="utf-8")
    return cm


# ── patch_configmap ──────────────────────────────────────────────────────────


def test_patch_configmap_updates_model_uri(tmp_configmap: Path) -> None:
    old_version = patch_configmap(tmp_configmap, "3")
    content = yaml.safe_load(tmp_configmap.read_text(encoding="utf-8"))
    assert content["data"]["MODEL_URI"] == "models:/fraud-detector/3"
    assert content["data"]["MODEL_MODE"] == "real"
    assert old_version == ""  # was empty initially


def test_patch_configmap_returns_old_version(tmp_configmap: Path) -> None:
    # Pre-populate with an existing version
    data = yaml.safe_load(CONFIGMAP_YAML)
    data["data"]["MODEL_URI"] = "models:/fraud-detector/2"
    tmp_configmap.write_text(yaml.dump(data), encoding="utf-8")

    old_version = patch_configmap(tmp_configmap, "3")
    assert old_version == "2"

    content = yaml.safe_load(tmp_configmap.read_text(encoding="utf-8"))
    assert content["data"]["MODEL_URI"] == "models:/fraud-detector/3"


def test_patch_configmap_raises_if_no_configmap_doc(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("kind: Deployment\nmetadata:\n  name: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No ConfigMap"):
        patch_configmap(bad, "5")


# ── build_pr_body ────────────────────────────────────────────────────────────


def test_build_pr_body_contains_version() -> None:
    metrics = {
        "pr_auc": 0.91,
        "roc_auc": 0.94,
        "conformal_coverage": 0.96,
        "review_rate": 0.014,
        "latency_p95_sec": 0.025,
    }
    body = build_pr_body("3", "2", metrics, run_id="abc123", tracking_uri="http://mlflow:5000")
    assert "fraud-detector` v3" in body
    assert "0.9100" in body
    assert "models:/fraud-detector/3" in body
    assert "models:/fraud-detector/2" in body
    assert "abc123" in body


def test_build_pr_body_no_old_version() -> None:
    body = build_pr_body("1", "", {}, run_id="xyz", tracking_uri="http://mlflow:5000")
    assert "(mock)" in body
    assert "`N/A`" in body


# ── promote (dry_run) ────────────────────────────────────────────────────────


def test_promote_dry_run_patches_configmap(
    tmp_configmap: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """dry_run=True patches the file but makes no HTTP calls."""
    monkeypatch.setenv("GITHUB_TOKEN", "")
    monkeypatch.setenv("GITHUB_REPOSITORY", "")

    import ml.src.pipeline.promote as mod

    monkeypatch.setattr(mod, "CONFIGMAP_PATH", str(tmp_configmap))

    metrics = {"pr_auc": 0.91, "review_rate": 0.014, "latency_p95_sec": 0.02}
    result = mod.promote(
        model_version="4",
        run_id="run-abc",
        metrics=metrics,
        auto_merge=False,
        dry_run=True,
    )

    assert result["pr_number"] == 0
    assert result["branch"] == "promote/model-v4"
    content = yaml.safe_load(tmp_configmap.read_text(encoding="utf-8"))
    assert content["data"]["MODEL_URI"] == "models:/fraud-detector/4"


# ── promote (mocked GitHub API) ──────────────────────────────────────────────


def _make_mock_responses(pr_number: int = 42) -> dict:
    repo_resp = MagicMock()
    repo_resp.status_code = 200
    repo_resp.json.return_value = {"default_branch": "main"}

    ref_resp = MagicMock()
    ref_resp.status_code = 200
    ref_resp.json.return_value = {"object": {"sha": "deadbeef" * 5}}

    create_ref_resp = MagicMock()
    create_ref_resp.status_code = 201
    create_ref_resp.raise_for_status.return_value = None
    create_ref_resp.json.return_value = {}

    contents_get_resp = MagicMock()
    contents_get_resp.status_code = 200
    contents_get_resp.json.return_value = {"sha": "blobsha123"}

    contents_put_resp = MagicMock()
    contents_put_resp.status_code = 200
    contents_put_resp.raise_for_status.return_value = None
    contents_put_resp.json.return_value = {"commit": {"sha": "commitsha"}}

    pr_resp = MagicMock()
    pr_resp.status_code = 201
    pr_resp.raise_for_status.return_value = None
    pr_resp.json.return_value = {
        "number": pr_number,
        "html_url": f"https://github.com/owner/repo/pull/{pr_number}",
        "node_id": "PR_nodeid",
    }

    labels_resp = MagicMock()
    labels_resp.status_code = 200
    labels_resp.raise_for_status.return_value = None

    graphql_resp = MagicMock()
    graphql_resp.status_code = 200
    graphql_resp.raise_for_status.return_value = None
    graphql_resp.json.return_value = {"data": {"enablePullRequestAutoMerge": {"pullRequest": {"number": pr_number}}}}

    return {
        "repo_resp": repo_resp,
        "ref_resp": ref_resp,
        "create_ref_resp": create_ref_resp,
        "contents_get_resp": contents_get_resp,
        "contents_put_resp": contents_put_resp,
        "pr_resp": pr_resp,
        "labels_resp": labels_resp,
        "graphql_resp": graphql_resp,
    }


@patch("ml.src.pipeline.promote.requests.post")
@patch("ml.src.pipeline.promote.requests.put")
@patch("ml.src.pipeline.promote.requests.get")
def test_promote_opens_pr(
    mock_get: MagicMock,
    mock_put: MagicMock,
    mock_post: MagicMock,
    tmp_configmap: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full promote() flow with mocked GitHub API — no real HTTP."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake_token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    import ml.src.pipeline.promote as mod

    monkeypatch.setattr(mod, "CONFIGMAP_PATH", str(tmp_configmap))

    mocks = _make_mock_responses(42)
    mock_get.side_effect = [
        mocks["repo_resp"],  # GET /repos/{repo}
        mocks["ref_resp"],  # GET /repos/{repo}/git/ref/heads/main
        mocks["contents_get_resp"],  # GET /repos/{repo}/contents/{file}?ref=branch
        mocks["pr_resp"],  # GET /repos/{repo}/pulls/42 (for auto_merge node_id)
    ]
    mock_post.side_effect = [
        mocks["create_ref_resp"],  # POST /repos/{repo}/git/refs  (create branch)
        mocks["pr_resp"],  # POST /repos/{repo}/pulls
        mocks["labels_resp"],  # POST /repos/{repo}/issues/{n}/labels
        mocks["graphql_resp"],  # POST /graphql (enable auto merge)
    ]
    mock_put.side_effect = [
        mocks["contents_put_resp"],  # PUT /repos/{repo}/contents/{file}
    ]

    metrics = {"pr_auc": 0.91, "review_rate": 0.014, "latency_p95_sec": 0.02}
    result = mod.promote(
        model_version="5",
        run_id="run-xyz",
        metrics=metrics,
        auto_merge=True,
        dry_run=False,
    )

    assert result["pr_number"] == 42
    assert "pull/42" in result["pr_url"]
    assert result["branch"] == "promote/model-v5"

    # Verify configmap was patched
    content = yaml.safe_load(tmp_configmap.read_text(encoding="utf-8"))
    assert content["data"]["MODEL_URI"] == "models:/fraud-detector/5"
    assert content["data"]["MODEL_MODE"] == "real"


@patch("ml.src.pipeline.promote.requests.post")
@patch("ml.src.pipeline.promote.requests.get")
def test_enable_auto_merge(mock_get: MagicMock, mock_post: MagicMock) -> None:
    mocks = _make_mock_responses(10)
    mock_get.return_value = mocks["pr_resp"]
    mock_post.return_value = mocks["graphql_resp"]

    enable_auto_merge("owner/repo", "token123", 10)
    assert mock_post.called
    assert "api.github.com/graphql" in mock_post.call_args[0][0]


def test_promote_raises_without_token(
    tmp_configmap: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    import ml.src.pipeline.promote as mod

    monkeypatch.setattr(mod, "CONFIGMAP_PATH", str(tmp_configmap))

    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        mod.promote(model_version="1", run_id="r", metrics={}, dry_run=False)


def test_promote_raises_without_repo(
    tmp_configmap: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    import ml.src.pipeline.promote as mod

    monkeypatch.setattr(mod, "CONFIGMAP_PATH", str(tmp_configmap))

    with pytest.raises(RuntimeError, match="GITHUB_REPOSITORY"):
        mod.promote(model_version="1", run_id="r", metrics={}, dry_run=False)


def test_promote_raises_if_configmap_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ml.src.pipeline.promote as mod

    monkeypatch.setattr(mod, "CONFIGMAP_PATH", "/nonexistent/path/configmap.yaml")
    with pytest.raises(FileNotFoundError):
        mod.promote(model_version="1", run_id="r", metrics={}, dry_run=True)
