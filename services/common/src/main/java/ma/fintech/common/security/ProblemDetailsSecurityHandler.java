package ma.fintech.common.security;

import java.io.IOException;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.web.servlet.HandlerExceptionResolver;

/**
 * 401/403 raised in the security filter chain never reach a controller, so they are handed to the
 * MVC exception resolvers. {@link SecurityExceptionHandler} then writes the same Problem Details
 * body as every other error. The Bearer entry point runs first for its {@code WWW-Authenticate} header.
 */
class ProblemDetailsSecurityHandler implements AuthenticationEntryPoint, AccessDeniedHandler {

    private final AuthenticationEntryPoint bearer;
    private final HandlerExceptionResolver resolver;

    ProblemDetailsSecurityHandler(AuthenticationEntryPoint bearer, HandlerExceptionResolver resolver) {
        this.bearer = bearer;
        this.resolver = resolver;
    }

    @Override
    public void commence(HttpServletRequest request, HttpServletResponse response, AuthenticationException ex)
            throws IOException, ServletException {
        bearer.commence(request, response, ex);
        resolver.resolveException(request, response, null, ex);
    }

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response, AccessDeniedException ex) {
        resolver.resolveException(request, response, null, ex);
    }
}
