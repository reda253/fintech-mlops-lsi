package ma.fintech.common.outbox;

import java.sql.Timestamp;
import java.time.Instant;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.Scheduled;

/**
 * Deletes rows published more than {@code fintech.outbox.retention} ago (default 7 days, §3.5).
 * Unpublished rows are never deleted. Every replica runs it; repeating the DELETE is harmless.
 */
public class OutboxPurgeJob {

    private static final Logger log = LoggerFactory.getLogger(OutboxPurgeJob.class);

    private final JdbcClient jdbc;
    private final OutboxProperties properties;

    public OutboxPurgeJob(JdbcClient jdbc, OutboxProperties properties) {
        this.jdbc = jdbc;
        this.properties = properties;
    }

    @Scheduled(initialDelayString = "${fintech.outbox.purge-initial-delay-ms:60000}",
            fixedDelayString = "${fintech.outbox.purge-interval-ms:3600000}")
    public void purge() {
        int deleted = jdbc.sql("DELETE FROM outbox_events WHERE published_at < :cutoff")
                .param("cutoff", Timestamp.from(Instant.now().minus(properties.retention())))
                .update();
        if (deleted > 0) {
            log.info("Outbox purge deleted {} published event(s)", deleted);
        }
    }
}
