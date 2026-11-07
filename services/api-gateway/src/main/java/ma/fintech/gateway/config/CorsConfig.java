package ma.fintech.gateway.config;

import java.time.Duration;
import java.util.List;

import ma.fintech.common.correlation.CorrelationId;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

/**
 * CORS for the React app (contracts/gateway-routes.md). Spring Security picks this bean up through
 * {@code http.cors(...)} and applies it inside the security chain, before authentication: a browser
 * never sends the Authorization header on a preflight, so the preflight must not need one.
 * (Spring Cloud Gateway's own {@code globalcors} runs after security and would get a 401.)
 *
 * <p>Services set no CORS headers themselves; only the browser-facing edge does.
 */
@Configuration(proxyBeanMethods = false)
public class CorsConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource(
            @Value("${gateway.cors.allowed-origins}") List<String> allowedOrigins) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(allowedOrigins);
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(List.of(
                HttpHeaders.AUTHORIZATION,
                HttpHeaders.CONTENT_TYPE,
                CorrelationId.HEADER,
                "Last-Event-ID"));          // EventSource reconnect on the SSE stream
        // Readable by the app's JavaScript; the browser hides any other response header.
        cors.setExposedHeaders(List.of(
                CorrelationId.HEADER,
                HttpHeaders.LOCATION,       // 201 Created
                HttpHeaders.RETRY_AFTER));  // 429 on /login
        // Bearer token in a header, refresh token in the JSON body: no cookie to send.
        cors.setAllowCredentials(false);
        cors.setMaxAge(Duration.ofHours(1)); // browser caches the preflight answer

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
