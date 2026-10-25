import threading
from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch

from frontend_compose_ci import assert_isolated
from frontend_gateway_stub import GatewayStub
from frontend_smoke_test import Assets, request, verify_proxy, verify_static


class AssetsTests(unittest.TestCase):
    def test_collects_only_compiled_asset_urls(self):
        parser = Assets()
        parser.feed('<script src="/assets/app.js"></script><link href="/assets/app.css"><link href="/favicon.svg">')
        self.assertEqual(parser.paths, ["/assets/app.js", "/assets/app.css"])

    @patch("frontend_smoke_test.request", return_value=(200, {}, b"not React"))
    def test_non_react_html_is_rejected(self, mocked):
        with self.assertRaisesRegex(AssertionError, "compiled React"):
            verify_static("http://localhost")

    @patch("frontend_smoke_test.request", return_value=(200, {}, b'<div id="root"></div>'))
    def test_missing_security_header_is_rejected(self, mocked):
        with self.assertRaisesRegex(AssertionError, "nosniff"):
            verify_static("http://localhost")


class GatewayFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), GatewayStub)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_fixture_satisfies_proxy_contract_and_streams(self):
        verify_proxy(self.url)

    def test_errors_are_returned_without_html_fallback(self):
        status, headers, body = request(self.url, "/not-an-api")
        self.assertEqual(status, 404)
        self.assertEqual(headers.get_content_type(), "application/json")
        self.assertIn(b'"status": 404', body)


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.project = "frontend-ci-unit"
        self.config = {"name": self.project, "services": {"frontend": {}, "api-gateway": {}}}

    def test_isolated_project_is_accepted(self):
        assert_isolated(self.config, self.project)

    def test_development_project_is_rejected(self):
        with self.assertRaises(ValueError):
            assert_isolated(self.config, "fintech-mlops-lsi")

    def test_persistent_volume_is_rejected(self):
        self.config["volumes"] = {"postgres_data": {}}
        with self.assertRaises(ValueError):
            assert_isolated(self.config, self.project)

    def test_fixed_container_name_is_rejected(self):
        self.config["services"]["frontend"]["container_name"] = "fintech-frontend"
        with self.assertRaises(ValueError):
            assert_isolated(self.config, self.project)


if __name__ == "__main__":
    unittest.main()
