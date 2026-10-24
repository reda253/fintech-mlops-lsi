package ma.fintech.common.security;

import ma.fintech.common.error.ProblemDetails;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;

/**
 * 401 and 403 as Problem Details, whether raised by the filter chain or by {@code @PreAuthorize}.
 * Ordered before {@link ma.fintech.common.error.GlobalExceptionHandler}, whose catch-all would
 * otherwise turn them into 500s.
 */
@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class SecurityExceptionHandler {

    @ExceptionHandler(AuthenticationException.class)
    ProblemDetail unauthorized(AuthenticationException ex, WebRequest request) {
        return ProblemDetails.of(HttpStatus.UNAUTHORIZED, "Missing or invalid access token", request);
    }

    @ExceptionHandler(AccessDeniedException.class)
    ProblemDetail forbidden(AccessDeniedException ex, WebRequest request) {
        return ProblemDetails.of(HttpStatus.FORBIDDEN, "Your role does not allow this operation", request);
    }
}
