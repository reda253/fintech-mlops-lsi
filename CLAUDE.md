# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

University final project (JEE module, 5 students, delivery 09/01/2027, hard deadline 10/01/2027): a high-availability FinTech MLOps platform that makes a real-time fraud decision on each card transaction (Sparkov synthetic dataset). Graded 50/50 on **ML rigor** (5-model benchmark, statistical tests, uncertainty) and **production quality** (microservices, Kubernetes, CI/CD, monitoring, resilience under load and failure).

The working user is **P1**: backend architect and project lead. P1 owns `services/` (the 7 Spring Boot services), `contracts/`, `e2e-tests/` and the final README. Other folders belong to teammates; see `CODEOWNERS`. Each top-level folder has a README naming its owner.

## Source of truth

- `docs/specs/Architecture_Plateforme_FinTech_MLOps_1.pdf`: architecture v1.0 (74 pages). Section numbers like "§3.5" in code and docs refer to it. The `docs/specs/*.md` files are per-role extracts. `P1_Learning_and_Task_Plan.md` is P1's week-by-week task list.
- `docs/decisions.md`: decisions D1–D32 from the spec, plus later ones (D33+). **Every new architecture decision is appended there** in the same PR.
- `contracts/`: **contract-first** (D32). The OpenAPI YAML is written before the code; the code must match it, and CI will diff the springdoc-generated spec against it. If an API changes, update the contract in the same PR.

## Commands

Requires **JDK 21**. The machine default `java` is 17, so set `JAVA_HOME` first:

```bash
export JAVA_HOME="C:/Program Files/Eclipse Adoptium/jdk-21.0.10.7-hotspot"
cd services
./mvnw verify                                   # build + test all modules
./mvnw -pl risk-service -am verify              # one service (+ common)
./mvnw -pl risk-service -am test -Dtest=DecisionPolicyTest              # one test class
./mvnw -pl risk-service -am test -Dtest=DecisionPolicyTest#reviewWhenSetIsEmpty
./mvnw -pl risk-service spring-boot:run         # needs PostgreSQL (+ RabbitMQ) running
```

Lint the contracts (config in `contracts/redocly.yaml`). Lint only the service files: `common.yaml` is a component library pulled in through `$ref`.

```bash
cd contracts && npx -y @redocly/cli@latest lint *-service.yaml
```

Database bootstrap (one-time, superuser, passwords given as psql variables, never committed): see the header of `deploy/sql/00_schemas_users.sql`.

## Architecture (big picture)

```
Simulator / React → Traefik → api-gateway (8080, WebFlux) → auth 8081 · customer 8082 · transaction 8083
                                                            · risk 8084 · notification 8085 · audit 8086
transaction → (sync REST) → risk → customer (risk-profile) + ml-service (FastAPI 8000, /predict)
transaction, risk, auth → outbox → RabbitMQ `fintech.events` → audit (all), notification, transaction
```

- **Decision path is synchronous; notification and audit are asynchronous.** risk-service applies the policy to the conformal prediction set from ml-service: `[0]`→APPROUVER, `[1]`→BLOQUER, `[0,1]` or `[]`→REVUE. ml-service never decides.
- **Fail-safe invariant: nothing is ever auto-approved without the model.** ml-service down/timeout/circuit open → REVUE with reason `ML_INDISPONIBLE`. risk down → transaction stays `EN_ATTENTE`, `202`, re-evaluated every 30 s. Timeouts, retries and circuit-breaker settings are in `docs/architecture.md`.
- **Transactional outbox (D15):** producers never publish to RabbitMQ directly. They insert into `outbox_events` in the same DB transaction, and a relay publishes it (`FOR UPDATE SKIP LOCKED`, publisher confirms). Consumers are idempotent through `processed_events` (audit uses `ON CONFLICT (event_id) DO NOTHING`). Envelope, routing keys, queues and DLQs: `contracts/events.md`.
- **Idempotency:** `POST /api/v1/transactions` is idempotent on `transNum` (Sparkov `trans_num`). A replay returns the original response with `200`. The Traefik retry and the load tests depend on this.
- **Data:** one PostgreSQL instance, one schema + one user per service, no cross-schema grants. Each service owns its Flyway migrations in `src/main/resources/db/migration`. Hibernate is `ddl-auto: validate`; never let it create schema. Audit is append-only at the DB level: Flyway runs as `audit_migrator`, and the runtime `audit_user` has INSERT+SELECT only (D35).
- **Card data:** the card number is never stored. customer-service keeps an HMAC-SHA256 fingerprint + last 4 digits. transaction-service resolves cards via `POST /internal/customers/lookup` (D33). risk reads `GET /internal/customers/{id}/risk-profile` (D34).
- **Security:** auth-service signs RS256 JWTs (claim `roles`: ADMIN, ANALYSTE, SIMULATEUR). The gateway validates them and every service re-validates via JWKS (resource server). The role matrix is in `contracts/gateway-routes.md`. `/internal/**`, `/predict`, `/actuator/**` and the JWKS endpoint are never routed by the gateway.
- **Model features are computed inside the model pipeline (D13).** Java services send raw Sparkov fields to `/predict`; never compute ML features in Java.

## Code conventions (services/)

- Spring Boot **4.1.1**, Spring Cloud **2025.1.3**, Java 21. Boot 4 uses modular starters (`spring-boot-starter-webmvc`, `-flyway`, `-amqp`, `-security-oauth2-resource-server`, and matching `-test` starters). Spring Security 7 changed its DSL: use the official reference docs, not Boot-3-era tutorials (no `WebSecurityConfigurerAdapter`).
- Gateway = reactive (WebFlux). All other services = Spring MVC.
- Shared plumbing goes in `services/common` (correlation id + MDC, Problem Details handler, resource-server config, event envelope, outbox relay, idempotent consumer, metric tags). Don't duplicate it per service.
- Package base `ma.fintech.<service>`, with sub-packages `api` (controllers/DTOs), `domain`, `repository`, `service`, `messaging`, `client`, `config`.
- API: prefix `/api/v1`, errors as RFC 7807 `ProblemDetail`, pagination `?page=&size=&sort=`, header `X-Correlation-Id` propagated to calls, logs (JSON) and events.
- Config comes only from env vars with dev defaults (`${DB_URL:…}`); nothing is hard-coded.
- Health: liveness never checks a dependency. Readiness checks the DB only, never ml-service or RabbitMQ. Graceful shutdown is on. Metrics tagged `application=<service>` with latency buckets 50 ms … 5 s.
- HTTP client pools: max connection lifetime 30 s (K8s Services balance connections, not requests).
- Tests: JUnit 5 + Mockito; integration with Testcontainers (PostgreSQL, RabbitMQ); WireMock for ml-service stubs. ml-service also has `MODEL_MODE=mock` (amount > 500 → `[1]`, 200–500 → `[0,1]`), which drives all three decisions.
- Git: trunk-based, short `feat/…` / `fix/…` branches, Conventional Commits, small PRs.
