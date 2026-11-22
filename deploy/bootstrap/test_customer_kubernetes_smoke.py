import csv
from io import StringIO
import unittest
from unittest.mock import patch
from uuid import uuid4

from customer_kubernetes_smoke import CARDS, COLUMNS, CUSTOMER_IMAGE, customer_resources, synthetic_files, verify_api


class CustomerKubernetesTests(unittest.TestCase):
    def test_csv_contains_only_synthetic_customer_columns(self):
        files = synthetic_files()
        self.assertEqual({"fraudTrain.csv", "fraudTest.csv"}, set(files))
        for text in files.values():
            rows = list(csv.DictReader(StringIO(text)))
            self.assertEqual(set(COLUMNS), set(rows[0]))
            self.assertEqual("Testing, only", rows[0]["job"])
            self.assertTrue(all(row["cc_num"] in CARDS and len(row["cc_num"]) == 11 for row in rows))
            self.assertNotIn("is_fraud", rows[0])

    def test_train_test_duplicate_is_intentional(self):
        cards = [row["cc_num"] for text in synthetic_files().values() for row in csv.DictReader(StringIO(text))]
        self.assertEqual(3, len(cards))
        self.assertEqual(2, len(set(cards)))

    def test_resources_mount_fixture_readonly_without_hostpath(self):
        items = [
            {"kind": "Deployment", "metadata": {"name": "customer-service"}, "spec": {
                "template": {"spec": {"containers": [{"volumeMounts": []}], "volumes": []}}}},
            {"kind": "Service", "metadata": {"name": "customer-service"}},
            {"kind": "ConfigMap", "metadata": {"name": "customer-service-config-fixture"}, "data": {}},
        ]
        result = customer_resources(items, "fintech-smoke-fixture")
        pod = result[0]["spec"]["template"]["spec"]
        self.assertEqual(CUSTOMER_IMAGE, pod["containers"][0]["image"])
        self.assertTrue(pod["containers"][0]["volumeMounts"][0]["readOnly"])
        self.assertTrue(all("hostPath" not in volume for volume in pod["volumes"]))
        self.assertNotIn("image", items[0]["spec"]["template"]["spec"]["containers"][0])

    def test_lookup_requires_minimal_response_and_stable_identity(self):
        customer_id = str(uuid4())
        with patch("customer_kubernetes_smoke.request", side_effect=[
            (401, None), (200, {"customerId": customer_id, "cardLast4": CARDS[0][-4:]}),
            (200, {"job": "Testing, only", "dob": "1990-01-01"}), (400, None), (404, None),
        ]):
            self.assertEqual(customer_id, verify_api(1234, "synthetic-token"))

    def test_raw_card_in_lookup_is_rejected(self):
        with patch("customer_kubernetes_smoke.request", side_effect=[
            (401, None), (200, {"customerId": str(uuid4()), "cardLast4": CARDS[0][-4:], "cardNumber": CARDS[0]}),
        ]):
            with self.assertRaisesRegex(ValueError, "lookup result"):
                verify_api(1234, "synthetic-token")
