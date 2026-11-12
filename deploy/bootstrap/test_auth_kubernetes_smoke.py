import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from auth_kubernetes_smoke import CONTEXT, SIGNING_SECRET, seal_key, signing_env, verify_login


class AuthKubernetesSmokeTests(unittest.TestCase):
    def test_auth_references_secret_not_literal(self):
        self.assertEqual({"name": "JWT_PRIVATE_KEY", "valueFrom": {
            "secretKeyRef": {"name": SIGNING_SECRET, "key": "private-key"}}}, signing_env())

    def test_sealing_uses_lab_context_strict_scope_and_stdin(self):
        namespace = "fintech-smoke-123456789abc"
        response = {
            "kind": "SealedSecret", "metadata": {"name": SIGNING_SECRET, "namespace": namespace},
            "spec": {"encryptedData": {"private-key": "ciphertext-fixture"}},
        }
        with patch("auth_kubernetes_smoke.subprocess.run",
                   return_value=SimpleNamespace(stdout=json.dumps(response))) as command:
            self.assertEqual(response, seal_key(namespace, "synthetic-key", "kubeseal"))
        args, kwargs = command.call_args
        self.assertEqual(["kubeseal", "--context", CONTEXT, "--scope", "strict", "--format", "json"], args[0])
        self.assertEqual({"private-key": "synthetic-key"}, json.loads(kwargs["input"])["stringData"])
        self.assertTrue(kwargs["capture_output"])

    def test_sealing_refuses_wrong_namespace(self):
        response = {"kind": "SealedSecret", "metadata": {"name": SIGNING_SECRET, "namespace": "fintech"}}
        with patch("auth_kubernetes_smoke.subprocess.run",
                   return_value=SimpleNamespace(stdout=json.dumps(response))):
            with self.assertRaisesRegex(ValueError, "sealing output"):
                seal_key("fintech-smoke-123456789abc", "synthetic-key", "kubeseal")

    def test_gateway_login_passes_token_to_protected_route(self):
        with patch("auth_kubernetes_smoke.request", side_effect=[
            (401, None), (401, None), (200, {"accessToken": "synthetic"}), (200, {"username": "admin"}),
        ]) as send:
            verify_login(1234)
        self.assertEqual("synthetic", send.call_args.kwargs["token"])

    def test_gateway_must_reject_invalid_token(self):
        with patch("auth_kubernetes_smoke.request", side_effect=[(401, None), (200, {})]):
            with self.assertRaisesRegex(ValueError, "invalid JWT"):
                verify_login(1234)
