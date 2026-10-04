# Architecture decisions

Rule (§10.7): **every new architecture decision is added here**, in the PR that implements it. D1–D32 come from the architecture document v1.0 (§2.6), where the alternatives and full justifications are listed.

| # | Decision | Rejected alternatives | Why |
|---|---|---|---|
| D1 | Sparkov dataset | ULB, PaySim, IEEE-CIS | Customers, merchants and categories map onto our services; time split already provided |
| D2 | GitHub monorepo | One repo per service | Simpler for 5 people and Argo CD; one PR can change a contract and both sides |
| D3 | Local kind cluster | Managed cloud | Free; enough for replicas, HPA, probes, rollback |
| D4 | Sync REST + RabbitMQ for notification/audit | REST only, Kafka | Takes non-critical services off the payment path; lighter than Kafka |
| D5 | One PostgreSQL instance, one schema + user per service | One DB per service | Logical isolation kept, ~1 GB RAM saved |
| D6 | JWT validated at the gateway and re-validated by each service | Service tokens, mTLS | Enough for scope; defence in depth |
| D7 | Kubernetes-native service discovery | Eureka | DNS + Services are enough |
| D8 | GitHub Actions (CI) + Argo CD (CD) | Self-hosted runner, manual deploy | Cluster never exposed; rollback via Git |
| D9 | ML pipeline = GitHub Actions + MLflow | Prefect | One less tool |
| D10 | SonarCloud | Self-hosted SonarQube | Free for public repos, no RAM cost |
| D11 | Calibration + conformal prediction (MAPIE) | Ensembles, bootstrap | Statistical coverage guarantee justifies human review |
| D12 | Three-way decision | Two-way | Certain cases automated, uncertain ones go to a human |
| D13 | Preprocessing inside the model pipeline; ml-service gets raw fields | Features computed in Java | No train/serve skew |
| D14 | In-app notifications only (stored + SSE) | Email, logs | Light, visible in the demo |
| D15 | Transactional outbox | Publish after commit | No lost events when pods are killed |
| D16 | Notification and audit owned by P1 | Owned by P4 | All Spring code under one owner |
| D17 | No customer-history features (stateless model) | 24 h aggregates | Simpler; Sparkov already separable |
| D18 | Gender and age kept, with a fairness audit | Drop them | Synthetic data, transparent audit |
| D19 | Simulated chargebacks: delayed true labels | Analyst labels only | Real production precision/recall/coverage |
| D20 | Model version pinned in Git, promoted by auto-merged PR (`AUTO_MERGE`) | Manual PR, MLflow alias + hot reload | Git is the single source of truth |
| D21 | Traefik ingress controller | Ingress NGINX (retired 03/2026), Envoy Gateway | Maintained, light, standard `Ingress` |
| D22 | Sealed Secrets | Secrets created by script | Everything deployable from Git |
| D23 | kind with 3 nodes | Single node | Replica spread and node-failure test |
| D24 | Automatic rollback via Git after failed e2e | Argo Rollouts | Simple, consistent with D20 |
| D25 | Security bonuses (cosign, ZAP) postponed | Plan them now | Only if time remains after S12 |
| D26 | Alerts to Discord | Slack, Grafana only | Free, on phones during the demo |
| D27 | Loki + Grafana Alloy | kubectl logs | Search by correlationId (~0.6 GB RAM) |
| D28 | k6 on a second laptop | k6 on the cluster machine | Unbiased measurements |
| D29 | 3 runs per experiment, median + range | Single run | Robust results |
| D30 | Spring Boot 4.1 + Java 21 | Boot 3.5, Java 25 | 3.x out of OSS support since 06/2026 |
| D31 | Reactive Spring Cloud Gateway (WebFlux) | Gateway Server MVC | Best documented, fits SSE |
| D32 | Contract-first OpenAPI | Code-first | Unblocks P3/P4/P5 from S2; CI checks code against contract |

## New decisions (after v1.0)

| # | Date | Decision | Rejected alternatives | Why |
|---|---|---|---|---|
| D33 | 2026-10-04 | `POST /api/v1/transactions` carries the raw card number (`cardNumber` = Sparkov `cc_num`). transaction-service resolves it with `POST /internal/customers/lookup` on customer-service (cached), then stores only `customerId` + `cardLast4` | Simulator sends `customerId`; transaction-service computes the HMAC | The simulator cannot know internal ids, and the HMAC key must stay in customer-service only (§6.9). Adds the flow transaction → customer to the NetworkPolicies (P4) |
| D34 | 2026-10-04 | risk-service reads the customer through `GET /internal/customers/{id}/risk-profile` (only the 6 fields `/predict` needs), not the public `GET /api/v1/customers/{id}` | Public endpoint with the propagated token | The propagated token is SIMULATEUR, which has no customer-read right (§3.8). Also data minimisation |
| D35 | 2026-10-04 | The audit schema is owned by `audit_migrator` (Flyway only). The runtime `audit_user` gets INSERT + SELECT through default privileges | `audit_user` owns the schema | A schema owner can always UPDATE/DELETE, so append-only would not be enforced by the database |
| D36 | 2026-10-04 | Users CRUD lives under `/api/v1/auth/users` | `/api/v1/users` | Keeps the one-prefix-per-service routing rule (`/api/v1/{domain}/**`) |
| D37 | 2026-10-04 | SSE auth uses the `Authorization` header (frontend: `@microsoft/fetch-event-source`) | Token in the query string | Tokens in URLs end up in access logs |
