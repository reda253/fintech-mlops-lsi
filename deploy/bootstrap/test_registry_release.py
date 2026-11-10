import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from registry_release import JAVA, MODULES, REVISION, inventory, receipt, targets


class RegistryReleaseTests(unittest.TestCase):
    def setUp(self):
        self.identity = ("reda253/fintech-mlops-lsi", "a" * 40, "1234", "1")
        self.targets = targets(*self.identity)
        self.receipts = []
        for target in self.targets:
            self.receipts.append(receipt(*self.identity, target["module"], {
                "Config": {"Labels": {REVISION: self.identity[1]}},
                "RepoDigests": [target["image"].split(":")[0] + "@sha256:" + "b" * 64],
            }))

    def test_exact_eleven_images(self):
        self.assertEqual(11, len(self.targets))
        self.assertEqual(set(MODULES), {item["module"] for item in self.targets})

    def test_build_paths_exist(self):
        root = Path(__file__).resolve().parents[2]
        for item in self.targets:
            self.assertTrue((root / item["context"]).is_dir())
            self.assertTrue((root / item["dockerfile"]).is_file())

    def test_java_reactor_context(self):
        for item in self.targets:
            if item["module"] in JAVA:
                self.assertEqual("services", item["context"])

    def test_repository_normalized(self):
        result = targets("Owner/Repository", *self.identity[1:])
        self.assertTrue(result[0]["image"].startswith("ghcr.io/owner/repository/"))

    def test_no_latest_or_short_sha(self):
        self.assertTrue(all(item["image"].endswith(":" + "a" * 40 + "-1234-1")
                            for item in self.targets))

    def test_reruns_have_distinct_tags(self):
        self.assertNotEqual(self.targets[0]["image"], targets(*self.identity[:3], "2")[0]["image"])

    def test_reject_invalid_repository(self):
        for value in ("owner/repo;echo", "../repo", "https://github.com/owner/repo", "owner/repo/other"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                targets(value, *self.identity[1:])

    def test_reject_invalid_commit(self):
        for value in ("main", "a" * 7, "A" * 40, "-" + "a" * 39):
            with self.subTest(value=value), self.assertRaises(ValueError):
                targets(self.identity[0], value, *self.identity[2:])

    def test_reject_invalid_run(self):
        for value in ("0", "-1", "1;echo", "", "01"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                targets(*self.identity[:2], value, "1")

    def test_missing_push_digest_rejected(self):
        with self.assertRaisesRegex(ValueError, "pushed GHCR digest"):
            receipt(*self.identity, "frontend", {"Config": {"Labels": {REVISION: "a" * 40}}, "RepoDigests": []})

    def test_source_label_required(self):
        for labels in (None, {}, {REVISION: "c" * 40}):
            with self.subTest(labels=labels), self.assertRaisesRegex(ValueError, "source revision"):
                receipt(*self.identity, "frontend", {"Config": {"Labels": labels}})

    def test_other_registry_digest_not_accepted(self):
        with self.assertRaises(ValueError):
            receipt(*self.identity, "frontend", {"Config": {"Labels": {REVISION: "a" * 40}},
                    "RepoDigests": ["docker.io/other/frontend@sha256:" + "b" * 64]})

    def test_ambiguous_digests_rejected(self):
        prefix = self.targets[0]["image"].split(":")[0] + "@sha256:"
        with self.assertRaises(ValueError):
            receipt(*self.identity, MODULES[0], {"Config": {"Labels": {REVISION: "a" * 40}},
                    "RepoDigests": [prefix + "b" * 64, prefix + "c" * 64]})

    def test_complete_inventory(self):
        result = inventory(*self.identity, list(reversed(self.receipts)))
        self.assertEqual("linux/amd64", result["platform"])
        self.assertEqual(set(MODULES), set(result["images"]))
        self.assertTrue(all("@sha256:" in image for image in result["images"].values()))
        self.assertNotIn("Config", json.dumps(result))

    def test_partial_inventory_rejected(self):
        with self.assertRaisesRegex(ValueError, "eleven"):
            inventory(*self.identity, self.receipts[:-1])

    def test_duplicates_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            inventory(*self.identity, [self.receipts[0]] * 11)

    def test_mixed_identity_rejected(self):
        for field, value in (("repository", "other/repo"), ("commit", "c" * 40),
                             ("run_id", "9999"), ("attempt", "2"), ("schema", 2)):
            changed = copy.deepcopy(self.receipts)
            changed[0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Mixed"):
                inventory(*self.identity, changed)

    def test_modified_digest_or_tag_rejected(self):
        for field, value in (("tag", "ghcr.io/other/repo:latest"),
                             ("image", "ghcr.io/other/repo@sha256:" + "b" * 64),
                             ("image", self.receipts[0]["image"][:-1]), ("image", "https://example.com")):
            changed = copy.deepcopy(self.receipts)
            changed[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                inventory(*self.identity, changed)

    def test_unknown_fields_rejected(self):
        changed = copy.deepcopy(self.receipts)
        changed[0]["credentials"] = "must-not-be-exported"
        with self.assertRaisesRegex(ValueError, "fields"):
            inventory(*self.identity, changed)

    def test_unknown_module_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            receipt(*self.identity, "not-a-service", {})

    def test_matrix_cli_without_docker_or_cluster(self):
        output = subprocess.check_output([
            sys.executable, "-B", str(Path(__file__).with_name("registry_release.py")), "matrix",
            "--repository", self.identity[0], "--commit", self.identity[1],
            "--run-id", self.identity[2], "--attempt", self.identity[3]], text=True)
        self.assertEqual({"include": self.targets}, json.loads(output))


if __name__ == "__main__":
    unittest.main()
