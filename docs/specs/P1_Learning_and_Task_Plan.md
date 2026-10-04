# P1 Personal Plan: What to Learn and Everything to Do

**Role:** Backend architect and project lead (*chef de projet*).
**Period:** S1 (28/09/2026) → delivery on Saturday 09/01/2027.
**Companion files:** `roles/00_Commun.md` and `roles/P1_Backend_Chef_de_projet.md`.

---

## 0. Before you start: three things to know

### Your job has two halves

| Half | Share of your time | What it means |
|---|---|---|
| **Backend architect** | ~75 % | Design and build the 7 Spring Boot services, the contracts, the event system and the end-to-end tests |
| **Project lead** | ~25 % | Run the weekly meeting, keep the board up to date, check handoffs and milestones, unblock people, consolidate the README, coordinate the demo |

You carry the heaviest load in the team. **P3 is your official backup** (decision in section 10). Use that help early, not in a panic in week 10.

### Confirmed technical choices

| Decision | Choice |
|---|---|
| D30 | **Spring Boot 4.1 + Java 21.** Spring Boot 3.x reached end of open-source support in June 2026. Spring Security 7 changed its configuration DSL, so tutorials written for Boot 3 may not compile as-is: use the **official reference docs** first |
| D31 | **Spring Cloud Gateway, reactive (WebFlux) flavor**, only for the Gateway. The 6 other services use classic Spring MVC. The Gateway is mostly YAML configuration plus two or three global filters, so you only need reactive basics (`Mono`, `ServerWebExchange`) |
| D32 | **Contract-first.** You write the OpenAPI YAML files in S1–S2 in `contracts/`, then implement them. springdoc generates the spec from the code, and the CI checks it matches the YAML |

### Build one shared library first

The 7 services all need the same plumbing:
- correlation ID,
- error format,
- JWT validation,
- event envelope,
- outbox,
- RabbitMQ setup,
- metrics tags.

**Write it once in a `common` Maven module, used by all services.** Otherwise you'll copy and fix the same bug 7 times. This is the single most important time-saver in your role.

```
services/
├── pom.xml                  # parent: Spring Boot + Spring Cloud BOMs, plugin versions
├── common/                  # shared library (no main class)
│   ├── correlation/         # X-Correlation-Id filter + MDC for logs
│   ├── error/               # RFC 7807 Problem Details handler
│   ├── security/            # resource-server config, role helpers
│   ├── events/              # event envelope, routing keys constants
│   ├── outbox/              # OutboxEvent entity, relay, purge job, metric
│   ├── messaging/           # idempotent consumer helper (processed_events), DLQ setup
│   └── observability/       # common metric tags, histogram buckets
├── api-gateway/
├── auth-service/
├── customer-service/
├── transaction-service/
├── risk-service/
├── notification-service/
└── audit-service/
```

**Package layout inside each service:**

| Package | Contents |
|---|---|
| `api` | Controllers and DTOs |
| `domain` | Entities and business rules |
| `repository` | Data access |
| `service` | Use cases |
| `messaging` | Publishers and consumers |
| `client` | Calls to other services |
| `config` | Configuration classes |

---

## 1. What you need to learn

**Learn just in time.** Each topic is placed right before the week you need it. You don't need to master everything in S1.

### 1.1 Learning roadmap

| # | Topic | Why (your task) | Learn by | Depth | Best resource |
|---|---|---|---|---|---|
| 1 | **OpenAPI 3** (writing YAML specs) | The contracts you deliver in S2, which block P3, P4 and P5 | S1 | Solid | OpenAPI Specification docs, Swagger Editor |
| 2 | **Spring Boot 4 fundamentals**: dependency injection, `@RestController`, validation (`@Valid`), configuration and profiles, `ProblemDetail` errors | Every service | S2 | Solid | Spring Boot reference docs, Spring "Getting Started" guides |
| 3 | **Maven multi-module projects** | The `services/` parent and `common` module | S2 | Basic | Maven docs ("multi-module") |
| 4 | **Spring Data JPA + PostgreSQL + Flyway**: entities, repositories, `@Transactional`, pagination, `@Version` (optimistic locking), native queries | All services with data | S3 | Solid | Spring Data JPA reference, Flyway docs |
| 5 | **PostgreSQL schemas, users and GRANTs** | One schema and user per service, audit with INSERT + SELECT only | S3 | Basic | PostgreSQL docs ("Schemas", "GRANT") |
| 6 | **JWT + RS256 + JWKS**: claims, signing with a private key, verifying with the public key | auth-service issues tokens, everyone verifies them | S3 | Solid | jwt.io introduction, Nimbus JOSE + JWT docs |
| 7 | **Spring Security 7**: OAuth2 **resource server** (JWT), `SecurityFilterChain`, `@PreAuthorize`, BCrypt | Every service plus the Gateway | S3 | Solid | Spring Security reference ("OAuth2 Resource Server → JWT"). Avoid old tutorials using `WebSecurityConfigurerAdapter` |
| 8 | **Spring Cloud Gateway (WebFlux)**: routes, predicates, filters, global filters, CORS, reactive security basics (`Mono`, `ServerWebExchange`, `SecurityWebFilterChain`) | api-gateway | S3–S4 | Medium | Spring Cloud Gateway reference |
| 9 | **Testing**: JUnit 5, Mockito, `@SpringBootTest`, `@WebMvcTest`, **Testcontainers** (PostgreSQL, RabbitMQ), WireMock | All services (CI requires it) | S4 | Solid | Testcontainers guides for Spring Boot, WireMock docs |
| 10 | **RabbitMQ concepts**: exchanges (topic, fanout), queues, bindings, routing keys, manual ack, dead-letter queues, publisher confirms | Events between services | S5 | Solid | Official RabbitMQ tutorials (Java), tutorials 1–5 + "Publisher confirms" |
| 11 | **Spring AMQP**: `RabbitTemplate`, `@RabbitListener`, declaring topology, error handling | Producers and consumers | S5 | Solid | Spring AMQP reference |
| 12 | **Transactional outbox pattern** and **idempotent consumers** | Reliable events (D15) | S5 | Solid | microservices.io: "Transactional outbox" and "Idempotent consumer" (Chris Richardson). PostgreSQL docs: `SELECT … FOR UPDATE SKIP LOCKED` |
| 13 | **HTTP clients**: Spring `RestClient`, timeouts, connection pool with max lifetime (Apache HttpClient 5) | transaction → risk, risk → customer, risk → ml-service | S6 | Medium | Spring Framework reference ("REST Clients") |
| 14 | **Resilience4j**: circuit breaker, time limiter, retry, fallback | risk-service resilience (section 3.6) | S6 | Solid | Resilience4j docs (Spring Boot module) |
| 15 | **Caffeine cache** with `@Cacheable` | Customer profile cache in risk-service | S7 | Basic | Spring Boot reference ("Caching") |
| 16 | **Server-Sent Events** (`SseEmitter`) | Live notifications in React | S7 | Medium | Spring Framework reference ("SSE") |
| 17 | **Actuator + Micrometer**: health groups (liveness, readiness), `/actuator/prometheus`, common tags, histogram buckets | Kubernetes probes and Grafana | S8 | Medium | Spring Boot reference ("Actuator", "Metrics") |
| 18 | **Structured JSON logs** with MDC (correlation ID) | Loki search by `correlationId` | S8 | Basic | Spring Boot reference ("Structured logging") |
| 19 | **Docker basics**: images, multi-stage Dockerfile, Docker Compose | Run and debug locally (P4 writes the final Dockerfiles) | S2 | Basic | Docker docs ("Get started") |
| 20 | **Kubernetes as a developer**: Pods, Deployments, Services, probes, ConfigMaps/Secrets, graceful shutdown, `kubectl logs/describe/port-forward` | Understand how your services run and fail | S8 | Basic | Kubernetes docs ("Tutorials → Basics") |
| 21 | **End-to-end testing** with REST Assured (or the Java HTTP client) | 7 post-deploy scenarios (section 7.7) | S9 | Medium | REST Assured docs |
| 22 | **Performance basics**: Tomcat thread pool and queue limits, HikariCP pool sizing, PostgreSQL indexes, `EXPLAIN` | Overload behavior (9.5) and fixing what load tests reveal | S10 | Basic | Spring Boot reference ("Embedded web servers"), HikariCP wiki ("About pool sizing") |
| 23 | **Git and GitHub for a lead**: PR reviews, rulesets, CODEOWNERS, Conventional Commits, GitHub Projects, milestones, releases | Running the repo | S1 | Medium | GitHub Docs |
| 24 | **Lightweight project management**: weekly meeting, tracking a critical path, risk list, writing clear issues | Lead role | S1 | Basic | Section 10 of the architecture document |

### 1.2 What you can skip

You don't need to learn these. Others own them, and understanding the concepts is enough:

| Topic | Owner |
|---|---|
| Machine learning internals | P2 |
| MLflow | P3 |
| Prometheus queries and Grafana dashboards | P5 |
| Helm, Argo CD, kind setup, k6 | P4 |
| React | P5 |

### 1.3 Concepts to understand deeply (likely jury questions)

1. **Why an outbox instead of publishing directly**, and what happens if a pod dies between the database commit and the publish.
2. **Why consumers must be idempotent** (at-least-once delivery means duplicates are possible).
3. **Why liveness must never check the database** (a database outage would cause a restart loop of every service).
4. **Why a failure never auto-approves a transaction** (fail-safe → human review).
5. **Why RS256 instead of a shared secret** (only auth-service can sign; everyone else can only verify).
6. **Why optimistic locking on reviews** (two analysts deciding the same case at once).
7. **Why Kubernetes Services balance connections, not requests**, and why the 30 s connection lifetime matters (section 6.11).

---

## 2. Complete task list, from first day to delivery

**Legend:**
- 🧭 = project-lead task, 🛠 = backend task.
- **[Handoff #n]** = a deliverable others are waiting for (section 10.5).
- Each week ends with the **Sunday team meeting** (30 min).

### S1 (28/09 → 04/10): Kick-off and foundations

- [ ] 🧭 **Kick-off meeting.** Present the architecture PDF, give each member their role file, and agree on the rules: daily Discord message, Sunday meeting, PR reviews.
- [ ] 🧭 **Create the GitHub organization/repo** with P4:
  - monorepo layout (section 7.1),
  - ruleset on `main` (PR + 1 approval + required checks),
  - `CODEOWNERS`,
  - PR template,
  - issue templates.
- [ ] 🧭 **GitHub Projects board:**
  - columns *Backlog / To do / In progress / Review / Done*,
  - one milestone per jalon (J1–J9),
  - one card per task in section 10.4, assigned to its owner.
- [ ] 🧭 **Discord server:** channels `#general`, `#backend`, `#ml`, `#devops`, `#frontend`, `#alertes-critiques`, `#alertes-warning`.
- [ ] 🛠 **Maven parent + empty modules:** `common` and the 7 services, generated from start.spring.io with Spring Boot 4.1 and Java 21, plus the compatible Spring Cloud release train shown there. Make sure `mvn verify` passes.
- [ ] 🛠 **Domain model on paper:** entities and fields for every service (section 3.4), transaction statuses (section 3.3), roles (section 3.8).
- [ ] 🛠 **Event catalog:** envelope JSON schema and routing keys (section 3.5), written in `contracts/events.md`.
- [ ] 🛠 Start the **OpenAPI contracts**: auth, customer, transaction.
- [ ] 📚 Learn: OpenAPI, Git/GitHub lead features, Docker basics.

### S2 (05/10 → 11/10): Contracts. Milestone J1 on Sunday 11/10

- [ ] 🛠 **Finish OpenAPI v1 for all services:**
  - gateway routes,
  - auth, customer, transaction, risk (public + `/internal`), notification (including SSE), audit.
  - Every error response uses Problem Details.
- [ ] 🛠 Agree on the **`/predict` contract** with P3, using section 5.7 as the base.
- [ ] 🛠 **Database schemas:** one Flyway `V1__init.sql` draft per service, with tables, keys and **indexes**:
  - `transactions(status, created_at)`,
  - `transactions(customer_id)`,
  - unique `trans_num`,
  - outbox "unpublished" index,
  - unique `event_id` in `processed_events`.
- [ ] 🛠 **SQL script for schemas and users** (`auth_user`, …, `audit_user` with INSERT + SELECT only), given to P4 for the PostgreSQL deployment.
- [ ] 🛠 **Architecture diagram + contracts in `docs/` and `contracts/`.**
- [ ] 🧭 **J1 review meeting:** P3, P4 and P5 validate the contracts. Merge them. **[Handoff #2 → P3, P4, P5]**
- [ ] 📚 Learn: Spring Boot 4 fundamentals, Maven multi-module, JWT concepts.

### S3 (12/10 → 18/10): Shared library + Auth. Milestone J2 on Sunday 18/10

- [ ] 🛠 **`common` module v1:**
  - correlation ID filter (servlet) with MDC,
  - Problem Details handler,
  - resource-server security config (JWKS URL from config, roles from a `roles` claim),
  - JSON structured logging config.
- [ ] 🛠 **auth-service:**
  - `users` table, BCrypt, roles `ADMIN` / `ANALYSTE` / `SIMULATEUR`;
  - seed users through a Flyway migration;
  - RS256 key pair loaded from a Secret, with a local file in dev;
  - `POST /login` (access token 15 min + refresh token 7 days), `POST /refresh`, `GET /me`, users CRUD (ADMIN);
  - `GET /.well-known/jwks.json`;
  - tests: unit + Testcontainers.
- [ ] 🛠 **api-gateway skeleton:** routes to auth, JWT validation via JWKS, correlation ID global filter, `/internal/**` never routed.
- [ ] 🛠 Run everything with **P4's Docker Compose** (delivered end of S3).
- [ ] 🧭 Check J2: MLflow (P3), data (P2), Docker Compose + CI (P4).
- [ ] 📚 Learn: Spring Data JPA, Flyway, PostgreSQL GRANTs, Spring Security 7 resource server, Spring Cloud Gateway.

### S4 (19/10 → 25/10): Gateway + Customer

- [ ] 🛠 **api-gateway complete:**
  - all routes, CORS for the React origin,
  - rate limiting on `/login` only,
  - SSE route (no buffering, long timeout),
  - HTTP client pool with **max connection lifetime 30 s**.
- [ ] 🛠 **customer-service:**
  - entity and CRUD with pagination and filters;
  - **card number never stored**: HMAC-SHA256 fingerprint + last 4 digits, with the key from a Secret;
  - Flyway data migration loading the **unique Sparkov customers** (get the extracted CSV from P2 at S3);
  - tests.
- [ ] 🛠 **Testcontainers base class** in `common` (shared PostgreSQL and RabbitMQ containers).
- [ ] 🧭 Check that SonarCloud and Trivy are running on your PRs (P4, S4–S6). Fix the first findings.
- [ ] 📚 Learn: testing stack (Testcontainers, WireMock).

### S5 (26/10 → 01/11): Transaction + outbox + RabbitMQ

- [ ] 🛠 **transaction-service:**
  - entity, statuses and decision source (`AUTO` / `MANUELLE`);
  - `POST` **idempotent on `trans_num`**: a duplicate returns the original response, without creating anything;
  - `GET` list with filters (status, customer, period, amount) and `GET /{id}`.
- [ ] 🛠 **Outbox in `common`:**
  - `outbox_events` entity,
  - `OutboxPublisher.save(event)` called in the same transaction as the business change,
  - relay every 500 ms with `SELECT … FOR UPDATE SKIP LOCKED` and **publisher confirms**, then mark as published,
  - purge job (> 7 days),
  - gauge `outbox_pending`.
- [ ] 🛠 **RabbitMQ topology in code:**
  - exchange `fintech.events` (topic) and `notifications.live` (fanout),
  - queues and bindings from section 3.5,
  - one DLQ per queue, 3 retries.
- [ ] 🛠 **Idempotent consumer helper:** `processed_events` table and a wrapper that skips already-seen `eventId`s.
- [ ] 🛠 Test: kill the app between commit and publish, and check the event is still published after restart.
- [ ] 📚 Learn: RabbitMQ, Spring AMQP, outbox and idempotent consumer.

### S6 (02/11 → 08/11): Risk service starts. Milestone J3 on Sunday 08/11

- [ ] 🛠 **transaction → risk call:** `RestClient`, 2 s timeout, circuit breaker. If risk is unavailable: status `EN_ATTENTE` + `202`, and a **scheduled job re-evaluates pending transactions every 30 s**.
- [ ] 🛠 **risk-service v1:**
  1. `POST /internal/risk/assess` fetches the customer profile.
  2. It calls the ml-service **in mock mode** (from P3 at S6) with a timeout of 800 ms, 1 retry and a circuit breaker.
  3. It applies the **decision policy**: `[0]` → APPROUVER, `[1]` → BLOQUER, `[0,1]` or `[]` → REVUE. If the ml-service fails → REVUE with reason `ML_INDISPONIBLE`.
  4. It saves the `assessments` row, including the model version.
- [ ] 🛠 **transaction-service** saves the decision and publishes `transaction.decided.*` through the outbox.
- [ ] 🛠 **Freeze the REST endpoints** and announce them. **[Handoff #7 → P4 (containers), P5 (React)]**
- [ ] 🧭 **J3 check:**
  - your base services work,
  - benchmark done (P2),
  - ml-service mock delivered (P3),
  - security checks active in the CI (P4).
- [ ] 📚 Learn: `RestClient` and connection pools, Resilience4j.

### S7 (09/11 → 15/11): Human review + Notification

- [ ] 🛠 **risk-service review queue:**
  - `reviews` table with `@Version`;
  - `GET /reviews?status=OUVERTE` (ANALYSTE);
  - `POST /reviews/{id}/decision` returns `409` on a conflict;
  - publishes `review.completed` through the outbox.
- [ ] 🛠 **transaction-service consumes `review.completed`** and moves `EN_REVUE` → `APPROUVEE` / `BLOQUEE` with source `MANUELLE`.
- [ ] 🛠 **Customer profile cache** in risk-service (Caffeine, 10 min).
- [ ] 🛠 **notification-service:**
  - consumes `decided.review` and `decided.blocked` from the shared durable queue and stores them;
  - republishes to the `notifications.live` fanout;
  - each replica has its own temporary queue and pushes to its **SSE** clients (`/notifications/stream`);
  - `GET` list and `PATCH /{id}/read`.
- [ ] 🛠 Start minimal (store + list), then add SSE. Ask P3 for help if you're late (backup).
- [ ] 📚 Learn: Caffeine, SSE.

### S8 (16/11 → 22/11): Audit + observability. Milestone J4 on Sunday 22/11

- [ ] 🛠 **audit-service:**
  - consumes `#` (all events) and stores them in `audit_events` (JSONB payload);
  - `GET /audit` with filters (ADMIN);
  - verify that the `audit_user` **cannot UPDATE or DELETE**, with a test.
- [ ] 🛠 **auth-service publishes** `auth.login.succeeded` / `.failed`.
- [ ] 🛠 **Observability in every service:**
  - Actuator health groups: liveness = process only, readiness = database where needed (never ml-service, never RabbitMQ);
  - `/actuator/prometheus`;
  - tag `application=<service>`;
  - latency histograms with buckets 0.05 / 0.1 / 0.25 / 0.5 / 1 / 2 / 5 s.
- [ ] 🛠 **Graceful shutdown:** `server.shutdown=graceful`. Give P4 the probe paths and startup times for the manifests.
- [ ] 🛠 **Switch from the mock to the first real model** (P3, S8) and check the three decisions still happen.
- [ ] 🧭 **J4 check:** statistics done (P2), Argo CD deployment (P4), first real model (P3), Prometheus (P5).
- [ ] 📚 Learn: Actuator / Micrometer, structured logs, Kubernetes basics.

### S9 (23/11 → 29/11): Feedback loop + end-to-end tests

- [ ] 🛠 **`POST /api/v1/risk/feedback`** (SIMULATEUR): store the true label, match it with the decision, and expose the counters:
  - `risk_feedback_total{decision,truth}`,
  - `risk_conformal_covered_total{truth}`,
  - `risk_review_agreement_total`.
- [ ] 🛠 **`GET /internal/risk/labels`** for P3's pipeline.
- [ ] 🛠 **`e2e-tests/` project:** the 7 scenarios of section 7.7 (health, auth, full transaction, model version, async chain to audit, review, `/predict` not reachable). Package it as a Docker image for the Argo CD PostSync Job.
- [ ] 🛠 Review P4's Kubernetes manifests for your services: probes, resources, env vars, Secrets.
- [ ] 📚 Learn: REST Assured.

### S10 (30/11 → 06/12): Resilience settings. Milestone J5 on Sunday 06/12

- [ ] 🛠 **e2e tests running after each deployment**, with automatic rollback working (with P4). **[Handoff #14 → P4]**
- [ ] 🛠 **Overload protection:**
  - bounded Tomcat threads and accept queue (fast `503` instead of piling up);
  - HikariCP pool sizes checked against PostgreSQL `max_connections`;
  - pool max-lifetime 30 s on every HTTP client.
- [ ] 🛠 Agree with P4 on the **Traefik retry** (safe thanks to `trans_num` idempotency) and `tolerationSeconds: 30`.
- [ ] 🛠 Help P4 with the **capacity test**: watch your services' latency and errors and fix the first bottlenecks (indexes, N+1 queries, pool sizes).
- [ ] 🧭 **J5 check:** final model (P2), full pipeline (P3), full CI/CD (P4), e2e tests green.
- [ ] 📚 Learn: performance basics.

### S11 (07/12 → 13/12): Experiments support + README start

- [ ] 🛠 Be **on call during P4's experiments** (main scenario, pod kills). Fix what breaks: outbox, idempotency, timeouts, circuit breakers.
- [ ] 🛠 Check **C6 (RabbitMQ killed):** the number of audit events equals the number of transactions after recovery.
- [ ] 🛠 Check **C4 (ml-service down):** **zero** auto-approvals.
- [ ] 🧭 **Create the README skeleton:** final structure, one heading per member, with a deadline for each section.
- [ ] 🛠 Write your README section **"Architecture microservices"**.

### S12 (14/12 → 20/12): Final fixes. Milestone J6 on Sunday 20/12

- [ ] 🛠 Fix every bug found during the chaos experiments, then re-run the affected experiment with P4.
- [ ] 🛠 Finish your README section: diagrams, endpoint list, event catalog, resilience choices, test coverage.
- [ ] 🧭 **J6 check:** all experiments ×3, dashboards and alerts validated, videos recorded (P4, P5).
- [ ] 🧭 Announce the **code freeze** for Monday 21/12.

### S13 (21/12 → 27/12): Code freeze

- [ ] 🧭 **Freeze rule:** only bug-fix PRs, each one reviewed. No new features.
- [ ] 🧭 **Collect all README sections.**
- [ ] 🛠 Fix only critical bugs.

### S14 (28/12 → 03/01): README consolidation. Milestone J8 on Sunday 03/01

- [ ] 🧭 **Consolidate the README:**
  - one consistent style,
  - table of contents,
  - links to the architecture PDF, dashboards (screenshots) and experiment results,
  - "how to run" section (`make cluster`, prerequisites),
  - limits and future work.
- [ ] 🧭 **Review the demo v1 with P5:** 5 min maximum, every subject requirement visible at least once.
- [ ] 🧭 **Everyone proofreads** the README. Fix the remarks.

### S15 (04/01 → 09/01): Delivery

- [ ] 🧭 **Repo cleanup:**
  - remove dead code and test files;
  - no secret in clear text (gitleaks green);
  - all workflows green.
- [ ] 🧭 **Final check on a clean machine:** `make cluster` → everything deploys → e2e tests pass.
- [ ] 🧭 **Tag the release `v1.0`** on GitHub with release notes.
- [ ] 🧭 **Final demo rehearsal** with the whole team.
- [ ] 🧭 **Deliver on Saturday 09/01:** GitHub link, README and demo video. Keep Sunday 10/01 as the safety margin.

---

## 3. Definition of done for each service

A service is "done" only when **all** of these are true:

- [ ] Endpoints match the OpenAPI contract (the CI `contracts` check is green).
- [ ] Unit tests and Testcontainers integration tests pass. SonarCloud quality gate is green (coverage on new code ≥ 60 %).
- [ ] Errors use Problem Details. Logs are JSON with `correlationId`.
- [ ] Actuator liveness and readiness are correct. `/actuator/prometheus` exposes metrics with the `application` tag.
- [ ] Graceful shutdown is configured.
- [ ] All configuration comes from env vars (ConfigMap / Secret). Nothing is hard-coded.
- [ ] Events go through the outbox, and consumers are idempotent.
- [ ] The service runs in Docker Compose **and** in the cluster.
- [ ] It is documented in your README section.

## 4. Your weekly lead routine (about 3 h per week)

| When | What |
|---|---|
| Every day (5 min) | Read the Discord daily messages and spot blockers |
| Mid-week (30 min) | Review open PRs from others that touch your contracts. Update the board |
| Sunday (30 min meeting + 30 min prep) | Before: check the milestone criteria and handoffs due. During: progress, blockers, decisions. After: write 5-line minutes in `docs/meetings/` |
| When a handoff slips | Same day: talk to the owner, decide on a fallback (mock, reduced scope, help from the backup) |
| When a decision is needed | Add it to the decisions table (section 2.6) so it's traceable |
