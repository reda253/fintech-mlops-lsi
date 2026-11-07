package ma.fintech.gateway.correlation;

import ma.fintech.common.correlation.CorrelationId;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

/**
 * Reactive counterpart of common's servlet CorrelationIdFilter (§3.10): keeps a valid incoming
 * {@code X-Correlation-Id} or generates one, forwards it to the routed service and echoes it on
 * the response.
 *
 * <p>A WebFilter rather than a gateway GlobalFilter: GlobalFilters run only on routed requests,
 * after Spring Security, so a 401 would carry no id. Highest precedence puts this filter ahead of
 * the security chain (order -100).
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationIdWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String id = CorrelationId.acceptOrGenerate(
                exchange.getRequest().getHeaders().getFirst(CorrelationId.HEADER));

        // The request is immutable in WebFlux: mutate() builds a copy with the header replaced,
        // so a client-sent invalid value never reaches the service.
        ServerWebExchange withId = exchange.mutate()
                .request(request -> request.headers(headers -> headers.set(CorrelationId.HEADER, id)))
                .build();

        // Set just before the response is committed, so it also wins over a header copied back
        // from the downstream response.
        withId.getResponse().beforeCommit(() -> {
            withId.getResponse().getHeaders().set(CorrelationId.HEADER, id);
            return Mono.empty();
        });
        return chain.filter(withId);
    }
}
