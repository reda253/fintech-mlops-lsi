import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import ci_bot_write_test as probe


class WriteProbeTest(unittest.TestCase):
    def setUp(self):
        self.previous_directory = Path.cwd()
        self.directory = tempfile.TemporaryDirectory()
        os.chdir(self.directory.name)
        self.addCleanup(self.restore_directory)
        for args in [
            ["init", "-q"],
            ["config", "user.name", "Probe test"],
            ["config", "user.email", "test@example.invalid"],
            ["config", "core.autocrlf", "false"],
        ]:
            self.git(*args)
        Path(probe.TARGET).parent.mkdir(parents=True)
        Path(probe.TARGET).write_text("resources: []\nimages: []\n", encoding="utf-8")
        Path("other.txt").write_text("original\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial test state")
        environment = patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"})
        environment.start()
        self.addCleanup(environment.stop)

    def restore_directory(self):
        os.chdir(self.previous_directory)
        self.directory.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], check=True, capture_output=True)

    def stage_probe(self):
        probe.prepare()
        self.git("add", probe.TARGET)

    def test_accepts_only_comment_change(self):
        self.stage_probe()
        probe.verify()
        self.assertIn("# ci-bot-write-test: 123/1", Path(probe.TARGET).read_text())

    def test_rejects_other_staged_file(self):
        self.stage_probe()
        Path("other.txt").write_text("changed\n", encoding="utf-8")
        self.git("add", "other.txt")
        with self.assertRaises(RuntimeError):
            probe.verify()

    def test_rejects_untracked_file(self):
        self.stage_probe()
        Path("unexpected.txt").write_text("unexpected", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            probe.verify()

    def test_rejects_unstaged_change(self):
        self.stage_probe()
        Path("other.txt").write_text("changed\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            probe.verify()

    def test_rejects_yaml_field_change(self):
        self.stage_probe()
        Path(probe.TARGET).write_text("resources: [unexpected.yaml]\n", encoding="utf-8")
        self.git("add", probe.TARGET)
        with self.assertRaises(RuntimeError):
            probe.verify()

    def test_rejects_dirty_start(self):
        Path("other.txt").write_text("changed\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            probe.prepare()

    def test_rejects_invalid_run_identifier(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "invalid\nvalue"}):
            with self.assertRaises(RuntimeError):
                probe.prepare()


if __name__ == "__main__":
    unittest.main()
