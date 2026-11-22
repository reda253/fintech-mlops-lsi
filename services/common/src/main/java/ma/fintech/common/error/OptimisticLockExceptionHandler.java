package ma.fintech.common.error;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;

/**
 * A {@code @Version} conflict (two users editing the same row) is a 409, not a 500 (§3.7). Separate
 * from {@link GlobalExceptionHandler} so it is only registered when spring-tx is on the classpath.
 */
@RestControllerAdvice
@Order(Ordered.LOWEST_PRECEDENCE - 1)
public class OptimisticLockExceptionHandler {

    @ExceptionHandler(OptimisticLockingFailureException.class)
    ProblemDetail conflict(OptimisticLockingFailureException ex, WebRequest request) {
        return ProblemDetails.of(HttpStatus.CONFLICT,
                "The resource was modified by someone else. Reload it and try again.", request);
    }
}
