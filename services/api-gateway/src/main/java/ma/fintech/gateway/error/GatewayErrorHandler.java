package ma.fintech.gateway.error;

import java.net.ConnectException;
import java.util.concurrent.TimeoutException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.webflux.error.ErrorWebExceptionHandler;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.netty.http.client.PrematureCloseException;

/**
 * Every error the gateway itself produces, as Problem Details. Ordered before Boot's default
 * handler (-1), which would answer with its own JSON shape.
 *
 * <p>Downstream down or too slow is a 503 (§3.6, docs/architecture.md), not Spring Cloud Gateway's
 * default 500 (connection refused) or 504 (response timeout). The gateway does not retry: Traefik
 * does (§9.6), and it retries on 503.
 */
@Component
@Order(-2)
class GatewayErrorHandler implements ErrorWebExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GatewayErrorHandler.class);

    private final ProblemResponseWriter problems;

    GatewayErrorHandler(ProblemResponseWriter problems) {
        this.problems = problems;
    }

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
        if (exchange.getResponse().isCommitted()) {
            // Part of the downstream response is already on the wire; nothing can be rewritten.
            return Mono.error(ex);
        }
        String path = exchange.getRequest().getPath().value();
        if (isDownstreamUnavailable(ex)) {
            log.warn("Downstream unavailable for {}: {}", path, ex.toString());
            return problems.write(exchange, HttpStatus.SERVICE_UNAVAILABLE,
                    "The service is temporarily unavailable, please retry later");
        }
        if (ex instanceof ResponseStatusException status) {
            // 404 for an unknown path, 405, ...: keep the status, but not the internal reason text.
            return problems.write(exchange, status.getStatusCode(), null);
        }
        log.error("Unexpected gateway error for {}", path, ex);
        return problems.write(exchange, HttpStatus.INTERNAL_SERVER_ERROR, "Unexpected error");
    }

    /** Connection refused or timed out, response timeout, or connection closed mid-response. */
    private static boolean isDownstreamUnavailable(Throwable ex) {
        for (Throwable t = ex; t != null; t = t.getCause()) {
            if (t instanceof ResponseStatusException status) {
                int code = status.getStatusCode().value();
                // 504: Spring Cloud Gateway's response timeout. 503: no instance for the route.
                if (code == 504 || code == 503) {
                    return true;
                }
            }
            if (t instanceof ConnectException
                    || t instanceof TimeoutException
                    || t instanceof PrematureCloseException) {
                return true;
            }
        }
        return false;
    }
}
