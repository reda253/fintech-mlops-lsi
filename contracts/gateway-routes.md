# api-gateway — routes and security (v1)

Spring Cloud Gateway, reactive (D31). Port 8080. Traefik sends `fintech.local/api/**` here.

## Routes

| Path | Target | Notes |
|---|---|---|
| `/api/v1/auth/**` | auth-service:8081 | `/login` and `/refresh` are public; `/login` is rate-limited in memory (brute-force protection) |
| `/api/v1/customers/**` | customer-service:8082 | |
| `/api/v1/transactions/**` | transaction-service:8083 | **No rate limit** (it would skew load tests) |
| `/api/v1/risk/**` | risk-service:8084 | |
| `/api/v1/notifications/**` | notification-service:8085 | `/stream` is SSE: long response timeout, no buffering |
| `/api/v1/audit/**` | audit-service:8086 | |
| `/api/v1/ml/**` | ml-service:8000 | Read-only model info, performance and visualisations |

**Never routed:** `/internal/**`, `/predict`, `/.well-known/jwks.json`, `/actuator/**`. They are also blocked by NetworkPolicies (§6.12). e2e scenario 7 checks that `/predict` returns `404` through the Ingress.

## Cross-cutting filters
- **Correlation id:** generate `X-Correlation-Id` (UUID) if absent, forward it, and return it on the response.
- **JWT:** validate signature and expiry against auth-service JWKS (cached), then forward the `Authorization` header unchanged. Each service re-validates it (D6).
- **Timeouts:** 1 s connect, 3 s response. On timeout or downstream failure, return `503` Problem Details. No retry at the gateway (Traefik retries, §9.6).
- **Connection pool:** max lifetime 30 s, so traffic moves to new pods after scale-up (§6.11).
- **CORS:** allow origin `https://fintech.local` (and `http://localhost:5173` in dev).

## Role matrix (§3.8), enforced in each service with `@PreAuthorize`

| Resource | ADMIN | ANALYSTE | SIMULATEUR |
|---|:-:|:-:|:-:|
| Users CRUD (`/api/v1/auth/users`) | ✔ | – | – |
| Customers read | ✔ | ✔ | – |
| Customers write | ✔ | – | – |
| Transactions create | – | – | ✔ |
| Feedback (`/api/v1/risk/feedback`) | – | – | ✔ |
| Transactions read | ✔ | ✔ | – |
| Reviews read and decide | – | ✔ | – |
| Notifications | ✔ | ✔ | – |
| Audit log | ✔ | – | – |
| ML info and visualisations | ✔ | ✔ | – |
| Risk assessments and stats | ✔ | ✔ | – |

`/internal/**` endpoints accept any valid JWT (the propagated caller token). Access is restricted by NetworkPolicy instead of by role, because the caller is a service acting for the original user (D33, D34).
