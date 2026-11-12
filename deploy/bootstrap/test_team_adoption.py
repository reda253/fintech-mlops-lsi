import copy
import json
import unittest

from check_kubernetes_manifests import PORTS, ROOT
from check_team_adoption import REPOSITORY, SOURCE_COMMIT, image_pins, live_summary


class TeamAdoptionTests(unittest.TestCase):
    def setUp(self):
        images = {name: f"ghcr.io/{REPOSITORY}/{name}@sha256:" + "a" * 64 for name in PORTS}
        self.inventory = {"schema": 1, "platform": "linux/amd64", "repository": REPOSITORY,
                          "commit": SOURCE_COMMIT, "images": images}
        self.apps = [{"kind": "Deployment", "metadata": {"name": name}, "spec": {
            "replicas": 1, "selector": {"matchLabels": {"app": name}},
            "template": {"spec": {"containers": [{"image": images[name]}]}}}}
            for name in PORTS]

    def test_pins_match_inventory(self):
        image_pins(self.apps, self.inventory)
        with self.assertRaisesRegex(ValueError, "reviewed"):
            image_pins(self.apps, self.inventory | {"commit": "main"})
        self.apps[0]["spec"]["template"]["spec"]["containers"][0]["image"] = "local:latest"
        with self.assertRaisesRegex(ValueError, "differs"):
            image_pins(self.apps, self.inventory)

    def test_existing_deployment_is_required_and_selector_must_match(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            live_summary(self.apps, [])
        live = copy.deepcopy(self.apps)
        live[0]["spec"]["selector"] = {}
        with self.assertRaisesRegex(ValueError, "selector differs"):
            live_summary(self.apps, live)

    def test_refuses_existing_argo_tracking(self):
        live = copy.deepcopy(self.apps)
        live[0]["metadata"]["annotations"] = {"argocd.argoproj.io/tracking-id": "other"}
        with self.assertRaisesRegex(ValueError, "already tracked"):
            live_summary(self.apps, live)

    def test_extra_resources_are_not_adopted(self):
        new = {"kind": "ConfigMap", "metadata": {"name": "new-config"}}
        extra = {"kind": "Ingress", "metadata": {"name": "ingress-test"}}
        report = live_summary(self.apps + [new], self.apps + [extra])
        self.assertIn("ConfigMap/new-config: create", report)
        self.assertIn("Ingress/ingress-test: outside candidate", report)

    def test_project_and_application_scope(self):
        folder = ROOT / "deploy/gitops/team/bootstrap"
        project = json.loads((folder / "project.json").read_text())["spec"]
        app = json.loads((folder / "application.json").read_text())
        destination = {"server": "https://kubernetes.default.svc", "namespace": "fintech"}
        self.assertEqual([destination], project["destinations"])
        self.assertEqual([], project["clusterResourceWhitelist"])
        self.assertEqual({("apps", "Deployment"), ("", "Service"), ("", "ConfigMap"),
                          ("networking.k8s.io", "Ingress")},
                         {(i["group"], i["kind"]) for i in project["namespaceResourceWhitelist"]})
        self.assertEqual(destination, app["spec"]["destination"])
        self.assertEqual("fintech-team", app["spec"]["project"])
        self.assertEqual("deploy/overlays/team-release", app["spec"]["source"]["path"])
        self.assertEqual([app["spec"]["source"]["repoURL"]], project["sourceRepos"])
        self.assertEqual({"syncOptions": ["Prune=false", "FailOnSharedResource=true"]}, app["spec"]["syncPolicy"])
        self.assertNotIn("operation", app)
        self.assertNotIn("finalizers", app["metadata"])
