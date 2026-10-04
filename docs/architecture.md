# Architecture overview

Short working summary. The reference is [`specs/Architecture_Plateforme_FinTech_MLOps_1.pdf`](specs/Architecture_Plateforme_FinTech_MLOps_1.pdf) (74 pages, decisions D1–D32). New decisions go to [`decisions.md`](decisions.md). API contracts live in [`../contracts/`](../contracts/).

## Three planes

| Plane | Components |
|---|---|
| Application | React, Traefik Ingress, Spring Cloud Gateway, 6 Spring Boot services, PostgreSQL, RabbitMQ |
| ML | Training pipeline, MLflow (tracking + registry), FastAPI ml-service |
| Platform | kind (HPA, probes), GitHub Actions, Argo CD, Prometheus, Grafana, Alertmanager, Loki |

## Services

| Service | Port | Schema | Publishes | Consumes |
|---|---|---|---|---|
| api-gateway | 8080 | – | – | – |
| auth-service | 8081 | `auth` | `auth.login.*` | – |
| customer-service | 8082 | `customer` | – | – |
| transaction-service | 8083 | `transaction` | `transaction.decided.*` | `review.completed` |
| risk-service | 8084 | `risk` | `review.completed` | – |
| notification-service | 8085 | `notification` | – | `transaction.decided.review`, `.blocked` |
| audit-service | 8086 | `audit` | – | all (`#`) |
| ml-service (FastAPI) | 8000 | – | – | – |

## Main flow: assessing a transaction

```mermaid
sequenceDiagram
  autonumber
  participant S as Simulator
  participant GW as API Gateway
  participant T as transaction
  participant C as customer
  participant R as risk
  participant M as ml-service
  participant Q as RabbitMQ
  S->>GW: POST /api/v1/transactions (JWT SIMULATEUR)
  GW->>T: forward + JWT + X-Correlation-Id
  T->>T: save EN_ATTENTE (idempotent on transNum)
  T->>C: POST /internal/customers/lookup (cardNumber) [D33, cached]
  T->>R: POST /internal/risk/assess (2 s, CB)
  R->>C: GET /internal/customers/{id}/risk-profile [D34, cache 10 min]
  R->>M: POST /predict (800 ms, 1 retry, CB)
  M-->>R: probability, prediction set, uncertainty, version
  R->>R: policy: [0] APPROUVER, [1] BLOQUER, else REVUE
  R-->>T: assessment
  T->>T: update status + outbox row (same tx)
  T-)Q: transaction.decided.* (relay)
  T-->>S: 201 + decision
```

**Fail-safe:** ml-service down → REVUE (`ML_INDISPONIBLE`). risk down → `EN_ATTENTE` + `202`, re-evaluated every 30 s. **Never auto-approve without the model.**

## Transaction lifecycle

```mermaid
stateDiagram-v2
  [*] --> EN_ATTENTE : received
  EN_ATTENTE --> APPROUVEE : AUTO, confident legit
  EN_ATTENTE --> BLOQUEE : AUTO, confident fraud
  EN_ATTENTE --> EN_REVUE : uncertain or ML unavailable
  EN_REVUE --> APPROUVEE : analyst approves (MANUELLE)
  EN_REVUE --> BLOQUEE : analyst rejects (MANUELLE)
```

## Resilience settings (§3.6)

| Call | Timeout | Retry | Circuit breaker | On failure |
|---|---|---|---|---|
| Gateway → services | 3 s | no | no | `503` Problem Details |
| transaction → risk | 2 s | no | yes | `EN_ATTENTE` + `202`, job every 30 s |
| risk → customer | 500 ms | 1 (GET) | yes | cache, otherwise REVUE |
| risk → ml-service | 800 ms | 1 (connection error) | yes | REVUE `ML_INDISPONIBLE` |

Circuit breaker: opens at 50 % failures over the last 20 calls, stays open 30 s. HTTP pools: max connection lifetime 30 s.

## Health rules (§6.7)
- Liveness never checks a dependency (a DB outage would restart every pod in a loop).
- Readiness checks the DB only. Never ml-service (risk has a fallback), never RabbitMQ (the outbox buffers).
