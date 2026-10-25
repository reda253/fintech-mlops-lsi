"""Regression tests for private data fixtures and safe schema bootstrap inputs."""

import copy
import io
import json
import unittest
from unittest.mock import patch

from check_kubernetes_data import validate_data
from kubernetes_data_smoke import bootstrap_sql, PASSWORD_VARIABLES, rabbit_request, secret, transaction_resources


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.passwords = {name: "a" * 48 for name in PASSWORD_VARIABLES}

    def test_reuses_team_sql_with_psql_variables(self):
        sql = bootstrap_sql(self.passwords)
        self.assertIn("CREATE ROLE transaction_user", sql)
        self.assertIn("CREATE ROLE audit_migrator", sql)
        self.assertIn("GRANT SELECT, INSERT ON TABLES TO audit_user", sql)
        self.assertEqual(sql.count("\\set "), len(PASSWORD_VARIABLES))
        self.assertNotIn("DROP ROLE", sql)

    def test_rejects_missing_password(self):
        del self.passwords["audit_migrator_pwd"]
        with self.assertRaisesRegex(ValueError, "exactly"):
            bootstrap_sql(self.passwords)

    def test_rejects_extra_password_variable(self):
        self.passwords["injected_variable"] = "a" * 48
        with self.assertRaisesRegex(ValueError, "exactly"):
            bootstrap_sql(self.passwords)

    def test_rejects_sql_injection_or_weak_fixture_values(self):
        for value in ("abc", "x" * 48, "a" * 47 + "'", "a" * 48 + "\n\\q"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "hex"):
                bootstrap_sql(self.passwords | {"transaction_pwd": value})


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.apps = "fintech-smoke-012345abcdef"
        self.data = "fintech-smoke-abcdef012345"
        self.items = [
            {"kind": "Deployment", "metadata": {"name": "transaction-service", "namespace": "fintech"},
             "spec": {"replicas": 2, "template": {"spec": {"containers": [{"image": "original"}]}}}},
            {"kind": "Service", "metadata": {"name": "transaction-service", "namespace": "fintech"}},
            {"kind": "ConfigMap", "metadata": {"name": "transaction-service-config-hash", "namespace": "fintech"},
             "data": {"MANAGEMENT_ENDPOINT_HEALTH_GROUP_READINESS_INCLUDE": "readinessState,db"}},
            {"kind": "Deployment", "metadata": {"name": "audit-service", "namespace": "fintech"}},
        ]

    def test_only_transaction_is_selected_and_original_is_untouched(self):
        before = copy.deepcopy(self.items)
        items = transaction_resources(self.items, self.apps, self.data, "transaction:test")
        self.assertEqual(self.items, before)
        self.assertEqual(len(items), 3)
        self.assertTrue(all(i["metadata"]["namespace"] == self.apps for i in items))
        config = next(i for i in items if i["kind"] == "ConfigMap")["data"]
        self.assertIn("postgres." + self.data + ".svc.cluster.local", config["DB_URL"])
        self.assertEqual(config["RABBITMQ_HOST"], "rabbitmq." + self.data + ".svc.cluster.local")
        self.assertEqual(config["MANAGEMENT_ENDPOINT_HEALTH_GROUP_READINESS_INCLUDE"], "readinessState,db")
        deployment = next(i for i in items if i["kind"] == "Deployment")
        self.assertEqual(deployment["spec"]["replicas"], 1)
        self.assertEqual(deployment["spec"]["template"]["spec"]["containers"][0]["image"], "transaction:test")

    def test_shared_or_same_namespaces_are_rejected(self):
        for apps, data in (("fintech", self.data), (self.apps, "data"), (self.apps, self.apps)):
            with self.subTest(apps=apps, data=data), self.assertRaises(ValueError):
                transaction_resources(self.items, apps, data, "transaction:test")

    def test_missing_transaction_config_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "only Transaction"):
            transaction_resources(self.items[:2], self.apps, self.data, "transaction:test")

    def test_secret_documents_are_runtime_only_and_namespaced(self):
        value = secret(self.apps, "transaction-service-db", {"username": "transaction_user", "password": "fixture"})
        self.assertEqual(value["kind"], "Secret")
        self.assertEqual(value["metadata"], {"namespace": self.apps, "name": "transaction-service-db"})
        self.assertEqual(value["stringData"]["username"], "transaction_user")


class PolicyTests(unittest.TestCase):
    def test_incomplete_data_tier_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "two StatefulSets"):
            validate_data([])

    def test_plaintext_secret_cannot_enter_the_base(self):
        items = [{"kind": "Secret", "metadata": {"name": str(i), "namespace": "data"}} for i in range(7)]
        with self.assertRaisesRegex(ValueError, "plaintext Secrets"):
            validate_data(items)


class BrokerClientTests(unittest.TestCase):
    @patch("kubernetes_data_smoke.urlopen")
    def test_basic_auth_is_in_header_not_url_and_json_is_structured(self, mocked):
        response = io.BytesIO(b'{"routed":true}')
        mocked.return_value = response
        body = rabbit_request("http://127.0.0.1:1234", "fixture-password", "/api/test", "POST", {"durable": True})
        request = mocked.call_args.args[0]
        self.assertNotIn("fixture-password", request.full_url)
        self.assertTrue(request.get_header("Authorization").startswith("Basic "))
        self.assertEqual(json.loads(request.data), {"durable": True})
        self.assertEqual(body, {"routed": True})


if __name__ == "__main__":
    unittest.main()
