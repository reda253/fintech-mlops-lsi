# services/ — owner P1

Maven multi-module: `common` + 7 Spring Boot services. Build: `./mvnw verify` (JDK 21).

## Observability (§6.7, §6.8, §8.2)

The same settings in every service's `application.yml`. K8s probes and `preStop` are in `deploy/k8s/apps/deployments.yaml`.

| Endpoint | Token | Checks | Used by |
|---|---|---|---|
| `/actuator/health/liveness` | no | the JVM only, **never a dependency** | K8s startupProbe and livenessProbe |
| `/actuator/health/readiness` | no | the database only (`readinessState,db`); never RabbitMQ (the outbox buffers events), never ml-service (risk falls back to REVUE). The gateway has no database | K8s readinessProbe |
| `/actuator/prometheus` | no (D43) | Micrometer metrics, tagged `application=<service>` | Prometheus |
| any other `/actuator/**` | JWT | – | – |

If liveness checked PostgreSQL, a database outage would restart every pod in a loop. Readiness only takes the pod out of the Service until the database is back.

**Latency histograms.** `http.server.requests` (incoming) and `http.client.requests` (calls to other services) have buckets on the objectives: 0.05 · 0.1 · 0.25 · 0.5 · 1 · 2 · 5 s. So p95 is computable with `histogram_quantile`, and the 2 s target is exactly one bucket. On the gateway, the server timer covers the whole proxied call.

```promql
histogram_quantile(0.95, sum by (le, application) (rate(http_server_requests_seconds_bucket[5m])))
```

**Graceful shutdown.** On SIGTERM, Kubernetes allows 30 s (`terminationGracePeriodSeconds`). `preStop` sleeps 5 s, so the pod leaves the Service endpoints before it stops taking requests. Spring then stops accepting new requests and gives in-flight ones up to 20 s (`spring.lifecycle.timeout-per-shutdown-phase`). That is 5 + 20 = 25 s, inside the 30 s, so the JVM is never killed mid-request.

Tests: `ProbeConfigTest` (customer, transaction, risk, notification, audit) reads these settings from `application.yml`. `auth-service` `ProbeGroupsTest` and `api-gateway` `MetricsTest` check them on a running application, including the buckets in the real scrape output.

Coming with later features: `outbox_pending` (#8), circuit-breaker state (#10), RabbitMQ queue metrics.
