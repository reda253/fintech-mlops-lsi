"""Policy regression checks; real rendered resources are checked separately on kind."""

import copy
import json
import unittest

from check_kubernetes_manifests import decode_objects, validate
from kubernetes_kind_smoke import can_cleanup, OWNER_LABEL, smoke_resources


class JsonTests(unittest.TestCase):
    def test_accepts_consecutive_kubectl_documents(self):
        first = {"kind": "ConfigMap", "metadata": {"name": "one"}}
        second = {"kind": "Service", "metadata": {"name": "two"}}
        self.assertEqual(decode_objects(json.dumps(first) + "\n" + json.dumps(second)), [first, second])

    def test_flattens_kubernetes_list(self):
        self.assertEqual(decode_objects('{"kind":"List","items":[{"kind":"Service"}]}'), [{"kind": "Service"}])

    def test_rejects_trailing_non_json(self):
        with self.assertRaises(json.JSONDecodeError):
            decode_objects('{"kind":"Service"} unexpected')


class PolicyTests(unittest.TestCase):
    def test_empty_application_set_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "eight Deployments"):
            validate([])

    def test_plaintext_secret_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no Secrets"):
            validate([{"kind": "Secret", "metadata": {"name": "bad", "namespace": "fintech"}}])

    def test_data_workloads_are_out_of_scope(self):
        with self.assertRaisesRegex(ValueError, "data stores"):
            validate([{"kind": "StatefulSet", "metadata": {"name": "postgres", "namespace": "fintech"}}])

    def test_other_namespaces_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unexpected namespace"):
            validate([{"kind": "ConfigMap", "metadata": {"name": "bad", "namespace": "data"}}])

    def test_duplicate_resource_identity_is_rejected(self):
        item = {"kind": "ConfigMap", "metadata": {"name": "bad", "namespace": "fintech"}}
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate([item, item])


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.namespace = "fintech-smoke-012345abcdef"
        self.items = []
        for name in ("frontend", "api-gateway"):
            for kind in ("Deployment", "Service", "ConfigMap"):
                resource_name = name + "-config-abcd" if kind == "ConfigMap" else name
                self.items.append({"kind": kind, "metadata": {"name": resource_name, "namespace": "fintech"},
                                   "data": {}, "spec": {"replicas": 2, "template": {"spec": {"containers": [{"image": "original"}]}}}})

    def test_smoke_rewrites_only_private_copies(self):
        original = copy.deepcopy(self.items)
        selected = smoke_resources(self.items, self.namespace, "frontend:test", "gateway:test")
        self.assertEqual(original, self.items)
        self.assertTrue(all(item["metadata"]["namespace"] == self.namespace for item in selected))
        configs = [item for item in selected if item["kind"] == "ConfigMap"]
        self.assertEqual(configs[0]["data"]["GATEWAY_UPSTREAM"],
                         f"http://api-gateway.{self.namespace}.svc.cluster.local:8080")
        deployments = [item for item in selected if item["kind"] == "Deployment"]
        self.assertEqual([d["spec"]["replicas"] for d in deployments], [1, 1])
        self.assertEqual([d["spec"]["template"]["spec"]["containers"][0]["image"] for d in deployments],
                         ["frontend:test", "gateway:test"])

    def test_shared_namespace_cannot_be_used_for_smoke(self):
        for namespace in ("fintech", "data", "ml", "default", "fintech-smoke-not-a-run"):
            with self.subTest(namespace=namespace), self.assertRaisesRegex(ValueError, "Unsafe"):
                smoke_resources(self.items, namespace, "frontend:test", "gateway:test")

    def test_missing_workload_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "two application"):
            smoke_resources(self.items[:-1], self.namespace, "frontend:test", "gateway:test")

    def test_cleanup_requires_exact_namespace_and_owner(self):
        metadata = {"name": self.namespace, "labels": {OWNER_LABEL: "run-owner"}}
        self.assertTrue(can_cleanup(self.namespace, metadata, "run-owner"))
        self.assertFalse(can_cleanup(self.namespace, metadata, "another-run"))
        self.assertFalse(can_cleanup("fintech", metadata, "run-owner"))
        self.assertFalse(can_cleanup(self.namespace, {"name": self.namespace}, "run-owner"))


if __name__ == "__main__":
    unittest.main()
