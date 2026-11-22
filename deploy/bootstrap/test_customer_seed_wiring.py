import copy
import unittest

from check_kubernetes_manifests import SPARKOV_PATHS, customer_seed_storage


class CustomerSeedTests(unittest.TestCase):
    def setUp(self):
        self.pod = {
            "nodeSelector": {"fintech.local/sparkov": "true"},
            "volumes": [
                {"name": "tmp", "emptyDir": {"medium": "Memory", "sizeLimit": "128Mi"}},
                {"name": "sparkov", "hostPath": {"path": "/data/sparkov", "type": "Directory"}},
            ],
        }
        self.app = {"volumeMounts": [
            {"name": "tmp", "mountPath": "/tmp"},
            {"name": "sparkov", "mountPath": "/data/sparkov", "readOnly": True},
        ]}
        self.config = {"CUSTOMER_SEED_PATH": SPARKOV_PATHS}

    def test_readonly_mount_to_verified_node(self):
        customer_seed_storage(self.pod, self.app, self.config)

    def test_writable_or_missing_readonly_rejected(self):
        for value in (False, None):
            app = copy.deepcopy(self.app)
            app["volumeMounts"][1]["readOnly"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "read-only"):
                customer_seed_storage(self.pod, app, self.config)

    def test_arbitrary_host_directory_rejected(self):
        self.pod["volumes"][1]["hostPath"]["path"] = "/"
        with self.assertRaisesRegex(ValueError, "existing Sparkov"):
            customer_seed_storage(self.pod, self.app, self.config)

    def test_directory_creation_rejected(self):
        self.pod["volumes"][1]["hostPath"]["type"] = "DirectoryOrCreate"
        with self.assertRaises(ValueError):
            customer_seed_storage(self.pod, self.app, self.config)

    def test_unverified_node_rejected(self):
        self.pod["nodeSelector"] = {}
        with self.assertRaisesRegex(ValueError, "verified"):
            customer_seed_storage(self.pod, self.app, self.config)

    def test_different_seed_paths_rejected(self):
        with self.assertRaisesRegex(ValueError, "seed paths"):
            customer_seed_storage(self.pod, self.app, {"CUSTOMER_SEED_PATH": "/tmp/customers.csv"})
