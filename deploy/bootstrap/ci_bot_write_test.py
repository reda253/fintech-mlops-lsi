"""Prepare and restrict a harmless Git write probe to the demo tags file."""

import os
from pathlib import Path
import re
import subprocess
import sys


TARGET = "deploy/overlays/demo/kustomization.yaml"
MARKER = "# ci-bot-write-test: "


def git(*args):
    return subprocess.check_output(["git", *args])


def paths(output):
    return [path.decode("utf-8") for path in output.split(b"\0") if path]


def check_target():
    target = Path(TARGET)
    if any(path.is_symlink() for path in [target, *target.parents]):
        raise RuntimeError("The allowed target must not be a symbolic link.")
    git("ls-files", "--error-unmatch", "--", TARGET)
    if not target.is_file():
        raise RuntimeError("The allowed target must already exist.")
    return target


def prepare():
    if git("status", "--porcelain"):
        raise RuntimeError("The worktree must be clean before the write probe.")
    target = check_target()
    run_id = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ["GITHUB_RUN_ATTEMPT"]
    if not re.fullmatch(r"[0-9]+", run_id) or not re.fullmatch(r"[0-9]+", attempt):
        raise RuntimeError("Invalid run identifier.")
    original = target.read_text(encoding="utf-8")
    # Keep YAML fields untouched and replace only the previous probe comment.
    lines = [line for line in original.splitlines() if not line.startswith(MARKER)]
    target.write_text("\n".join(lines) + f"\n{MARKER}{run_id}/{attempt}\n", encoding="utf-8")


def verify():
    check_target()
    if paths(git("ls-files", "--others", "--exclude-standard", "-z")):
        raise RuntimeError("Unexpected untracked files.")
    if git("diff", "--name-only", "-z"):
        raise RuntimeError("Unexpected unstaged changes.")
    if paths(git("diff", "--cached", "--name-only", "-z")) != [TARGET]:
        raise RuntimeError("The staged change must affect only the allowed target.")
    staged = git("show", f":{TARGET}").decode("utf-8")
    original = git("show", f"HEAD:{TARGET}").decode("utf-8")
    without_marker = lambda text: [line for line in text.splitlines() if not line.startswith(MARKER)]
    if without_marker(staged) != without_marker(original):
        raise RuntimeError("The write probe must not change YAML fields.")


if __name__ == "__main__":
    if sys.argv[1:] == ["prepare"]:
        prepare()
    elif sys.argv[1:] == ["verify"]:
        verify()
    else:
        raise SystemExit("Usage: ci_bot_write_test.py prepare|verify")
