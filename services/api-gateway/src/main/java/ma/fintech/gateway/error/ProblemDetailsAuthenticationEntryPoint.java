package ma.fintech.gateway.error;

import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpResponseDecorator;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * 401 with a Problem Details body. Spring's Bearer entry point still runs first, for the standard
 * {@code WWW-Authenticate: Bearer ...} header (RFC 6750), but it ends the response with no body.
 * Its {@code setComplete()} is turned into a no-op so the body can be written afterwards.
 */
public class ProblemDetailsAuthenticationEntryPoint implements ServerAuthenticationEntryPoint {

    private final ServerAuthenticationEntryPoint bearer = new BearerTokenServerAuthenticationEntryPoint();
    private final ProblemResponseWriter problems;

    public ProblemDetailsAuthenticationEntryPoint(ProblemResponseWriter problems) {
        this.problems = problems;
    }

    @Override
    public Mono<Void> commence(ServerWebExchange exchange, AuthenticationException ex) {
        ServerHttpResponseDecorator headersOnly = new ServerHttpResponseDecorator(exchange.getResponse()) {
            @Override
            public Mono<Void> setComplete() {
                return Mono.empty();
            }
        };
        return bearer.commence(exchange.mutate().response(headersOnly).build(), ex)
                .then(problems.write(exchange, HttpStatus.UNAUTHORIZED, "Missing or invalid access token"));
    }
}
