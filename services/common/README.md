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

## Not here yet

Outbox, event envelope, idempotent consumer, RabbitMQ topology (#8), and metric tags (#14).
