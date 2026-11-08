package ma.fintech.gateway.config;

import java.time.Duration;

import ma.fintech.gateway.error.ProblemResponseWriter;
import ma.fintech.gateway.ratelimit.LoginRateLimitWebFilter;
import ma.fintech.gateway.ratelimit.LoginRateLimiter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

/** Login brute-force limit (D42). Values from env vars, see application.yml. */
@Configuration(proxyBeanMethods = false)
public class RateLimitConfig {

    /** Upper bound on IPs tracked at once; idle ones are dropped past it. */
    private static final int MAX_TRACKED_IPS = 10_000;

    @Bean
    LoginRateLimiter loginRateLimiter(
            @Value("${gateway.rate-limit.login.capacity}") int capacity,
            @Value("${gateway.rate-limit.login.period}") Duration period) {
        return new LoginRateLimiter(capacity, period, MAX_TRACKED_IPS, System::nanoTime);
    }

    /** Order 0: after the Spring Security chain (-100), so CORS headers are already set. */
    @Bean
    @Order(0)
    LoginRateLimitWebFilter loginRateLimitWebFilter(LoginRateLimiter limiter, ProblemResponseWriter problems) {
        return new LoginRateLimitWebFilter(limiter, problems);
    }
}
