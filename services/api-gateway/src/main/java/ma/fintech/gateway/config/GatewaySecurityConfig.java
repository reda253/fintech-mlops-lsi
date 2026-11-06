package ma.fintech.gateway.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

/**
 * Gateway edge security (§3.4, contracts/gateway-routes.md). Reactive, so SecurityWebFilterChain.
 * Every service re-validates the JWT itself (D6); role checks live in the services, not here.
 */
@Configuration(proxyBeanMethods = false)
public class GatewaySecurityConfig {

    @Bean
    SecurityWebFilterChain gatewaySecurity(ServerHttpSecurity http) {
        return http
                // Stateless Bearer-token API: no session or auth cookie for a CSRF attack to ride on.
                // Left on, Spring rejects every POST without a CSRF token with 403.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchange -> exchange
                        .pathMatchers(HttpMethod.GET,
                                "/actuator/health/liveness",
                                "/actuator/health/readiness").permitAll()
                        // No token exists yet at these two calls (auth-service.yaml: security: []).
                        .pathMatchers(HttpMethod.POST,
                                "/api/v1/auth/login",
                                "/api/v1/auth/refresh").permitAll()
                        .anyExchange().authenticated())
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
