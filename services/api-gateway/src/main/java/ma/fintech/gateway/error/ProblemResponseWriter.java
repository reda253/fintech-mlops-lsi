package ma.fintech.gateway.error;

import java.net.URI;
import java.util.List;

import ma.fintech.common.error.ProblemDetails;
import ma.fintech.gateway.correlation.CorrelationIdWebFilter;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.codec.HttpMessageWriter;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.reactive.result.view.ViewResolver;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * Writes the ProblemDetail body of contracts/common.yaml (RFC 7807, {@code application/problem+json})
 * from reactive code, where common's servlet {@code ProblemDetails} helper cannot run.
 * Adds {@code instance} (request path) and {@code correlationId}, like the other services.
 */
@Component
public class ProblemResponseWriter {

    private final ServerResponse.Context context;

    public ProblemResponseWriter(ServerCodecConfigurer codecs) {
        // The same JSON writers WebFlux uses for controllers, so ProblemDetail is serialized the
        // standard way (its extra properties appear at the top level).
        List<HttpMessageWriter<?>> writers = codecs.getWriters();
        this.context = new ServerResponse.Context() {
            @Override
            public List<HttpMessageWriter<?>> messageWriters() {
                return writers;
            }

            @Override
            public List<ViewResolver> viewResolvers() {
                return List.of();
            }
        };
    }

    public Mono<Void> write(ServerWebExchange exchange, HttpStatusCode status, String detail) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(status, detail);
        problem.setInstance(URI.create(exchange.getRequest().getPath().value()));
        String correlationId = exchange.getAttribute(CorrelationIdWebFilter.ATTRIBUTE);
        if (correlationId != null) {
            problem.setProperty(ProblemDetails.CORRELATION_ID, correlationId);
        }
        return ServerResponse.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .bodyValue(problem)
                .flatMap(response -> response.writeTo(exchange, context));
    }
}
