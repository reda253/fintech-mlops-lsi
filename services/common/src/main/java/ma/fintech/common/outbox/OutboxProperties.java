package ma.fintech.common.outbox;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * {@code fintech.outbox.*}. The relay and purge periods are plain milliseconds
 * ({@code relay-interval-ms}, {@code purge-interval-ms}) because {@code @Scheduled} reads them directly.
 *
 * @param enabled        turns the outbox on; only producers (auth, transaction, risk) have the table
 * @param batchSize      rows locked and published per relay run
 * @param confirmTimeout how long to wait for the broker's publisher confirm
 * @param retention      published rows older than this are purged (§3.5: 7 days)
 */
@ConfigurationProperties("fintech.outbox")
public record OutboxProperties(boolean enabled, Integer batchSize, Duration confirmTimeout, Duration retention) {

    public OutboxProperties {
        batchSize = batchSize != null ? batchSize : 100;
        confirmTimeout = confirmTimeout != null ? confirmTimeout : Duration.ofSeconds(5);
        retention = retention != null ? retention : Duration.ofDays(7);
    }
}
