import unittest

from verify_java_image import verify_config, verify_identity


class ImageContractTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "User": "10001:10001",
            "WorkingDir": "/app",
            "Entrypoint": ["java", "-jar", "application.jar"],
            "ExposedPorts": {"8081/tcp": {}},
            "Env": ["JAVA_TOOL_OPTIONS=-XX:MaxRAMPercentage=70"],
        }

    def test_expected_image_contract(self):
        verify_config(self.config, 8081)

    def test_root_user_is_rejected(self):
        self.config["User"] = "0"
        with self.assertRaisesRegex(AssertionError, "USER"):
            verify_config(self.config, 8081)

    def test_wrong_entrypoint_is_rejected(self):
        self.config["Entrypoint"] = ["sh"]
        with self.assertRaisesRegex(AssertionError, "entrypoint"):
            verify_config(self.config, 8081)

    def test_wrong_workdir_is_rejected(self):
        self.config["WorkingDir"] = "/"
        with self.assertRaisesRegex(AssertionError, "directory"):
            verify_config(self.config, 8081)

    def test_wrong_port_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, "8084"):
            verify_config(self.config, 8084)

    def test_missing_ports_are_rejected(self):
        self.config["ExposedPorts"] = None
        with self.assertRaisesRegex(AssertionError, "port"):
            verify_config(self.config, 8081)

    def test_missing_heap_option_is_rejected(self):
        self.config["Env"] = []
        with self.assertRaisesRegex(AssertionError, "heap"):
            verify_config(self.config, 8081)

    def test_baked_runtime_secrets_are_rejected(self):
        for name in ("DB_PASSWORD", "FLYWAY_PASSWORD", "RABBITMQ_PASSWORD", "JWT_PRIVATE_KEY"):
            with self.subTest(name=name):
                self.config["Env"] = ["JAVA_TOOL_OPTIONS=-XX:MaxRAMPercentage=70", name + "=placeholder"]
                with self.assertRaisesRegex(AssertionError, name):
                    verify_config(self.config, 8081)

    def test_actual_unprivileged_identity(self):
        verify_identity("uid=10001(fintech) gid=10001(fintech) groups=10001(fintech)")

    def test_root_and_wrong_identity_are_rejected(self):
        for identity in ("uid=0(root) gid=0(root)", "uid=100010 gid=100010", "uid=10001 gid=0", ""):
            with self.subTest(identity=identity):
                with self.assertRaisesRegex(AssertionError, "UID/GID"):
                    verify_identity(identity)


if __name__ == "__main__":
    unittest.main()
