package ma.fintech.gateway.config;

import ma.fintech.gateway.error.ProblemDetailsAuthenticationEntryPoint;
import ma.fintech.gateway.error.ProblemResponseWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;

/**
 * Gateway edge security (§3.4, contracts/gateway-routes.md). Reactive, so SecurityWebFilterChain.
 * Every service re-validates the JWT itself (D6); role checks live in the services, not here.
 */
@Configuration(proxyBeanMethods = false)
public class GatewaySecurityConfig {

    @Bean
    SecurityWebFilterChain gatewaySecurity(ServerHttpSecurity http, ProblemResponseWriter problems) {
        ServerAuthenticationEntryPoint unauthorized = new ProblemDetailsAuthenticationEntryPoint(problems);
        return http
                // Stateless Bearer-token API: no session or auth cookie for a CSRF attack to ride on.
                // Left on, Spring rejects every POST without a CSRF token with 403.
                .csrf(ServerHttpSecurity.CsrfSpec::disable) // NOSONAR java:S4502 stateless Bearer-only API, see above
                // Uses the CorsConfigurationSource bean (CorsConfig). Answers preflights itself,
                // before the authorization rules below.
                .cors(Customizer.withDefaults())
                .authorizeExchange(exchange -> exchange
                        .pathMatchers(HttpMethod.GET,
                                "/actuator/health/liveness",
                                "/actuator/health/readiness").permitAll()
                        // Prometheus scrapes without a token; never routed from outside (D43).
                        .pathMatchers(HttpMethod.GET, "/actuator/prometheus").permitAll()
                        // No token exists yet at these two calls (auth-service.yaml: security: []).
                        .pathMatchers(HttpMethod.POST,
                                "/api/v1/auth/login",
                                "/api/v1/auth/refresh").permitAll()
                        .anyExchange().authenticated())
                // Both paths to a 401 use the same entry point: no token at all (exceptionHandling)
                // and an invalid or expired token (oauth2ResourceServer).
                .exceptionHandling(exceptions -> exceptions.authenticationEntryPoint(unauthorized))
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .authenticationEntryPoint(unauthorized)
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
