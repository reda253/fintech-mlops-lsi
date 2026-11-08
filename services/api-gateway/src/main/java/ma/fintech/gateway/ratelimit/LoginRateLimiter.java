package ma.fintech.gateway.ratelimit;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.LongSupplier;

/**
 * In-memory rate limit per key (client IP), for brute-force protection on login (D42).
 *
 * <p>Token-bucket behaviour: each key may make {@code capacity} attempts in a burst, then one
 * attempt comes back every {@code period / capacity}. So "5 per minute" allows 5 at once, then
 * one every 12 s.
 *
 * <p>Implemented as GCRA (generic cell rate algorithm): instead of a fractional token count, each
 * key stores one instant, the "theoretical arrival time" (TAT). Every attempt pushes it one
 * interval later; an attempt is refused when the TAT would be more than one burst ahead of now.
 * Integer nanoseconds only, so no rounding drift.
 *
 * <p>State lives in this JVM only: with N gateway replicas the effective limit is about N times
 * higher, and a restart resets it. Accepted in D42.
 */
public class LoginRateLimiter {

    /** Outcome of one attempt; {@code retryAfter} is zero when allowed. */
    public record Result(boolean allowed, Duration retryAfter) {
    }

    private final long intervalNanos;
    private final long burstNanos;
    private final int maxTrackedKeys;
    private final LongSupplier nanoClock;
    private final Map<String, Long> arrivalTimes = new ConcurrentHashMap<>();

    public LoginRateLimiter(int capacity, Duration period, int maxTrackedKeys, LongSupplier nanoClock) {
        if (capacity < 1 || period.isNegative() || period.isZero()) {
            throw new IllegalArgumentException("capacity must be >= 1 and period > 0");
        }
        this.intervalNanos = period.toNanos() / capacity;
        this.burstNanos = intervalNanos * capacity;
        this.maxTrackedKeys = maxTrackedKeys;
        this.nanoClock = nanoClock;
    }

    public Result tryAcquire(String key) {
        long now = nanoClock.getAsLong();
        if (arrivalTimes.size() >= maxTrackedKeys) {
            forgetIdleKeys(now);
        }
        Result[] result = new Result[1];
        // compute() runs atomically per key, so two concurrent attempts cannot both pass.
        arrivalTimes.compute(key, (k, tat) -> {
            long current = tat == null ? now : Math.max(tat, now);
            long next = current + intervalNanos;
            long ahead = next - now;
            if (ahead > burstNanos) {
                result[0] = new Result(false, Duration.ofNanos(ahead - burstNanos));
                return tat;
            }
            result[0] = new Result(true, Duration.ZERO);
            return next;
        });
        return result[0];
    }

    int trackedKeys() {
        return arrivalTimes.size();
    }

    /**
     * A key whose TAT is in the past has its full burst back, the same as an unknown key, so
     * dropping it changes no decision. This bounds memory when many distinct IPs log in, without
     * resetting any IP that is currently limited.
     */
    private void forgetIdleKeys(long now) {
        arrivalTimes.values().removeIf(tat -> tat <= now);
    }
}
