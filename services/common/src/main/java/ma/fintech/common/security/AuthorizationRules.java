package ma.fintech.common.security;

import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AuthorizeHttpRequestsConfigurer;

/**
 * A service's own URL rules (role matrix, contracts/gateway-routes.md), applied by the common
 * filter chain after the open probe paths and before {@code anyRequest().authenticated()}.
 * Declare one or more as beans:
 *
 * <pre>{@code
 * @Bean
 * AuthorizationRules customerRules() {
 *     return rules -> rules.requestMatchers(HttpMethod.GET, "/api/v1/customers/**").hasAnyRole("ADMIN", "ANALYSTE");
 * }
 * }</pre>
 */
@FunctionalInterface
public interface AuthorizationRules {

    void configure(AuthorizeHttpRequestsConfigurer<HttpSecurity>.AuthorizationManagerRequestMatcherRegistry rules);
}
