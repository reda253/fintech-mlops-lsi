# deploy/ — owner P4

Kustomize bases/overlays, Argo CD apps, Helm values, SealedSecrets. `deploy/sql/` holds the PostgreSQL bootstrap script (P1).

Application base and isolated kind validation: [Kubernetes applications](../docs/kubernetes-apps.md).
Existing ML manifests remain separately owned and are not replaced by the application overlay.

Separate PostgreSQL/RabbitMQ base and persistence tests: [Kubernetes data](../docs/kubernetes-data.md).

Protected local release and explicit first-install stages: [Shared deployment](../docs/kubernetes-shared-deployment.md).
