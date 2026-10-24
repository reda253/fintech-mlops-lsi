package ma.fintech.common.error;

import java.net.URI;

import ma.fintech.common.correlation.CorrelationId;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.web.context.request.ServletWebRequest;
import org.springframework.web.context.request.WebRequest;

/** Builds the {@code ProblemDetail} body declared in contracts/common.yaml. */
public final class ProblemDetails {

    public static final String CORRELATION_ID = "correlationId";
    public static final String ERRORS = "errors";

    private ProblemDetails() {
    }

    public static ProblemDetail of(HttpStatusCode status, String detail, WebRequest request) {
        return enrich(ProblemDetail.forStatusAndDetail(status, detail), request);
    }

    /** Adds {@code instance} (request path) when missing, and the request's {@code correlationId}. */
    public static ProblemDetail enrich(ProblemDetail problem, WebRequest request) {
        if (problem.getInstance() == null && request instanceof ServletWebRequest servlet) {
            problem.setInstance(URI.create(servlet.getRequest().getRequestURI()));
        }
        CorrelationId.current().ifPresent(id -> problem.setProperty(CORRELATION_ID, id));
        return problem;
    }
}
