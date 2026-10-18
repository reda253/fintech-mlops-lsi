package ma.fintech.common.security;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.servlet.HandlerExceptionResolver;

/**
 * Every MVC service is a stateless resource server: it re-validates the RS256 JWT from auth-service
 * against the JWKS at {@code spring.security.oauth2.resourceserver.jwt.jwk-set-uri}, and maps the
 * {@code roles} claim to {@code ROLE_*} authorities. Runs before Boot's own security defaults, which
 * then back off. A service that declares its own {@link SecurityFilterChain} replaces this one.
 */
@AutoConfiguration(beforeName = {
        "org.springframework.boot.security.autoconfigure.web.servlet.ServletWebSecurityAutoConfiguration",
        "org.springframework.boot.security.oauth2.server.resource.autoconfigure.web.OAuth2ResourceServerWebSecurityAutoConfiguration"})
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnClass({SecurityFilterChain.class, JwtDecoder.class})
@EnableMethodSecurity
public class ResourceServerSecurityAutoConfiguration {

    public static final String ROLES_CLAIM = "roles";

    /** Kubernetes probes call these without a token (§6.7). */
    static final String[] PROBE_PATHS = {"/actuator/health/liveness", "/actuator/health/readiness"};

    @Bean
    @ConditionalOnMissingBean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter roles = new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName(ROLES_CLAIM);
        roles.setAuthorityPrefix("ROLE_");
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(roles);
        return converter;
    }

    @Bean
    SecurityExceptionHandler securityExceptionHandler() {
        return new SecurityExceptionHandler();
    }

    @Bean
    @ConditionalOnMissingBean(SecurityFilterChain.class)
    SecurityFilterChain resourceServerFilterChain(HttpSecurity http,
                                                  JwtAuthenticationConverter jwtAuthenticationConverter,
                                                  ObjectProvider<AuthorizationRules> serviceRules,
                                                  @Qualifier("handlerExceptionResolver") HandlerExceptionResolver resolver)
            throws Exception {
        ProblemDetailsSecurityHandler problemDetails =
                new ProblemDetailsSecurityHandler(new BearerTokenAuthenticationEntryPoint(), resolver);
        return http
                // Bearer tokens only, no cookies: CSRF does not apply and there is no session.
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(rules -> {
                    rules.requestMatchers(HttpMethod.GET, PROBE_PATHS).permitAll();
                    serviceRules.orderedStream().forEach(r -> r.configure(rules));
                    rules.anyRequest().authenticated();
                })
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter))
                        .authenticationEntryPoint(problemDetails)
                        .accessDeniedHandler(problemDetails))
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(problemDetails)
                        .accessDeniedHandler(problemDetails))
                .build();
    }
}
