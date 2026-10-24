import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from unittest.mock import patch

from transaction_compose_ci import assert_isolated
from transaction_smoke_test import assert_stays_ready, request, verify, wait_for_checks


def response_for_path(base_url, path, method="GET"):
    if method == "GET" and path.endswith(("/liveness", "/readiness")):
        return 200, {}, {"status": "UP"}
    return 401, {"WWW-Authenticate": "Bearer"}, {"status": 401}


class SmokeTests(unittest.TestCase):
    @patch("transaction_smoke_test.request", side_effect=response_for_path)
    def test_healthy_probes_and_protected_routes(self, mocked):
        verify("http://localhost:8090")
        self.assertEqual(mocked.call_count, 7)

    def test_dependency_outage_keeps_liveness_up(self):
        def outage(base_url, path, method="GET"):
            if path.endswith("/readiness") and method == "GET":
                return 503, {}, {"status": "DOWN"}
            return response_for_path(base_url, path, method)

        with patch("transaction_smoke_test.request", side_effect=outage):
            verify("http://localhost:8090", "DOWN")

    def test_public_prometheus_is_rejected(self):
        def insecure(base_url, path, method="GET"):
            if path == "/actuator/prometheus":
                return 200, {}, {}
            return response_for_path(base_url, path, method)

        with patch("transaction_smoke_test.request", side_effect=insecure):
            with self.assertRaisesRegex(AssertionError, "401 Bearer"):
                verify("http://localhost")

    @patch("transaction_smoke_test.request", return_value=(503, {}, {"status": "DOWN"}))
    def test_failed_liveness_is_rejected(self, mocked):
        with self.assertRaisesRegex(AssertionError, "Liveness"):
            verify("http://localhost", "DOWN")

    @patch("transaction_smoke_test.verify", side_effect=AssertionError("not ready"))
    def test_timeout_is_a_failure(self, mocked):
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            wait_for_checks("http://localhost", timeout=0)

    @patch("transaction_smoke_test.time.sleep")
    @patch("transaction_smoke_test.verify", side_effect=[OSError("starting"), None])
    def test_startup_is_retried(self, mocked, sleep):
        wait_for_checks("http://localhost")
        self.assertEqual(mocked.call_count, 2)

    @patch("transaction_smoke_test.verify")
    def test_stays_ready_passes_when_always_up(self, mocked):
        assert_stays_ready("http://localhost", duration=0)
        mocked.assert_called_once_with("http://localhost", "UP")

    @patch("transaction_smoke_test.time.sleep")
    @patch("transaction_smoke_test.verify", side_effect=[None, AssertionError("Readiness must be HTTP 200 UP")])
    def test_stays_ready_fails_on_first_down(self, mocked, sleep):
        with self.assertRaisesRegex(RuntimeError, "left UP"):
            assert_stays_ready("http://localhost", duration=60)
        self.assertEqual(mocked.call_count, 2)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(401 if self.path == "/protected" else 200)
                self.send_header("Content-Type", "application/json")
                if self.path != "/missing-correlation":
                    self.send_header("X-Correlation-Id", self.headers["X-Correlation-Id"])
                self.end_headers()
                self.wfile.write(json.dumps({"status": 401 if self.path == "/protected" else "UP"}).encode())

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_success_and_correlation_header(self):
        self.assertEqual(request(self.url, "/health")[2], {"status": "UP"})

    def test_http_error_body_is_read(self):
        self.assertEqual(request(self.url, "/protected")[0], 401)

    def test_missing_correlation_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, "correlation"):
            request(self.url, "/missing-correlation")


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.project = "transaction-ci-test"
        self.config = {
            "name": self.project,
            "services": {
                "postgres": {"volumes": [{"source": "transaction_ci_data"}]},
                "rabbitmq": {},
            },
            "volumes": {"transaction_ci_data": {"name": self.project + "_transaction_ci_data"}},
        }

    def test_private_project_is_allowed(self):
        assert_isolated(self.config, self.project)

    def test_developer_project_is_rejected(self):
        with self.assertRaises(ValueError):
            assert_isolated(self.config, "fintech-mlops-lsi")

    def test_fixed_container_name_is_rejected(self):
        self.config["services"]["postgres"]["container_name"] = "fintech-postgres"
        with self.assertRaises(ValueError):
            assert_isolated(self.config, self.project)

    def test_exposed_broker_port_is_rejected(self):
        self.config["services"]["rabbitmq"]["ports"] = [{"published": "5672"}]
        with self.assertRaises(ValueError):
            assert_isolated(self.config, self.project)

    def test_developer_volume_is_rejected(self):
        self.config["services"]["postgres"]["volumes"][0]["source"] = "postgres_data"
        with self.assertRaises(ValueError):
            assert_isolated(self.config, self.project)

    def test_external_volume_is_rejected(self):
        self.config["volumes"]["transaction_ci_data"]["external"] = True
        with self.assertRaises(ValueError):
            assert_isolated(self.config, self.project)


if __name__ == "__main__":
    unittest.main()
