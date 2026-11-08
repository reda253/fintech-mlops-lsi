package ma.fintech.gateway.ratelimit;

import java.time.Duration;

import ma.fintech.gateway.error.ProblemResponseWriter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.support.ipresolver.RemoteAddressResolver;
import org.springframework.cloud.gateway.support.ipresolver.XForwardedRemoteAddressResolver;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

/**
 * Applies {@link LoginRateLimiter} to {@code POST /api/v1/auth/login} only. Transactions are never
 * limited: it would skew the load tests (contracts/gateway-routes.md).
 *
 * <p>Registered after the Spring Security chain (see RateLimitConfig). Login is public, so security
 * lets it through, and the CORS headers are already on the response: the browser can read the 429.
 */
public class LoginRateLimitWebFilter implements WebFilter {

    static final String LOGIN_PATH = "/api/v1/auth/login";
    private static final Logger log = LoggerFactory.getLogger(LoginRateLimitWebFilter.class);

    /**
     * Client IP = the last X-Forwarded-For entry, the one Traefik appends. Earlier entries come
     * from the client and are ignored, so a forged header cannot buy a fresh limit. Without the
     * header (local run, no proxy), the TCP peer address is used.
     */
    private final RemoteAddressResolver clientIp = XForwardedRemoteAddressResolver.maxTrustedIndex(1);
    private final LoginRateLimiter limiter;
    private final ProblemResponseWriter problems;

    public LoginRateLimitWebFilter(LoginRateLimiter limiter, ProblemResponseWriter problems) {
        this.limiter = limiter;
        this.problems = problems;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        ServerHttpRequest request = exchange.getRequest();
        if (request.getMethod() != HttpMethod.POST || !LOGIN_PATH.equals(request.getPath().value())) {
            return chain.filter(exchange);
        }
        String ip = clientIp.resolve(exchange).getHostString();
        LoginRateLimiter.Result result = limiter.tryAcquire(ip);
        if (result.allowed()) {
            return chain.filter(exchange);
        }
        long seconds = Math.max(1, ceilSeconds(result.retryAfter()));
        log.warn("Login rate limit reached for {}, retry in {} s", ip, seconds);
        exchange.getResponse().getHeaders().set(HttpHeaders.RETRY_AFTER, Long.toString(seconds));
        return problems.write(exchange, HttpStatus.TOO_MANY_REQUESTS,
                "Too many login attempts, retry in " + seconds + " s");
    }

    private static long ceilSeconds(Duration duration) {
        long seconds = duration.toSeconds();
        return duration.toNanosPart() > 0 ? seconds + 1 : seconds;
    }
}
