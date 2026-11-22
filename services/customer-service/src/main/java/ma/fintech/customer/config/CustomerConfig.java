package ma.fintech.customer.config;

import ma.fintech.common.security.AuthorizationRules;
import ma.fintech.customer.service.CardFingerprinter;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CustomerProperties.class)
public class CustomerConfig {

    /** Fails the startup when CARD_HMAC_KEY is missing or too short. */
    @Bean
    CardFingerprinter cardFingerprinter(CustomerProperties properties) {
        return new CardFingerprinter(properties.cardHmacKey());
    }

    /**
     * Role matrix (contracts/gateway-routes.md): read = ADMIN, ANALYSTE; write = ADMIN.
     * {@code /internal/**} falls through to "authenticated" (any valid JWT).
     */
    @Bean
    AuthorizationRules customerRules() {
        return rules -> rules
                .requestMatchers(HttpMethod.GET, "/api/v1/customers", "/api/v1/customers/**")
                .hasAnyRole("ADMIN", "ANALYSTE")
                .requestMatchers("/api/v1/customers", "/api/v1/customers/**").hasRole("ADMIN");
    }
}
