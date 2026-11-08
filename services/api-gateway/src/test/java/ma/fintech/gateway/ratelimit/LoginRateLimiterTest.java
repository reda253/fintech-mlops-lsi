package ma.fintech.gateway.ratelimit;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Token bucket rules, with a fake clock so no test has to sleep. */
class LoginRateLimiterTest {

    private final AtomicLong nanos = new AtomicLong();

    /** 5 attempts, refilled at one every 12 s (5 per minute). */
    private final LoginRateLimiter limiter = new LoginRateLimiter(5, Duration.ofMinutes(1), 100, nanos::get);

    @Test
    void allowsBurstUpToCapacityThenRefuses() {
        for (int i = 0; i < 5; i++) {
            assertTrue(limiter.tryAcquire("1.2.3.4").allowed(), "attempt " + (i + 1));
        }
        LoginRateLimiter.Result refused = limiter.tryAcquire("1.2.3.4");
        assertFalse(refused.allowed());
        assertEquals(Duration.ofSeconds(12), refused.retryAfter());
    }

    @Test
    void refillsOneAttemptPerPeriodSlice() {
        drain("1.2.3.4");

        advance(Duration.ofSeconds(11));
        LoginRateLimiter.Result early = limiter.tryAcquire("1.2.3.4");
        assertFalse(early.allowed());
        assertEquals(Duration.ofSeconds(1), early.retryAfter());

        advance(Duration.ofSeconds(1));
        assertTrue(limiter.tryAcquire("1.2.3.4").allowed());
        assertFalse(limiter.tryAcquire("1.2.3.4").allowed());
    }

    @Test
    void neverRefillsAboveCapacity() {
        advance(Duration.ofHours(1));
        drain("1.2.3.4");
        assertFalse(limiter.tryAcquire("1.2.3.4").allowed());
    }

    @Test
    void eachKeyHasItsOwnBucket() {
        drain("1.2.3.4");
        assertTrue(limiter.tryAcquire("5.6.7.8").allowed());
    }

    /** Many distinct IPs must not grow the map forever: full buckets carry no state and are dropped. */
    @Test
    void forgetsIdleKeysWhenTooManyAreTracked() {
        for (int i = 0; i < 100; i++) {
            limiter.tryAcquire("10.0.0." + i);
        }
        advance(Duration.ofMinutes(1));          // every bucket is full again
        limiter.tryAcquire("10.0.1.1");          // over the limit of 100 keys: triggers the cleanup

        assertEquals(1, limiter.trackedKeys());
    }

    @Test
    void cleanupKeepsKeysThatAreStillLimited() {
        drain("1.2.3.4");
        for (int i = 0; i < 100; i++) {
            limiter.tryAcquire("10.0.0." + i);
        }
        assertFalse(limiter.tryAcquire("1.2.3.4").allowed(), "cleanup must not reset a limited key");
    }

    private void drain(String key) {
        for (int i = 0; i < 5; i++) {
            limiter.tryAcquire(key);
        }
    }

    private void advance(Duration duration) {
        nanos.addAndGet(duration.toNanos());
    }
}
