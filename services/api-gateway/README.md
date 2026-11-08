# api-gateway

Owner: P1. Single entry point for the React app and the simulator: routing, JWT check, correlation id, CORS, login rate limit, error format. Spring Cloud Gateway on WebFlux (reactive), port 8080. No database.

Spec: §3.4, §3.6, §6.11. Contract: [`contracts/gateway-routes.md`](../../contracts/gateway-routes.md) (routes, role matrix). Traefik sends `fintech.local/api/**` here.

## What happens to a request

Order matters; each step is a `WebFilter` or part of the Spring Security chain.

| # | Step | Class | On failure |
|---|---|---|---|
| 1 | Keep a valid `X-Correlation-Id` or generate one; forward it and set it on every response | `correlation/CorrelationIdWebFilter` (highest precedence) | – |
| 2 | Spring Security firewall: reject `..`, encoded `/`, `;` in the path | built in | `400` |
| 3 | CORS: answer preflights, add `Access-Control-*` headers | `config/CorsConfig` + `http.cors()` | `403` (unknown origin) |
| 4 | JWT: signature and expiry against auth-service's JWKS. Public: probes, `/actuator/prometheus`, `POST /api/v1/auth/login` and `/refresh` | `config/GatewaySecurityConfig` | `401` Problem Details + `WWW-Authenticate: Bearer` |
| 5 | Login rate limit, per client IP | `ratelimit/LoginRateLimitWebFilter` (order 0) | `429` Problem Details + `Retry-After` |
| 6 | Route to the service, `Authorization` forwarded unchanged | `application.yml` routes | `404` (no route) |
| 7 | Service down or no response headers within 3 s | `error/GatewayErrorHandler` | `503` Problem Details |

Roles are **not** checked here. Each service re-validates the JWT and checks roles itself (D6).

Never routed, even with a valid token: `/internal/**`, `/predict`, `/.well-known/jwks.json`, `/actuator/**` (`NeverRoutedTest`).

## Configuration

Only env vars, with dev defaults (`src/main/resources/application.yml`).

| Variable | Default | Meaning |
|---|---|---|
| `AUTH_URI` … `AUDIT_URI`, `ML_URI` | `http://localhost:8081` … `8086`, `8000` | Base URL of each service |
| `JWKS_URI` | `http://localhost:8081/.well-known/jwks.json` | auth-service public keys (cached) |
| `CORS_ALLOWED_ORIGINS` | `https://fintech.local,http://localhost:5173` | Comma-separated, exact origins |
| `LOGIN_RATE_LIMIT_CAPACITY` | `5` | Login attempts allowed in a burst, per IP and per pod |
| `LOGIN_RATE_LIMIT_PERIOD` | `1m` | Time to get the whole burst back (here: 1 attempt every 12 s) |

Fixed in `application.yml`: connect timeout 1 s, response timeout 3 s (off for the SSE route), connection pool max lifetime 30 s (§6.11: new connections spread over pods after a scale-up).

## Run locally

Needs auth-service (for login and the JWKS). The other services are only needed for their own routes.

```bash
cd services
./mvnw -pl auth-service spring-boot:run      # see auth-service/README.md for the key
./mvnw -pl api-gateway spring-boot:run
```

Try it with a demo account:

```bash
# Login through the gateway
curl -s -X POST http://localhost:8080/api/v1/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"analyste1","password":"analyste-demo-2026"}'

# A protected route without a token: 401 Problem Details, with the correlation id
curl -i http://localhost:8080/api/v1/customers

# Service down (customer-service not started), with a token: 503 Problem Details
curl -i http://localhost:8080/api/v1/customers -H "Authorization: Bearer <accessToken>"

# Six wrong logins in a row: the 6th gets 429 with Retry-After
for i in 1 2 3 4 5 6; do
  curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8080/api/v1/auth/login \
       -H 'Content-Type: application/json' -d '{"username":"analyste1","password":"wrong-password"}'
done
```

Docker image and container checks: [`docs/api-gateway-docker.md`](../../docs/api-gateway-docker.md).

## Tests

`./mvnw -pl api-gateway -am verify`. No Docker needed: a JDK `HttpServer` (`FakeDownstream`) stands in for the services, and `TestJwt` signs real RS256 tokens with a throwaway key.

| Test | Covers |
|---|---|
| `GatewaySecurityTest` | public paths, `401` Problem Details, malformed token, Prometheus scrape |
| `CorrelationIdTest` | id kept, generated, replaced when not a UUID, present on `401` |
| `DownstreamTimeoutTest`, `DownstreamDownTest` | `503` Problem Details when a service is slow or down |
| `CorsTest` | preflight without token, unknown origin, headers on a `401` |
| `LoginRateLimiterTest`, `LoginRateLimitTest` | token bucket math, `429` + `Retry-After`, forged `X-Forwarded-For`, `/refresh` not limited |
| `SseRouteTest` | notification stream neither cut nor buffered |
| `NeverRoutedTest` | internal paths and path traversal never reach a service |

## Known limits

- **Rate limit is per pod (D42).** With N replicas the real limit is about N × the configured one, and a restart resets it.
- **Correlation id is not in the gateway's own logs yet.** It is forwarded and returned, but MDC does not follow WebFlux thread switches. This needs Reactor context propagation (follow-up).
- **SSE through Traefik.** Traefik's idle timeout can close a quiet stream. notification-service should send a comment line (`: ping`) every 15–20 s. The browser client (`fetch-event-source`, D37) reconnects on its own.
- **Firewall `400` has no body.** Requests rejected by Spring Security's firewall (step 2) get an empty `400`, not Problem Details.
