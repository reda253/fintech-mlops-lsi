# Event catalog (RabbitMQ) — v1

Owner: P1. Source: architecture §3.5. Envelope JSON Schema: [`events.schema.json`](events.schema.json).

## Rules

1. **Producers never publish directly.** They insert into `outbox_events` in the same DB transaction as the business change; a relay publishes every 500 ms (`SELECT … FOR UPDATE SKIP LOCKED`, publisher confirms) and then marks the row published (D15).
2. **Delivery is at-least-once.** Durable exchanges, queues and messages; manual ack after processing.
3. **Consumers are idempotent.** Each consumer inserts `eventId` into its `processed_events` table in the same transaction as its own change, and skips the message if the id is already there (unique key).
4. **Failures:** 3 attempts, then the message goes to the queue's DLQ via `fintech.dlx`.
5. **AMQP properties:** `message_id = eventId`, `content_type = application/json`, header `X-Correlation-Id = correlationId`, `delivery_mode = 2` (persistent).
6. **Versioning:** a breaking payload change bumps `version` and both versions are consumed during the transition. Adding an optional field is not breaking.

## Envelope

```json
{
  "eventId": "8a1f0c6e-7a1b-4c39-9a52-0f9d3c1b2e44",
  "type": "transaction.decided.blocked",
  "version": 1,
  "occurredAt": "2026-11-20T14:03:12Z",
  "correlationId": "b7e0…",
  "producer": "transaction-service",
  "actor": "system",
  "payload": { }
}
```

`actor` is the username behind the change (`system` for automatic decisions). audit-service stores it in `audit_events.actor`.

## Topology

| Exchange | Type | Purpose |
|---|---|---|
| `fintech.events` | topic, durable | All domain events |
| `notifications.live` | fanout, durable | Live re-broadcast to every notification-service replica |
| `fintech.dlx` | direct, durable | Dead letters (routing key = original queue name) |

| Queue | Bindings on `fintech.events` | Consumer | DLQ |
|---|---|---|---|
| `audit.all` | `#` | audit-service | `audit.all.dlq` |
| `notification.alerts` | `transaction.decided.review`, `transaction.decided.blocked` | notification-service (shared by replicas) | `notification.alerts.dlq` |
| `transaction.review-results` | `review.completed` | transaction-service | `transaction.review-results.dlq` |
| *(server-named, exclusive, auto-delete)* | bound to `notifications.live` | one per notification-service replica | none (live push only, data already stored) |

## Events

### `transaction.decided.approved` / `.review` / `.blocked`
Producer: **transaction-service**, after the AUTO decision (§2.5). Consumers: audit (all three), notification (`review`, `blocked`).

```json
{
  "transactionId": "uuid",
  "transNum": "2da90c7d74bd46a0caf3777415b3ebd3",
  "customerId": "uuid",
  "amount": 842.17,
  "category": "shopping_net",
  "status": "BLOQUEE",
  "decisionSource": "AUTO",
  "decision": "BLOQUER",
  "reason": "MODELE_CONFIANT",
  "fraudProbability": 0.87,
  "predictionSet": [1],
  "uncertainty": 0.56,
  "modelVersion": "fraud-detector:8",
  "reviewId": null
}
```
`status` ∈ `APPROUVEE | EN_REVUE | BLOQUEE`. For `reason = ML_INDISPONIBLE`, `fraudProbability`, `predictionSet`, `uncertainty` and `modelVersion` are `null`. `reviewId` is set when `status = EN_REVUE`.

### `review.completed`
Producer: **risk-service**, when an analyst decides. Consumers: transaction (moves `EN_REVUE` → final status with source `MANUELLE`), audit.

```json
{
  "reviewId": "uuid",
  "transactionId": "uuid",
  "finalDecision": "BLOQUEE",
  "analyst": "analyste1",
  "comment": "Montant atypique, carte utilisée à 800 km",
  "modelVersion": "fraud-detector:8",
  "openedAt": "2026-11-20T14:03:12Z",
  "closedAt": "2026-11-20T14:09:40Z"
}
```

### `auth.login.succeeded` / `auth.login.failed`
Producer: **auth-service**. Consumer: audit.

```json
{ "userId": "uuid or null", "username": "analyste1", "reason": "BAD_CREDENTIALS | DISABLED | null" }
```
The password is never included. The IP is not stored (out of scope).

## Changing this catalog
Add or change an event **in the same PR** as the producer and consumer changes, and request review from the owners of every consuming service (CODEOWNERS).
