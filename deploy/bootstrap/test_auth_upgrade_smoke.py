import unittest
from http.client import RemoteDisconnected
from unittest.mock import patch
from urllib.error import HTTPError

from auth_upgrade_smoke import HTTP, MODULES, NEW, REPO, release_images, request, wait_for


class AuthUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.inventory = {
            "schema": 1, "repository": REPO, "commit": NEW, "platform": "linux/amd64",
            "images": {module: f"ghcr.io/{REPO}/{module}@sha256:" + "a" * 64 for module in MODULES},
        }

    def test_selects_only_required_images(self):
        self.inventory["images"]["frontend"] = "unused"
        self.assertEqual(set(release_images(self.inventory)), set(MODULES))

    def test_requires_reviewed_release(self):
        for field, value in (("commit", "main"), ("platform", "linux/arm64"), ("repository", "other/repo")):
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                release_images(self.inventory | {field: value})

    def test_rejects_missing_image(self):
        self.inventory["images"].pop("postgres")
        with self.assertRaisesRegex(RuntimeError, "postgres"):
            release_images(self.inventory)

    def test_rejects_mutable_or_wrong_module_image(self):
        for image in (f"ghcr.io/{REPO}/auth-service:latest", self.inventory["images"]["api-gateway"]):
            self.inventory["images"]["auth-service"] = image
            with self.subTest(image=image), self.assertRaisesRegex(RuntimeError, "auth-service"):
                release_images(self.inventory)

    def test_http_errors_report_status_without_reading_body(self):
        error = HTTPError("http://127.0.0.1:1234", 401, "Unauthorized", {}, None)
        with patch.object(HTTP, "open", side_effect=error) as send:
            self.assertEqual(request(1234, "/api/v1/auth/me", token="synthetic"), (401, None))
            sent = send.call_args.args[0]
            self.assertEqual(sent.full_url, "http://127.0.0.1:1234/api/v1/auth/me")
            self.assertEqual(sent.get_header("Authorization"), "Bearer synthetic")

    def test_wait_retries_disconnected_startup_probe(self):
        with patch("auth_upgrade_smoke.time.sleep"), patch.object(
            HTTP, "open", side_effect=RemoteDisconnected("starting")
        ) as send:
            def check():
                return send.call_count > 0 or request(1234, "/actuator/health/readiness")

            wait_for(check, "fixture")
            self.assertEqual(1, send.call_count)
