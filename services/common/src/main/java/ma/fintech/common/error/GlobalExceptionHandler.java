package ma.fintech.common.error;

import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

/**
 * Every error leaves the service as RFC 7807 Problem Details (§3.10). Spring MVC's own exceptions
 * and {@code ResponseStatusException}/{@code ErrorResponseException} keep their status; validation
 * errors list the fields; anything unexpected is a 500 whose message is logged, never returned.
 * Ordered last so a service's own {@code @RestControllerAdvice} wins.
 */
@RestControllerAdvice
@Order(Ordered.LOWEST_PRECEDENCE)
public class GlobalExceptionHandler extends ResponseEntityExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(Exception.class)
    ProblemDetail unexpected(Exception ex, WebRequest request) {
        log.error("Unhandled exception", ex);
        return ProblemDetails.of(HttpStatus.INTERNAL_SERVER_ERROR, "Unexpected error", request);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(MethodArgumentNotValidException ex,
                                                                  HttpHeaders headers, HttpStatusCode status,
                                                                  WebRequest request) {
        List<Map<String, String>> errors = ex.getBindingResult().getFieldErrors().stream()
                .map(error -> Map.of("field", error.getField(),
                        "message", String.valueOf(error.getDefaultMessage())))
                .toList();
        ex.getBody().setDetail("Validation failed");
        ex.getBody().setProperty(ProblemDetails.ERRORS, errors);
        return super.handleMethodArgumentNotValid(ex, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> createResponseEntity(Object body, HttpHeaders headers,
                                                          HttpStatusCode statusCode, WebRequest request) {
        if (body instanceof ProblemDetail problem) {
            ProblemDetails.enrich(problem, request);
        }
        return super.createResponseEntity(body, headers, statusCode, request);
    }
}
