# common — owner P1

Shared library (no main class). Add it as a dependency and these auto-configurations apply on their own:

| Feature | What a service gets | Where |
|---|---|---|
| Correlation id | `X-Correlation-Id` read (or generated if missing or not a UUID), put in the MDC as `correlationId`, and echoed on the response. Every `RestClient.Builder` from the context forwards it on outgoing calls. | `correlation/` |
| Problem Details | Every error is `application/problem+json` with `instance` and `correlationId` (contracts/common.yaml). A 400 lists `errors[{field, message}]`. A 500 returns `"Unexpected error"`: the real message only goes to the log. | `error/` |
| Resource server | A stateless JWT filter chain. JWKS comes from `spring.security.oauth2.resourceserver.jwt.jwk-set-uri`. The `roles` claim maps to `ROLE_*`. Liveness and readiness are open, everything else needs a token. 401 and 403 are Problem Details. `@PreAuthorize` is enabled. | `security/` |
| JSON logs | ECS JSON on stdout: `service.name`, `correlationId` and every MDC entry. Set `LOG_FORMAT=plain` for readable logs when running locally. | `logging/` |

All of these are servlet-only (`@ConditionalOnWebApplication(SERVLET)`). The web and security dependencies are `optional`, so the WebFlux gateway only gets the JSON logs.

## Using it in a service

Role rules (matrix: `contracts/gateway-routes.md`) are declared as beans. They apply after the probe paths and before `anyRequest().authenticated()`:

```java
@Bean
AuthorizationRules customerRules() {
    return rules -> rules
            .requestMatchers(HttpMethod.GET, "/api/v1/customers/**").hasAnyRole("ADMIN", "ANALYSTE")
            .requestMatchers("/api/v1/customers/**").hasRole("ADMIN");
}
```

Throw `ResponseStatusException` (or a subclass of `ErrorResponseException`) for 404, 409 and similar errors; the status and detail are kept. A service-specific `@RestControllerAdvice` takes priority over the common one. To build a body by hand, use `ProblemDetails.of(status, detail, request)`.

Declaring your own `SecurityFilterChain` replaces the common one entirely. Avoid it; it is only there as an escape hatch.

Outgoing calls: inject `RestClient.Builder`. Don't use `RestClient.create()`, which skips the correlation interceptor.

## Events (outbox, topology, idempotent consumer)

Rules: [`contracts/events.md`](../../contracts/events.md), choices: D15, D49.

| Feature | What a service gets | Where |
|---|---|---|
| Envelope | `EventEnvelope` record, `EventTypes` and `Topology` constants | `events/` |
| Outbox | `OutboxPublisher` writes the event in your transaction. A relay publishes every 500 ms (`FOR UPDATE SKIP LOCKED`, publisher confirms), a job purges rows published more than 7 days ago, and `outbox_pending` / `outbox_publish_failures_total` are exported. Opt-in: `fintech.outbox.enabled=true` | `outbox/` |
| Topology | Exchanges, queues, DLQs and bindings declared by every AMQP service. JSON message converter, so listeners take `EventEnvelope` | `messaging/` |
| Delivery defaults | Publisher confirms, ack after the listener returns, 3 attempts then the queue's DLQ. Overridable in `application.yml` | `messaging/` |
| Idempotent consumer | `IdempotentConsumer.handle(event, action)`: `processed_events` insert + action in one transaction, duplicates skipped, correlation id in the MDC | `messaging/` |

Set `spring.datasource.hikari.schema: <schema>` so plain JDBC uses the service schema.

Producer (must run inside the business transaction, otherwise `IllegalTransactionStateException`):

```java
@Transactional
public void decide(Transaction tx) {
    tx.setStatus(BLOQUEE);
    outbox.publish(EventTypes.TRANSACTION_BLOCKED, tx.getId().toString(), DecidedEvent.of(tx));   // actor = "system"
}
```

Consumer:

```java
@RabbitListener(queues = Topology.TRANSACTION_REVIEW_RESULTS_QUEUE)
void onReviewCompleted(EventEnvelope event) {
    idempotentConsumer.handle(event, e -> transactions.applyReview(e.payload()));
}
```

A throwing action rolls back its `processed_events` row, so the retry sees the event as new; after 3 attempts it lands in `<queue>.dlq`.

## Not here yet

Metric tags (#14).
