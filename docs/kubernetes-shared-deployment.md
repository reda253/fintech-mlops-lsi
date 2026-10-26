# Protected local release and first shared deployment

## Scope

This lot turns the existing application/data bases into an explicit first-install
procedure for local kind. It does not silently apply manifests to shared data.
It prepares nine locally built images (seven Java, frontend, PostgreSQL), ten
generated Secrets, the schema bootstrap and the eight application Deployments.
RabbitMQ remains the upstream digest-pinned image from the data base.

This is not Argo CD, Sealed Secrets, image publication or a production release
system. The committed demo/data bases retain their placeholders: real image pins
live in a reviewed local release bundle. GitOps conversion remains #40 work.
MLflow, ml-service, the pipeline and monitoring keep their separate deployment
ownership. No ML workload is installed by this tool.

The application frontend is still built in demo/MSW mode. Auth signing and
customer HMAC consumers are not yet implemented in the service scaffolds.
Ready probes and anonymous HTTP 401 do not prove real JWT login, payment
processing, outbox delivery, ML predictions or high availability.

## Private Release Bundle

`kubernetes_release.py prepare` exports a committed Git tree, not your dirty
working directory. Before every build the snapshot is compared against that
commit using a separate temporary Git index. Unexpected files are refused.
Docker receives only the relevant source subdirectory, never credentials.json.

The bundle directory must not exist and must be outside any Git checkout.
On Windows its inherited ACL is removed and full access granted only to the
current user and SYSTEM. On Unix the directory is mode 0700 and JSON files are
0600. The directory contains:

- `source/`: committed build and SQL sources, without .git.
- `credentials.json`: eleven independent generated 192-bit passwords. Never
  display, commit, attach, upload or send this file.
- `apps.json` / `data.json`: public resource manifests with full commit image tags.
- `release.json`: commit, cluster/namespace UIDs, hashes and Docker image IDs.
- `stages.json`: local progress receipts; SQL has its own authoritative marker.

The source label is `org.opencontainers.image.revision`. Builds never overwrite
an existing SHA tag without that matching label. Existing correctly labelled
images can be reused, and their IDs are recorded. A replaced image tag, changed
manifest, changed credentials file, recreated namespace or recreated cluster
causes refusal. These checks do not replace signed registry artifacts or fully
pinned builder/base images. Always load this release's images into kind before
installing it; do not rely on an old node image cache with a reused SHA tag.

Never regenerate credentials to recover a partial install. Keep this directory
private and backed up securely; ordinary shared Kubernetes Secret values are not
read back by the tool. Secret creation uses stdin, not passwords in argv, and
does not create last-applied annotations containing secret data. GitHub Actions
masks generated values defensively and never uploads the bundle as an artifact.

## Prepare And Review (Windows CMD)

Start from a reviewed, committed version containing the Kubernetes bases. Needs
Python 3.12+, Git, Docker Desktop, kind and kubectl. The existing context must be
`kind-<cluster-name>`; `data` and `fintech` namespaces must already exist.

```cmd
git status --short
set "RELEASE_DIR=%LOCALAPPDATA%\fintech-env\shared-release-01"
python -B deploy/bootstrap/kubernetes_release.py prepare --context kind-fintech --bundle "%RELEASE_DIR%"
python -B deploy/bootstrap/kubernetes_release.py build --bundle "%RELEASE_DIR%"
python -B deploy/bootstrap/kubernetes_release.py plan --bundle "%RELEASE_DIR%"
python -B deploy/bootstrap/kubernetes_release.py load-images --bundle "%RELEASE_DIR%"
```

Preparation and plan do not change Kubernetes resources. Building adds local
Docker images and runs the existing Maven/frontend tests in Docker. Only brief
registry DNS/TLS/socket failures can retry (three attempts); test/build failures
are not ignored or retried. Loading images changes only kind's image store.
The plan performs strict image/UID checks and server-side dry-run, not credential
provisioning. The bundle's manifests can be reviewed locally without opening its
credentials file. Use a new directory name for another proposed release.

Do not immediately run the installation commands below just because plan passed.
Review them with the team, confirm the target namespaces are correct and fresh,
and preserve a backup of any existing data. The tool is a first-install helper,
not an upgrade/rotation/disaster-recovery tool.

## Explicit Mutating Stages

The first stage refuses unowned data workloads, pods, retained PVCs, Secrets or
colliding resource names. It never adopts an existing database or deletes a PVC.
It creates the PostgreSQL administrator Secret and a separate broker administrator
Secret in `data`, then waits for the two StatefulSets. Pods/claims belong to the
release's random ownership identity. Normal reruns of this same bundle can resume
owned resources; another bundle cannot take them over.

```cmd
python -B deploy/bootstrap/kubernetes_shared_deploy.py data --bundle "%RELEASE_DIR%" --confirm-first-install
python -B deploy/bootstrap/kubernetes_shared_deploy.py bootstrap --bundle "%RELEASE_DIR%" --confirm-first-install
```

SQL initialization takes an advisory transaction lock, checks for existing
service/custom roles, non-system schemas and public tables/views/sequences,
runs P1's snapshot of 00_schemas_users.sql, and records a
marker in the same PostgreSQL transaction. On error it rolls back. A subsequent
bootstrap with this same bundle verifies the marker/password fingerprint and
schema ownership; it does not reset passwords. A different bootstrap or an
already-initialized unmarked database is refused. No DROP or password-reset
recovery is attempted.

RabbitMQ gets a separate runtime user, with no management/admin tags, and
permissions only in the default vhost. The broker administrator stays in `data`;
applications receive the runtime account in `fintech/rabbitmq-credentials`.
Existing unexpected user credentials/tags cause refusal instead of an overwrite.
Broker credentials use only loopback port-forward: environment HTTP proxies and
redirects are disabled for these authenticated requests.
The eight application Secrets include six schema-specific DB accounts and a
distinct audit_migrator credential used only by Audit Flyway. The SQL superuser
is never supplied to Java. MLflow's generated DB role is prepared, but its Secret
and Deployment are intentionally not installed here.

The common AMQP account still has configure/read/write permissions throughout
that local vhost. Per-service users, queue/topic restrictions, internal TLS and
Sealed Secrets remain follow-up security work. Tagless is not synonymous with
least privilege for all message operations.

Before the next stage, Traefik must recognize ingressClassName `traefik`, serve
entrypoint `websecure`, and the pre-provisioned `fintech/fintech-local-tls` must
cover fintech.local with a trusted local CA. The installer checks only the Secret's
existence, never reads/copies its private key, and does not issue a certificate.

```cmd
python -B deploy/bootstrap/kubernetes_shared_deploy.py apps --bundle "%RELEASE_DIR%" --confirm-first-install
python -B deploy/bootstrap/kubernetes_shared_deploy.py verify --bundle "%RELEASE_DIR%"
curl.exe --resolve fintech.local:443:127.0.0.1 -i https://fintech.local/
curl.exe --resolve fintech.local:443:127.0.0.1 -i https://fintech.local/api/v1/transactions
```

Verify is read-only against the cluster: ready replicas, expected images,
health/security checks via loopback port-forward, frontend proxy rejection,
six Flyway V1 histories and append-only audit/schema isolation privileges.
The curl commands separately validate the shared Ingress and the workstation's
certificate trust: expected frontend 200 and anonymous API 401, never `-k`.
The private test does not claim this shared HTTPS path has already been tested.

Every mutating CLI stage requires its confirmation flag and a private operation
lock. On failure, owned resources and data are retained for inspection. There is
no reset/cleanup command for shared namespaces. If a process is killed outright,
inspect the stage and ensure no installer process remains before removing a
stale .operation.lock; never delete a live lock or recreate credentials.

## Isolated Full Installer Test

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_kubernetes_release.py
python -B deploy/bootstrap/kubernetes_shared_smoke.py --cluster fintech
```

The smoke test creates two random labelled namespaces, builds/reuses the nine
commit-labelled images, creates a private temporary bundle and exercises the same
installer functions. It reduces each app to one replica solely for CI capacity,
selects a ready data node, and skips Ingress solely in these private namespaces.
It checks repeat-safe bootstrap, refusal of changed credentials/existing schemas,
all eight applications and six migrations. Only namespaces whose exact random
names and ownership labels match this run are deleted, including their disposable
PVCs. The cluster, shared data, existing TLS and other ML/team resources are kept.
For a repeat local run only, --skip-image-load can reuse exact already-loaded images.

`.github/workflows/kubernetes-shared.yml` provides a manually triggered full test
on a separate disposable CI kind cluster. Pull requests run the focused guard
unit tests automatically; the existing individual image scans remain unchanged.
The manual workflow does not use deployment credentials or repository write access
and is not a command to deploy the real shared cluster.

## Local Evidence

On 26 October 2026, 88 DevOps unit tests passed. The full installer was tested on
kind with nine images built from committed source 91469c45c85add39bbca1a007a7aa77f0766cb66.
All eight applications became ready and all six Flyway V1 histories were checked.
The same-bundle SQL/broker bootstrap was run twice without resetting accounts;
changed credentials and attempted bootstrap over existing service schemas were
refused. A pre-existing public table also caused refusal, with no partially
created transaction role left behind. The read-only verifier checked probes,
anonymous rejection, frontend proxying and audit INSERT/SELECT without
UPDATE/DELETE/TRUNCATE.

Only disposable namespaces were used and cleaned; the shared data/fintech stack
was not initialized or deployed. Shared Ingress HTTPS, normal multi-replica
capacity and the new manual Linux CI workflow still require their own validation.
The private test deliberately uses one replica per app and omits Ingress.

References: [PostgreSQL advisory locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS),
[RabbitMQ management tags](https://www.rabbitmq.com/docs/management#access-and-permissions).
