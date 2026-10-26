"""Release and first-install safety guards without access to any real credential."""

import base64
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kubernetes_release import ROOT, MODULES, REVISION, check_namespaces, check_target, digest, docker_build, private_path, verify_images, write_json
import subprocess
from kubernetes_shared_deploy import Installer, NoRedirect, bootstrap_statement, broker_request, matches_password
from kubernetes_data_smoke import PASSWORD_VARIABLES


class PrivateBundleTests(unittest.TestCase):
    def test_repository_and_descendants_are_rejected(self):
        for path in (ROOT, ROOT / "tmp/private-release", ROOT / "output/private-release"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "outside"):
                private_path(path)

    def test_another_git_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            with self.assertRaisesRegex(ValueError, "any Git"):
                private_path(root / "release")

    def test_external_path_and_atomic_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = private_path(Path(temporary) / "bundle")
            folder.mkdir()
            write_json(folder / "file.json", {"first": True})
            write_json(folder / "file.json", {"second": True})
            self.assertIn('"second": true', (folder / "file.json").read_text())
            self.assertFalse((folder / "file.new").exists())

    def test_canonical_digest_ignores_mapping_order(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))
        self.assertNotEqual(digest({"a": 1}), digest({"a": 2}))

    def test_only_shared_or_private_namespace_pairs_are_allowed(self):
        check_namespaces("data", "fintech")
        check_namespaces("fintech-smoke-012345abcdef", "fintech-smoke-abcdef012345")
        for pair in (("default", "fintech"), ("data", "ml"), ("data", "data"), ("fintech", "fintech")):
            with self.subTest(pair=pair), self.assertRaises(ValueError):
                check_namespaces(*pair)

    @patch("kubernetes_release.namespace_uid", side_effect=["different-cluster"])
    def test_recreated_cluster_is_rejected(self, _):
        with self.assertRaisesRegex(ValueError, "Cluster"):
            check_target({"context": "kind-test", "cluster_uid": "original"})

    @patch("kubernetes_release.namespace_uid", side_effect=["cluster", "different-namespace"])
    def test_recreated_namespace_is_rejected(self, _):
        with self.assertRaisesRegex(ValueError, "Namespace"):
            check_target({"context": "kind-test", "cluster_uid": "cluster", "data_namespace": "data", "data_uid": "original", "apps_namespace": "fintech"})


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.release = {"commit": "a" * 40, "images": {name: "sha256:" + "b" * 64 for name in MODULES}}
        self.image = {"Id": "sha256:" + "b" * 64, "Config": {"Labels": {REVISION: "a" * 40}}}

    @patch("kubernetes_release.inspect_image")
    def test_all_images_require_matching_id_and_source_label(self, mocked):
        mocked.return_value = self.image
        verify_images(self.release)
        self.assertEqual(mocked.call_count, 9)

    @patch("kubernetes_release.inspect_image")
    def test_replaced_tag_is_rejected(self, mocked):
        mocked.return_value = self.image | {"Id": "sha256:" + "c" * 64}
        with self.assertRaisesRegex(ValueError, "replaced"):
            verify_images(self.release)

    def test_partial_build_is_rejected(self):
        self.release["images"].pop("postgres")
        with self.assertRaisesRegex(ValueError, "nine"):
            verify_images(self.release)

    @patch("kubernetes_release.time.sleep")
    @patch("kubernetes_release.subprocess.run")
    def test_registry_dns_failure_can_retry_same_command(self, mocked, sleep):
        mocked.side_effect = [subprocess.CompletedProcess([], 1, "", "lookup auth.docker.io: no such host"),
                              subprocess.CompletedProcess([], 0, "build passed\n", "")]
        with patch("builtins.print"):
            docker_build(["docker", "build", "fixture"])
        self.assertEqual(mocked.call_count, 2)
        sleep.assert_called_once_with(5)

    @patch("kubernetes_release.time.sleep")
    @patch("kubernetes_release.subprocess.run")
    def test_failed_tests_are_not_retried_or_ignored(self, mocked, sleep):
        mocked.return_value = subprocess.CompletedProcess([], 1, "Maven tests failed\n", "")
        with self.assertRaises(subprocess.CalledProcessError), patch("builtins.print"):
            docker_build(["docker", "build", "fixture"])
        self.assertEqual(mocked.call_count, 1)
        sleep.assert_not_called()


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.passwords = {name: "a" * 48 for name in PASSWORD_VARIABLES}

    def test_transaction_and_lock_precede_team_sql(self):
        sql = bootstrap_statement("CREATE ROLE example;", self.passwords, "b" * 32)
        self.assertLess(sql.index("BEGIN;"), sql.index("pg_advisory_xact_lock"))
        self.assertLess(sql.index("RAISE EXCEPTION"), sql.index("CREATE ROLE example"))
        self.assertTrue(sql.endswith("COMMIT;\n"))
        self.assertIn("fintech_bootstrap.installation", sql)
        self.assertIn(digest(self.passwords), sql)
        self.assertNotIn("DROP SCHEMA", sql)
        self.assertIn("pg_class", sql)
        self.assertIn("n.nspname='public'", sql)

    def test_schema_password_injection_is_rejected(self):
        self.passwords["auth_pwd"] = "'; DROP ROLE postgres;"
        with self.assertRaises(ValueError):
            bootstrap_statement("", self.passwords, "b" * 32)

    def test_release_identity_injection_is_rejected(self):
        with self.assertRaises(ValueError):
            bootstrap_statement("", self.passwords, "';DROP SCHEMA public")

    def test_broker_password_hash_validation_without_reset(self):
        salt, password = b"abcd", "generated-private-fixture"
        user = {"hashing_algorithm": "rabbit_password_hashing_sha256",
                "password_hash": base64.b64encode(salt + hashlib.sha256(salt + password.encode()).digest()).decode()}
        self.assertTrue(matches_password(user, password))
        self.assertFalse(matches_password(user, "another-password"))
        self.assertFalse(matches_password(user | {"hashing_algorithm": "unknown"}, password))

    def test_broker_credentials_cannot_target_remote_urls(self):
        for url in ("https://example.com", "http://localhost:15672", "http://127.0.0.1:15672/path", "http://user@127.0.0.1:15672"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "loopback"):
                broker_request(url, "fixture", "private-fixture", "/api/users")

    def test_broker_redirects_are_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, None, None, None, None))


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.installer = Installer.__new__(Installer)
        self.installer.context = "kind-unit"
        self.installer.owner = "a" * 32
        self.item = {"kind": "ConfigMap", "metadata": {"name": "config", "namespace": "fintech"}}

    @patch.object(Installer, "get", return_value=["uid", "another-owner"])
    def test_foreign_resource_is_not_adopted(self, _):
        with self.assertRaisesRegex(ValueError, "Refusing to adopt"):
            self.installer.check_owned(self.item)

    @patch.object(Installer, "get", return_value=["uid", "a" * 32])
    def test_owned_resource_is_recognized(self, _):
        self.assertEqual(self.installer.check_owned(self.item), ["uid", "a" * 32])

    @patch("kubernetes_shared_deploy.kubectl")
    @patch.object(Installer, "get", side_effect=[None, ["uid", "foreign"]])
    def test_whole_public_set_is_checked_before_any_write(self, _, mocked):
        with self.assertRaises(ValueError):
            self.installer.apply_public([self.item, self.item])
        mocked.assert_not_called()

    @patch("kubernetes_shared_deploy.kubectl")
    @patch.object(Installer, "get", side_effect=[None, ["uid", "foreign"]])
    def test_whole_secret_set_is_checked_before_any_write(self, _, mocked):
        first = {"kind": "Secret", "metadata": {"name": "first", "namespace": "fintech"}, "stringData": {"password": "fixture"}}
        second = {"kind": "Secret", "metadata": {"name": "second", "namespace": "fintech"}, "stringData": {"password": "fixture"}}
        with self.assertRaises(ValueError):
            self.installer.create_credentials([first, second])
        mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
