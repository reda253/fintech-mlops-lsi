import json
from pathlib import Path
import unittest


PILOT = Path(__file__).resolve().parents[1] / "gitops/pilot"
REPO = "https://github.com/reda253/fintech-mlops-lsi.git"
TARGET = {"server": "https://kubernetes.default.svc", "namespace": "fintech-gitops-pilot"}


def read(path):
    return json.loads((PILOT / path).read_text(encoding="utf-8"))


class GitOpsPilotTests(unittest.TestCase):
    def test_application_is_manual_and_non_cascading(self):
        app = read("bootstrap/application.json")
        self.assertNotIn("finalizers", app["metadata"])
        self.assertNotIn("operation", app)
        self.assertEqual({"syncOptions": ["Prune=false", "FailOnSharedResource=true"]},
                         app["spec"]["syncPolicy"])
        self.assertEqual("fintech-pilot", app["spec"]["project"])
        self.assertEqual(TARGET, app["spec"]["destination"])
        self.assertEqual({"repoURL": REPO, "targetRevision": "main", "path": "deploy/gitops/pilot/workload"},
                         app["spec"]["source"])

    def test_project_limits_repository_destination_and_kinds(self):
        spec = read("bootstrap/project.json")["spec"]
        self.assertEqual([REPO], spec["sourceRepos"])
        self.assertEqual([TARGET], spec["destinations"])
        self.assertEqual([], spec["clusterResourceWhitelist"])
        self.assertEqual({("apps", "Deployment"), ("", "Service")},
                         {(item["group"], item["kind"]) for item in spec["namespaceResourceWhitelist"]})

    def test_only_stateless_frontend_is_referenced(self):
        workload = PILOT / "workload"
        self.assertEqual({"deployment.json", "service.json", "kustomization.yaml"},
                         {path.name for path in workload.iterdir()})
        self.assertEqual("apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n"
                         "namespace: fintech-gitops-pilot\nresources:\n  - deployment.json\n  - service.json\n",
                         (workload / "kustomization.yaml").read_text(encoding="utf-8"))
        self.assertEqual("ClusterIP", read("workload/service.json")["spec"]["type"])

    def test_frontend_image_and_container_security(self):
        pod = read("workload/deployment.json")["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])
        self.assertEqual({"kubernetes.io/arch": "amd64"}, pod["nodeSelector"])
        self.assertEqual(1, len(pod["containers"]))
        container = pod["containers"][0]
        self.assertRegex(container["image"], r"^ghcr\.io/reda253/fintech-mlops-lsi/frontend@sha256:[a-f0-9]{64}$")
        self.assertEqual("Always", container["imagePullPolicy"])
        self.assertEqual([{"name": "GATEWAY_UPSTREAM", "value": "http://127.0.0.1:9"}], container["env"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(["ALL"], container["securityContext"]["capabilities"]["drop"])
        self.assertEqual([{"name": "tmp", "emptyDir": {"medium": "Memory", "sizeLimit": "64Mi"}}], pod["volumes"])
