"""Unit tests validating Kubernetes monitoring manifests (Issue #49: §8.1 & §8.6)."""

from pathlib import Path
import re
import unittest


K8S_DIR = Path(__file__).resolve().parent
REPO_ROOT = K8S_DIR.parents[1]

SPRING_BOOT_SERVICES = (
    "api-gateway",
    "auth-service",
    "customer-service",
    "transaction-service",
    "risk-service",
    "notification-service",
    "audit-service",
)


class KubernetesMonitoringSpecTests(unittest.TestCase):
    def test_required_monitoring_k8s_files_exist(self):
        expected = (
            "namespace.yaml",
            "kube-prometheus-stack-values.yaml",
            "servicemonitors.yaml",
            "loki.yaml",
            "alloy.yaml",
            "kustomization.yaml",
        )
        for filename in expected:
            path = K8S_DIR / filename
            self.assertTrue(path.is_file(), f"Missing required file: {path}")

    def test_kube_prometheus_stack_values_match_section_8_1(self):
        content = (K8S_DIR / "kube-prometheus-stack-values.yaml").read_text(encoding="utf-8")
        self.assertIn("scrapeInterval: 15s", content)
        self.assertIn("evaluationInterval: 15s", content)
        self.assertIn("retention: 7d", content)
        self.assertIn("storage: 5Gi", content)
        # Resource budgets (§8.1): Prometheus 512Mi-1Gi, Grafana 128Mi, Alertmanager 64Mi
        self.assertIn("memory: 512Mi", content)
        self.assertIn("memory: 1Gi", content)
        self.assertIn("memory: 128Mi", content)
        self.assertIn("memory: 64Mi", content)
        # Security (§8.7 / D22): Grafana admin password via SealedSecret reference, no plaintext secret
        self.assertIn("existingSecret: grafana-admin-credentials", content)
        self.assertNotIn("adminPassword:", content)
        # Loki datasource and correlationId derived field
        self.assertIn("http://loki.monitoring.svc.cluster.local:3100", content)
        self.assertIn("name: correlationId", content)
        self.assertIn("grafana.fintech.local", content)

    def test_servicemonitors_cover_spring_boot_ml_and_data_targets(self):
        content = (K8S_DIR / "servicemonitors.yaml").read_text(encoding="utf-8")
        self.assertIn("kind: ServiceMonitor", content)
        self.assertIn("release: prometheus", content)
        self.assertIn("path: /actuator/prometheus", content)
        self.assertIn("path: /metrics", content)
        self.assertIn("interval: 15s", content)
        for service in SPRING_BOOT_SERVICES:
            self.assertIn(service, content, f"Missing Spring Boot service in ServiceMonitor: {service}")
        self.assertIn("ml-service", content)
        self.assertIn("rabbitmq", content)
        self.assertIn("postgres-exporter", content)
        self.assertIn("kind: Probe", content)

    def test_loki_monolithic_config_matches_section_8_6(self):
        content = (K8S_DIR / "loki.yaml").read_text(encoding="utf-8")
        self.assertIn("kind: StatefulSet", content)
        self.assertIn("retention_period: 72h", content)
        self.assertIn("storage: 5Gi", content)
        self.assertIn("memory: 256Mi", content)
        self.assertIn("memory: 512Mi", content)
        self.assertIn("runAsNonRoot: true", content)
        # Critical log alerts (§8.6): OutOfMemoryError and model loading failure
        self.assertIn("OutOfMemoryError", content)
        self.assertIn("MlModelLoadFailureInLogs", content)

    def test_alloy_daemonset_enforces_strict_loki_labels_section_8_6(self):
        content = (K8S_DIR / "alloy.yaml").read_text(encoding="utf-8")
        self.assertIn("kind: DaemonSet", content)
        self.assertIn("memory: 100Mi", content)
        self.assertIn('values = ["namespace", "app", "pod", "level"]', content)
        self.assertIn("http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push", content)
        # Verify correlationId is NEVER added inside stage.labels block (§8.6 cardinality rule)
        labels_blocks = re.findall(r"stage\.labels\s*\{([^}]*)\}", content, flags=re.DOTALL)
        self.assertTrue(labels_blocks, "Expected stage.labels block in Alloy config")
        for block in labels_blocks:
            self.assertNotIn("correlationId", block, "correlationId must not be indexed as a Loki label")


if __name__ == "__main__":
    unittest.main()
