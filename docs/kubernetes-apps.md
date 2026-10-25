# Kubernetes application base (issue #39)

## Scope and ownership

This batch adds the seven Java applications and the frontend, not a replacement
for the existing ML deployment work. The demo overlay composes
`deploy/k8s/apps`: eight Deployments, eight ClusterIP Services, eight generated
ConfigMaps and one standard Traefik Ingress. No Secret is stored in Git.
The existing CI-bot probe comment in the demo overlay remains supported.

The application manifests do not install PostgreSQL, RabbitMQ, MLflow,
Prometheus, Argo CD, Sealed Secrets, or their CRDs. The existing directories
`deploy/k8s/ml`, `ml-service` and `ml-pipeline` remain unchanged and are not
silently included in this overlay. In particular, MLflow's measured 3 Gi limit
is not reduced to the older architecture estimate.

Do not close #39 solely on this batch: shared data-tier integration and a full
team demonstration remain necessary. HPA, PDB and NetworkPolicy rollout are
separate work; these manifests alone do not prove high availability.

## Workloads

| Deployment | Port | Replicas | Readiness |
|---|---:|---:|---|
| api-gateway | 8080 | 2 | readinessState |
| auth-service | 8081 | 1 | readinessState + db |
| customer-service | 8082 | 1 | readinessState + db |
| transaction-service | 8083 | 2 | readinessState + db |
| risk-service | 8084 | 2 | readinessState + db |
| notification-service | 8085 | 1 | readinessState + db |
| audit-service | 8086 | 1 | readinessState + db |
| frontend | 8080 | 2 | local nginx /healthz |

Java requests are 200m/384Mi and limits 1000m/512Mi per replica; frontend
requests are 50m/64Mi and limits 200m/128Mi. Minimum application requests total
3,968 MiB (ten JVMs plus two frontend pods), before platform/data/ML costs.
These are initial budgets, not measured capacity guarantees.

All containers use UID/GID 10001, RuntimeDefault seccomp, no privilege escalation,
no capabilities, no service-account token, a read-only root and bounded writable
memory-backed /tmp. That tmpfs counts towards the container memory limit.
Startup allows 150 seconds. Liveness checks only the local process; readiness
does not include RabbitMQ or downstream HTTP services. This preserves #88's
outbox/readiness policy without claiming that the outbox business logic is tested.

Rolling updates use maxSurge=1/maxUnavailable=0, minReadySeconds=10 and five
revisions. The progress deadline is 240 seconds, deliberately longer than the
150-second startup budget (the earlier 120-second estimate was too short).
Graceful shutdown has a five-second preStop and 30-second grace period.
Node not-ready/unreachable eviction tolerations are 30 seconds; replicas are not
yet guaranteed to be spread across workers.

ConfigMaps are generated from individual public `.env` files. Kustomize's name
hash updates the Deployment reference when configuration changes, causing a
rollout. Secret changes still need an explicit rollout until a GitOps secret
rotation mechanism is introduced.

## Dependencies and credentials

The shared namespace is `fintech`. Prerequisites must be prepared by their owners:

- PostgreSQL is reachable as `postgres.data.svc.cluster.local:5432`, database
  `fintech`; service roles, schema ownership/search_path and audit append-only
  grants follow `deploy/sql/00_schemas_users.sql`. Never rerun its CREATE ROLE
  statements blindly against an initialized database.
- RabbitMQ is reachable as `rabbitmq.data.svc.cluster.local:5672`; credentials
  must be authorized for the configured vhost.
- Each of auth/customer/transaction/risk/notification/audit has a Secret named
  `<service>-db` with keys `username` and `password`, matching its own runtime role.
- `audit-migrator-db` has `username`/`password` for audit_migrator, separate from
  audit_user. Only audit-service receives the Flyway credentials.
- `rabbitmq-credentials` has `username`/`password`. It is referenced only by
  auth, transaction, risk, notification and audit, not customer or Gateway.
- Traefik recognizes ingressClassName `traefik` and entrypoint `websecure`.
  `fintech-local-tls` exists in `fintech` and covers `fintech.local`; the workstation
  trusts its local CA and resolves that hostname to kind's exposed ports.

Create credentials from private files outside Git, never password literals in
commands/screenshots. Example CMD for one already-provisioned account:

```cmd
notepad "%LOCALAPPDATA%\fintech-env\k8s-transaction-secret.env"
kubectl --context kind-fintech -n fintech create secret generic transaction-service-db --from-env-file="%LOCALAPPDATA%\fintech-env\k8s-transaction-secret.env"
```

The private file contains `username=transaction_user` and `password=` followed by
the real account password. Do not create this example in the repository. Repeat
with each actual role only after provisioning it. No dummy/default password is
inserted into the application ConfigMaps. Sealed Secrets integration is deferred
to #40; base64-encoded Secret YAML must not be committed either.

Auth signing keys and customer HMAC provisioning are not wired here because the
current scaffolds do not expose their final consumers yet. Agree those contracts
with P1 before enabling real authentication/payment flows.

## Ingress and frontend DNS

HTTPS `fintech.local/` routes to frontend and `/api` to api-gateway, preserving the
request path. There is no public Ingress to PostgreSQL, RabbitMQ, internal Java
services or `/predict`. No global retry middleware is added before the business
idempotency contract is verified. Traefik/SSE end-to-end behavior remains to test.

The frontend now derives a validated IPv4 resolver from `/etc/resolv.conf`:
Docker's resolver under Compose, CoreDNS under Kubernetes. The nginx asynchronous
proxy resolver cannot use a hard-coded Docker-only 127.0.0.11 in Kubernetes.
The upstream uses a fully qualified Service name because nginx's asynchronous
resolver does not expand the pod's DNS search domains. IPv6-only clusters are not
supported by this entrypoint; startup fails clearly if no IPv4 resolver exists.

The browser bundle remains demo/MSW mode. Runtime ConfigMaps cannot change Vite
build-time flags. Successful HTTP 401 checks prove rejection of anonymous traffic,
not working JWT login, business endpoints or actual payment processing.

## Validation from Windows CMD

Requires Python 3, kubectl, kind and Docker Desktop. The existing cluster must
already exist; these scripts never recreate/delete the shared cluster.

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_kubernetes_manifests.py
python -B deploy/bootstrap/check_kubernetes_manifests.py --context kind-fintech --allow-placeholder
docker build -t fintech-frontend:k8s-test frontend
docker build -f services/api-gateway/Dockerfile -t fintech-api-gateway:k8s-test services
python -B deploy/bootstrap/kubernetes_kind_smoke.py --cluster fintech --frontend-image fintech-frontend:k8s-test --gateway-image fintech-api-gateway:k8s-test
```

The checker renders with kubectl Kustomize, checks application policies, rejects
eight intentionally unsafe mutations, then performs API-server schema validation
with server-side dry-run. It does not read any Secret values or change resources.

The smoke test loads only the two named Docker images into kind, creates a random
`fintech-smoke-<12 hex>` namespace, runs one real Gateway/frontend replica and
checks UID, probes, SPA/assets and anonymous Bearer HTTP 401 through the frontend
proxy and CoreDNS. It uses localhost-only port-forward, not public Ingress/TLS.
Cleanup deletes only the namespace whose exact name and ownership label match
this run. Other namespaces, PVCs and Compose containers are never cleaned up.
Interruptions that kill Python outright may leave a labelled smoke namespace;
inspect its ownership before any manual deletion.

CI repeats schema/policy validation and the real smoke test in its own disposable
single-node kind cluster, after the frontend Compose/browser tests. The shared
local cluster remains three nodes; this small CI fixture is not an HA test.
CI pins kind 0.33.0, the Kubernetes 1.37.0 node image by digest, and kubectl 1.37.0.

Local evidence on 25 October 2026: 55 DevOps unit tests and 31 frontend tests
passed; all 25 application resources passed server-side dry-run; eight unsafe
policy mutations were rejected. Real Gateway/frontend pods passed the isolated
kind smoke (including CoreDNS proxy and Bearer 401), and the existing Compose
smoke still passed (including SSE and Gateway-stub outage/recovery). Test resources
were removed. The new GitHub Actions steps still require their first remote run.

## Shared deployment gate

Images intentionally use `REPLACE_WITH_COMMIT_SHA` until reviewed images are
built and available. Do not apply this unconfigured overlay as a working stack.
Add all eight image entries in the demo overlay's `images` list using a full
40-character application commit SHA (or a digest), for example:

```yaml
images:
  - name: fintech-api-gateway
    newTag: FULL_40_CHARACTER_APPLICATION_COMMIT_SHA
  - name: fintech-frontend
    newTag: FULL_40_CHARACTER_APPLICATION_COMMIT_SHA
```

Repeat for the other six Java images. Build/publish those exact images first, or
load them into the correct kind cluster with `kind load docker-image --name fintech`.
There is no registry publication job in this batch. Never substitute latest/dev.
After dependencies, credentials, TLS and image tags are ready, the following
checker must pass WITHOUT `--allow-placeholder` before applying anything:

```cmd
python -B deploy/bootstrap/check_kubernetes_manifests.py --context kind-fintech
kubectl --context kind-fintech diff -k deploy/overlays/demo
kubectl --context kind-fintech apply -k deploy/overlays/demo
kubectl --context kind-fintech -n fintech get deployments,pods,services,ingress
curl.exe --resolve fintech.local:443:127.0.0.1 -i https://fintech.local/
curl.exe --resolve fintech.local:443:127.0.0.1 -i https://fintech.local/api/v1/transactions
```

`kubectl diff` returns 1 when differences exist. Review those differences before
apply; do not use a shell chain that ignores errors. Expected anonymous API
response is 401, never a fake SPA 200. Full six-service database startup,
Ingress TLS and actual business flows remain pending a shared-stack validation.
Do not disable authentication or remove probes to force readiness green.

References: [Kustomize generators](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/),
[Deployment progress deadlines](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/),
[nginx variable proxy DNS](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass),
[kind image loading](https://kind.sigs.k8s.io/docs/user/quick-start/#loading-an-image-into-your-cluster).
