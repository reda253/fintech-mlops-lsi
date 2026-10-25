# Kubernetes data tier and Transaction integration (#39)

## What is included

`deploy/k8s/data` is a separate Kustomize base, not automatically applied by the
application demo overlay. It defines two single-replica StatefulSets, two
headless identity Services, two client ClusterIP Services and a generated
RabbitMQ ConfigMap. The namespace `data` must already exist.

| Workload | Image | Identity | PVC | Requests / limits |
|---|---|---|---|---|
| postgres | fintech-postgres built from digest-pinned PostgreSQL 17 Alpine | UID/GID 70 | 5Gi | 250m/512Mi, 1000m/1Gi |
| rabbitmq | RabbitMQ 4.3.6 management Alpine, digest pinned | UID 100/GID 101 | 1Gi | 200m/384Mi, 500m/512Mi |

The PostgreSQL derived image removes the unused `/usr/local/bin/gosu` helper.
The selected official base embeds Go 1.24.6 in that executable, and the local
critical gate identified CVE-2025-68121. PostgreSQL runs directly as its existing
non-root account and does not need a root-to-user helper. No vulnerability
exception or global scan suppression is introduced. Do not run this derived
image as root: its root entrypoint path intentionally cannot call gosu.

The PostgreSQL application image must be tagged with a full reviewed commit SHA
before shared deployment. The source Dockerfile pins its official base digest.
RabbitMQ remains an upstream image pinned by digest. Version changes require
reviewing both manifests and the CI image-scan references.

RabbitMQ 4.3 is selected for a fresh Kubernetes database, not as an in-place
upgrade of the existing Compose 3.13 broker. PostgreSQL 17 also creates a fresh
database; no existing PostgreSQL 16 Docker volume is mounted or upgraded.
Do not attach old broker/database volumes to these images without a separately
reviewed backup, compatibility and migration plan.

## Storage and placement

Both data pods select `fintech-worker` via `kubernetes.io/hostname`. Verify that
node exists and is Ready. A differently named shared cluster needs a reviewed
nodeSelector patch. The private CI test selects a ready node in its own cluster
instead of assuming that hostname exists.

PVC templates omit storageClassName to use the cluster default (`standard` in
the tested kind installation). Do not set a guessed `local-path` class name.
ReadWriteOnce volumes are local to their provisioned node. Retention policy is
Retain on both StatefulSet deletion and scale-down. Scaling to zero and back
reuses the same named claims and data.

**Retention is not a backup.** Deleting a PVC or its namespace can still destroy
its backing storage under the default reclaim policy. Never delete namespace
`data`, delete its PVCs, or run a shared-cluster cleanup to reset this setup.
There is only one instance of each data service: a pod/node outage interrupts it.
No high availability or node-failure recovery guarantee is implied.

Data containers have no API token, use RuntimeDefault seccomp, drop capabilities
and run with a read-only root. PostgreSQL has separate bounded writable socket,
temporary and shared-memory mounts. Persistent data uses PVCs, never a shared
hostPath. fsGroupChangePolicy OnRootMismatch avoids repeatedly changing the
RabbitMQ cookie permissions when an existing volume is remounted.

RabbitMQ's server and diagnostic CLI have explicit small scheduler counts.
Repeated diagnostic-CLI probes exceeded their time budget under the 500m CPU
limit and caused restart loops during testing. Kubernetes therefore probes the
local AMQP TCP listener without spawning extra Erlang VMs. This is a listener
availability check, not proof of message processing; the separate authenticated
publish/persistence tests cover that stronger contract. PostgreSQL uses local
pg_isready probes. No probe depends on an application. Image download/startup can take
several minutes. No public NodePort, host port or Ingress exposes either service.

## Secrets and first initialization

No Secret YAML, default password or real credential is committed. The shared
deployment needs these Secrets created securely in `data`:

- `postgres-admin`: key `password`; SQL superuser is `postgres`, database `fintech`.
  Its password is consumed from a read-only Secret file, not a command argument.
- `rabbitmq-credentials`: keys `username` and `password`, used to initialize the
  broker on a fresh data directory. Use a named account, never remote guest access.

These initialization settings do not rotate passwords stored in an existing
database/broker. Editing a Secret alone does not update those stored accounts.
Plan actual server-side credential rotation and application rollout separately.

The broker's default seeded account has administrative privileges. Its use is
limited to this local development/bootstrap design. Before deploying the full
shared application, provision separate least-privilege AMQP runtime users and
place their credentials in the `fintech/rabbitmq-credentials` Secret. Do not copy
broker administrator credentials into application pods. Broker TLS, dedicated
users/vhosts and sealed credential delivery remain follow-up work.

PostgreSQL starts without service schemas. P1's existing
`deploy/sql/00_schemas_users.sql` is the schema/role contract. Run it only on a
new database with all eight password variables supplied securely via stdin or
mounted private input, never password literals in CLI arguments or screenshots.
It creates separate schema owners and the distinct audit_migrator/audit_user
roles; do not replace it with a shared superuser account for applications.
Do not rerun its CREATE ROLE statements against an initialized database.

This batch runs that bootstrap automatically only in private disposable tests.
It does not automatically initialize or alter a shared database. Shared bootstrap
and delivery of per-service Secrets must be coordinated with P1 and #40.

## Shared deployment checklist

First review the existing state, storage class, node placement and external
credential inputs. CMD examples (do not print the contents of private files):

```cmd
kubectl --context kind-fintech -n data get statefulsets,pvc,services
kubectl --context kind-fintech get storageclass
kubectl --context kind-fintech get node fintech-worker
```

Stop if this reveals an existing database/broker: do not overwrite it. For an
agreed fresh deployment only, prepare private files outside Git and create the
initialization Secrets. For example the admin env file has one key `password`,
and the broker env file has `username`/`password`:

```cmd
notepad "%LOCALAPPDATA%\fintech-env\k8s-postgres-admin.env"
notepad "%LOCALAPPDATA%\fintech-env\k8s-rabbitmq.env"
kubectl --context kind-fintech -n data create secret generic postgres-admin --from-env-file="%LOCALAPPDATA%\fintech-env\k8s-postgres-admin.env"
kubectl --context kind-fintech -n data create secret generic rabbitmq-credentials --from-env-file="%LOCALAPPDATA%\fintech-env\k8s-rabbitmq.env"
```

Build and load the reviewed PostgreSQL image on the selected kind node. Registry
publication is not provided here; renaming the repository also requires reviewing
the image policy checker. Add an `images` override in the data Kustomization
with `name: fintech-postgres` and `newTag:` equal to its full application commit
SHA. The default placeholder intentionally cannot pass the deployment gate.

```cmd
python -B deploy/bootstrap/check_kubernetes_data.py --context kind-fintech
kubectl --context kind-fintech diff -k deploy/k8s/data
kubectl --context kind-fintech apply -k deploy/k8s/data
kubectl --context kind-fintech -n data get pods,pvc,services
```

Review diff output (exit code 1 means differences), provision schemas/runtime
users securely, and only then complete the application deployment procedure in
`docs/kubernetes-apps.md`. Do not remove probes, use admin DB credentials in Java,
or delete storage just to make readiness green.

## Reproducible private test (CMD)

Requires Docker Desktop, Python 3, kind, kubectl, a running kind cluster and
registry access from the kind node. It does not recreate or remove your cluster.

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_kubernetes_data.py
python -B deploy/bootstrap/check_kubernetes_data.py --context kind-fintech --allow-placeholder
docker build -t fintech-postgres:k8s-data-test deploy/images/postgres
docker build -f services/transaction-service/Dockerfile -t fintech-transaction-service:k8s-data-test services
python -B deploy/bootstrap/kubernetes_data_smoke.py --cluster fintech --transaction-image fintech-transaction-service:k8s-data-test --postgres-image fintech-postgres:k8s-data-test
```

The test checks actual manifests before creating two random namespaces with
ownership labels. Generated 192-bit passwords are passed through private API
request bodies/stdin, never CLI arguments. GitHub Actions masks them defensively.
No developer credential file or shared Secret value is read.

The test is intended to verify:

- The repository schema bootstrap, no transaction-to-auth schema access, and
  audit INSERT/SELECT privileges without UPDATE/DELETE.
- Real Transaction Flyway V1, UID 10001, correlation IDs, readiness/liveness and
  rejection of anonymous requests by the existing HTTP security checks.
- Durable RabbitMQ queue/message creation through its loopback-forwarded API.
- RabbitMQ scale-to-zero leaves Transaction readiness UP for a 20-second window.
- PostgreSQL scale-to-zero leaves liveness UP but makes readiness DOWN; restoring
  the same StatefulSet brings readiness back UP.
- The same PVC UIDs, a retained SQL row and a durable RabbitMQ message after both
  data pods have been recreated.

Cleanup verifies both the exact random namespace name and the current run's
ownership label before deleting a namespace. This intentionally deletes ONLY
the test namespaces and their disposable PVCs. Shared `fintech`, `data` and `ml`
are never reset. An outright process kill can leave labelled test namespaces;
inspect ownership before considering manual cleanup.

For repeated local checks only, `--skip-image-load` avoids reimporting the two
application images when those exact tags already exist on every kind node.
Normal first runs and CI do not skip loading. The pinned RabbitMQ image is pulled
by kubelet, avoiding incomplete multiarchitecture Docker Desktop export indexes.

This is an infrastructure/security/persistence test, not proof of transaction
business processing, outbox publishing, consumer deduplication, end-to-end JWT,
data-tier HA, or zero data loss during arbitrary crashes. The outages are graceful
scale-downs, not forced node failures. StatefulSet/PVC backups are still required.
CI runs the same test on its own disposable single-node cluster and scans both
data images with the critical/unfixed gate enabled.

## Validation evidence and limits

On 25 October 2026, 66 DevOps unit tests passed and all seven data-tier resources
passed API-server dry-run plus three unsafe-policy mutation checks. A private
integration run verified schema grants, Flyway V1, probes, anonymous rejection,
both dependency outages, identical PVC UIDs, the retained SQL row and durable
RabbitMQ message. The final run used the retained TCP probe configuration and
cleaned both namespaces successfully. No shared database was initialized or modified.

Local archive scans with Trivy 0.70.0 and the current vulnerability database
reported zero CRITICAL findings for the derived PostgreSQL image and pinned
RabbitMQ image, with ignore-unfixed=false. The original PostgreSQL base failed
before removal of the unused gosu binary. These are severity-filtered results,
not a claim that no lower-severity vulnerabilities exist.

Residual scanner warnings remain: Alpine 3.24 was absent from that scanner's
EOL list, and the database had no details for CVE-2026-107891. No warning was
suppressed, and missing details are not treated as evidence that a CVE is harmless.
Review scanner/database upgrades separately. New GitHub Actions steps still need
their first remote run; the composite tool installer is YAML-validated locally,
not executed as Linux CI on this Windows workstation.

References: [PostgreSQL image behavior](https://hub.docker.com/_/postgres),
[RabbitMQ supported releases](https://www.rabbitmq.com/release-information),
[RabbitMQ upgrade prerequisites](https://www.rabbitmq.com/docs/upgrade),
[StatefulSet PVC retention](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/#persistentvolumeclaim-retention).
